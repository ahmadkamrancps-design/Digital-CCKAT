import sys
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import cli
from app.config import Settings
from app.core import passwords
from app.core.passwords import hash_password, validate_new_password, verify_password
from app.models import AuditEvent, AuthSession, Role, SecurityEvent, User
from app.services.staff_login_service import set_staff_password

PASSWORD = "A sample staff passphrase 2026"


@pytest.fixture(scope="module")
def encoded_password() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def staff(db_factory: sessionmaker[Session], encoded_password: str) -> User:
    with db_factory() as db:
        user = User(
            email="staff@cck.edu.pk",
            display_name="Approved Staff",
            role=Role.ADMIN,
            password_hash=encoded_password,
        )
        db.add(user)
        db.commit()
        return user


def sign_in(client: TestClient, headers: dict[str, str], **changes: str) -> Response:
    return client.post(
        "/api/auth/staff",
        json={"email": "staff@cck.edu.pk", "password": PASSWORD, **changes},
        headers=headers,
    )


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PROCTOR, Role.EXAMINER])
def test_approved_staff_password_login_cookie_rbac_and_logout(
    client: TestClient,
    staff: User,
    db_factory: sessionmaker[Session],
    login_headers: dict[str, str],
    role: Role,
) -> None:
    with db_factory() as db:
        db.get(User, staff.id).role = role
        db.commit()
    response = sign_in(client, login_headers, email=" STAFF@CCK.EDU.PK ")
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["role"] == role and data["candidate"] is None
    assert "password" not in response.text and "argon2" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/me").json() == data
    assert client.get("/api/admin/questions").status_code == (200 if role == Role.ADMIN else 403)
    with db_factory() as db:
        event = db.scalar(select(SecurityEvent))
        assert event.method == "PASSWORD" and event.event_type == "LOGIN_SUCCESS"
        assert db.get(User, staff.id).google_subject is None
    assert client.post("/api/auth/logout", headers=login_headers).status_code == 403
    assert (
        client.post(
            "/api/auth/logout",
            headers={
                **login_headers,
                "X-CSRF-Token": data["csrf_token"],
            },
        ).status_code
        == 204
    )
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("scenario", ["unknown", "wrong", "disabled", "candidate", "unset"])
def test_password_login_rejects_every_ineligible_case_with_same_message(
    client: TestClient,
    staff: User,
    db_factory: sessionmaker[Session],
    login_headers: dict[str, str],
    scenario: str,
) -> None:
    with db_factory() as db:
        user = db.get(User, staff.id)
        if scenario == "disabled":
            user.is_active = False
        elif scenario == "candidate":
            user.role = Role.CANDIDATE
        elif scenario == "unset":
            user.password_hash = None
        db.commit()
    response = sign_in(
        client,
        login_headers,
        email="unknown@cck.edu.pk" if scenario == "unknown" else "staff@cck.edu.pk",
        password="wrong password" if scenario == "wrong" else PASSWORD,
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Unable to sign in. Check your email and password."}
    assert "cck_session" not in client.cookies
    with db_factory() as db:
        assert db.scalar(select(AuthSession)) is None
        assert db.scalar(select(SecurityEvent)).event_type == "LOGIN_FAILURE"


def test_password_login_origin_and_input_validation(
    client: TestClient,
    login_headers: dict[str, str],
) -> None:
    assert sign_in(client, {}).status_code == 403
    assert sign_in(client, {"Origin": "https://evil.example"}).status_code == 403
    for changes in ({"password": "x" * 129}, {"email": "invalid"}):
        response = sign_in(client, login_headers, **changes)
        assert response.status_code == 422
        assert response.json() == {"detail": "Please check the request data."}
    response = client.post(
        "/api/auth/staff",
        content=b'{"email":"staff@cck.edu.pk","password":"\\ud800"}',
        headers={**login_headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("scope", ["email", "ip"])
def test_password_login_is_rate_limited_before_kdf(
    client: TestClient,
    settings: Settings,
    login_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
) -> None:
    setattr(settings, "staff_login_" + scope + "_limit", 1)
    verifier = Mock(return_value=False)
    monkeypatch.setattr("app.services.staff_login_service.verify_password", verifier)
    assert sign_in(client, login_headers).status_code == 401
    response = sign_in(
        client, login_headers, email="other@cck.edu.pk" if scope == "ip" else "staff@cck.edu.pk"
    )
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert verifier.call_count == 1


def test_password_rotation_and_operator_reset_revoke_sessions_and_audit(
    client: TestClient,
    staff: User,
    db_factory: sessionmaker[Session],
    login_headers: dict[str, str],
) -> None:
    assert sign_in(client, login_headers).status_code == 200
    old = client.cookies.get("cck_session")
    assert sign_in(client, login_headers).status_code == 200
    assert client.cookies.get("cck_session") != old
    with TestClient(client.app) as reopened:
        reopened.cookies.set("cck_session", old)
        assert reopened.get("/api/me").status_code == 401
    with db_factory() as db:
        set_staff_password(db, staff.email, "Another longer staff passphrase")
        assert db.scalar(select(AuditEvent)).event_type == "STAFF_PASSWORD_SET"
    assert client.get("/api/me").status_code == 401
    assert sign_in(client, login_headers).status_code == 401
    assert (
        sign_in(client, login_headers, password="Another longer staff passphrase").status_code
        == 200
    )


def test_google_route_can_be_disabled_without_disabling_password_login(
    client: TestClient,
    settings: Settings,
    staff: User,
    login_headers: dict[str, str],
) -> None:
    settings.google_login_enabled = False
    assert (
        client.post(
            "/api/auth/google", json={"credential": "test-valid-credential"}, headers=login_headers
        ).status_code
        == 404
    )
    assert sign_in(client, login_headers).status_code == 200


def test_password_hash_salt_unicode_and_malformed_hashes(encoded_password: str) -> None:
    assert encoded_password.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert hash_password(PASSWORD) != encoded_password
    assert verify_password(PASSWORD, encoded_password)
    assert not verify_password(PASSWORD + " ", encoded_password)
    for malformed in (None, "invalid", encoded_password.replace("m=65536", "m=999999999")):
        assert not verify_password(PASSWORD, malformed)
    unicode_password = " یہ ایک محفوظ پاس ورڈ ہے "
    assert verify_password(unicode_password, hash_password(unicode_password))


@pytest.mark.parametrize("password", ["short", " " * 16, "x" * 129, "valid long phrase\n"])
def test_new_password_policy(password: str) -> None:
    with pytest.raises(ValueError):
        validate_new_password(password)


def test_kdf_concurrency_is_bounded() -> None:
    assert passwords._workers.acquire(blocking=False)
    assert passwords._workers.acquire(blocking=False)
    try:
        with pytest.raises(HTTPException) as exc:
            verify_password(PASSWORD, None)
        assert exc.value.status_code == 503
    finally:
        passwords._workers.release()
        passwords._workers.release()


def test_cli_password_reset_accepts_stdin_without_echo(
    staff: User,
    db_engine: Engine,
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from io import StringIO

    monkeypatch.setattr(
        sys, "argv", ["cli", "set-staff-password", "--email", staff.email, "--password-stdin"]
    )
    monkeypatch.setattr(sys, "stdin", StringIO(PASSWORD + "\n"))
    monkeypatch.setattr(cli, "create_db_engine", lambda _: db_engine)
    # The CLI disposes its own engine; keep the fixture's in-memory DB alive for assertions.
    with monkeypatch.context() as context:
        context.setattr(db_engine, "dispose", lambda: None)
        cli.main()
    assert PASSWORD not in capsys.readouterr().out
    with db_factory() as db:
        assert verify_password(PASSWORD, db.get(User, staff.id).password_hash)
        with pytest.raises(ValueError):
            set_staff_password(db, "not-approved@cck.edu.pk", PASSWORD)
