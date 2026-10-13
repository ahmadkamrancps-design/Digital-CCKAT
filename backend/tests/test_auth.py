from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.permissions import require_roles
from app.core.security import token_hash, utc_now
from app.models import AuthSession, Candidate, CandidateStatus, Role, User
from app.services.google_identity import GoogleIdentity
from tests.conftest import FakeIdentityVerifier


def sign_in(client: TestClient, headers: dict[str, str]) -> Response:
    return client.post(
        "/api/auth/google", json={"credential": "test-valid-credential"}, headers=headers
    )


def test_registered_candidate_login_refresh_and_logout(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    response = sign_in(client, login_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate"]["roll_number"] == "CCK-104"
    assert data["user"]["role"] == "CANDIDATE"
    assert "google_subject" not in data["user"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api" in cookie
    raw_token = client.cookies.get("cck_session")
    assert raw_token not in str(data)
    assert response.headers["cache-control"] == "no-store"
    with db_factory() as db:
        saved = db.scalar(select(AuthSession))
        assert saved.token_hash == token_hash(raw_token)
        assert db.get(User, approved_user.id).google_subject == "google-sub-104"
    # New HTTP client simulates reopening/refreshing; session survives without browser state.
    with TestClient(client.app) as reopened:
        reopened.cookies.set("cck_session", raw_token)
        assert reopened.get("/api/me").json() == data
        assert reopened.get("/api/candidate/me").status_code == 200
    logout = client.post(
        "/api/auth/logout",
        headers={**login_headers, "X-CSRF-Token": data["csrf_token"]},
    )
    assert logout.status_code == 204
    client.cookies.set("cck_session", raw_token)
    assert client.get("/api/me").status_code == 401
    with db_factory() as db:
        assert db.scalar(select(AuthSession)) is None


def test_unregistered_google_account_cannot_enter(
    client: TestClient, login_headers: dict[str, str], db_factory: sessionmaker[Session]
) -> None:
    assert sign_in(client, login_headers).status_code == 403
    assert "cck_session" not in client.cookies
    with db_factory() as db:
        assert db.scalar(select(User)) is None
        assert db.scalar(select(AuthSession)) is None


@pytest.mark.parametrize("credential", ["forged", "expired", "wrong-audience"])
def test_invalid_google_credential_denied(
    client: TestClient, approved_user: User, login_headers: dict[str, str], credential: str
) -> None:
    response = client.post(
        "/api/auth/google", json={"credential": credential}, headers=login_headers
    )
    assert response.status_code == 401
    assert "cck_session" not in client.cookies


@pytest.mark.parametrize("path", ["/api/me", "/api/candidate/me"])
def test_anonymous_access_denied(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "origin", [None, "http://evil.example", "http://localhost:5173.evil.example"]
)
def test_login_origin_required(client: TestClient, approved_user: User, origin: str | None) -> None:
    headers = {} if origin is None else {"Origin": origin}
    assert sign_in(client, headers).status_code == 403


@pytest.mark.parametrize("change", ["disabled_user", "disabled_candidate", "missing_candidate"])
def test_ineligible_candidate_denied_at_login(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    change: str,
) -> None:
    with db_factory() as db:
        user = db.get(User, approved_user.id)
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
        if change == "disabled_user":
            user.is_active = False
        elif change == "disabled_candidate":
            candidate.status = CandidateStatus.DISABLED
        else:
            db.delete(candidate)
        db.commit()
    assert sign_in(client, login_headers).status_code == 403


def test_disable_candidate_revokes_existing_access(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    assert sign_in(client, login_headers).status_code == 200
    with db_factory() as db:
        candidate = db.scalar(select(Candidate))
        candidate.status = CandidateStatus.DISABLED
        db.commit()
    assert client.get("/api/me").status_code == 403


def test_expired_session_cannot_access(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    sign_in(client, login_headers)
    with db_factory() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/me").status_code == 401


def test_new_login_rotates_and_revokes_old_session(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    sign_in(client, login_headers)
    old_cookie = client.cookies.get("cck_session")
    sign_in(client, login_headers)
    assert client.cookies.get("cck_session") != old_cookie
    with db_factory() as db:
        assert len(db.scalars(select(AuthSession)).all()) == 1
    client.cookies.clear()
    client.cookies.set("cck_session", old_cookie)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("csrf", [None, "wrong"])
def test_logout_requires_csrf(
    client: TestClient, approved_user: User, login_headers: dict[str, str], csrf: str | None
) -> None:
    sign_in(client, login_headers)
    headers = {**login_headers, **({"X-CSRF-Token": csrf} if csrf else {})}
    assert client.post("/api/auth/logout", headers=headers).status_code == 403
    assert client.get("/api/me").status_code == 200


def test_logout_rejects_foreign_origin(
    client: TestClient, approved_user: User, login_headers: dict[str, str]
) -> None:
    data = sign_in(client, login_headers).json()
    assert (
        client.post(
            "/api/auth/logout",
            headers={
                "Origin": "http://evil.example",
                "X-CSRF-Token": data["csrf_token"],
            },
        ).status_code
        == 403
    )


def test_bound_subject_cannot_be_replaced_by_matching_email(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    verifier: FakeIdentityVerifier,
) -> None:
    sign_in(client, login_headers)
    client.cookies.clear()
    verifier.identity = GoogleIdentity("different-sub", "candidate@gmail.com", True)
    assert sign_in(client, login_headers).status_code == 403


def test_stable_subject_login_survives_email_change(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    verifier: FakeIdentityVerifier,
) -> None:
    sign_in(client, login_headers)
    verifier.identity = GoogleIdentity("google-sub-104", "changed@gmail.com", True)
    response = sign_in(client, login_headers)
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "candidate@gmail.com"


def test_third_party_email_requires_approved_subject(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    verifier: FakeIdentityVerifier,
) -> None:
    with db_factory() as db:
        user = db.get(User, approved_user.id)
        assert user is not None
        user.email = "candidate@example.org"
        db.commit()
    verifier.identity = GoogleIdentity("google-sub-104", "candidate@example.org", False)
    assert sign_in(client, login_headers).status_code == 403
    with db_factory() as db:
        user = db.get(User, approved_user.id)
        assert user is not None
        user.google_subject = "google-sub-104"
        db.commit()
    assert sign_in(client, login_headers).status_code == 200


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PROCTOR, Role.EXAMINER])
def test_staff_cannot_use_candidate_endpoint(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    role: Role,
) -> None:
    with db_factory() as db:
        user = db.get(User, approved_user.id)
        user.role = role
        db.commit()
    assert sign_in(client, login_headers).status_code == 200
    assert client.get("/api/me").json()["candidate"] is None
    assert client.get("/api/candidate/me").status_code == 403


def test_candidate_cannot_use_admin_dependency(
    application: FastAPI,
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
) -> None:
    @application.get("/api/test-admin", dependencies=[Depends(require_roles(Role.ADMIN))])
    def admin_only() -> dict[str, str]:
        return {"status": "ok"}

    sign_in(client, login_headers)
    assert client.get("/api/test-admin").status_code == 403


def test_validation_does_not_echo_credential(
    client: TestClient, login_headers: dict[str, str]
) -> None:
    credential = "SENSITIVE_CREDENTIAL" * 1000
    response = client.post(
        "/api/auth/google", json={"credential": credential}, headers=login_headers
    )
    assert response.status_code == 422
    assert "SENSITIVE_CREDENTIAL" not in response.text


def test_secure_cookie_when_configured(
    application: FastAPI,
    settings: Settings,
    approved_user: User,
    login_headers: dict[str, str],
) -> None:
    settings.session_cookie_secure = True
    with TestClient(application, base_url="https://testserver") as client:
        response = sign_in(client, login_headers)
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/api/me").status_code == 200
