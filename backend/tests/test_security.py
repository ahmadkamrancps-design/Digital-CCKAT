"""Adversarial HTTP, role boundaries, and PostgreSQL history protection."""

import asyncio
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import Message, Receive, Scope, Send

from app.auth_maintenance import prune_expired_auth
from app.config import Settings
from app.core.http_security import RequestLimitsMiddleware
from app.core.security import token_hash, utc_now
from app.main import create_app
from app.models import AuthSession, Candidate, LoginThrottle, Role, SecurityEvent, User
from app.schemas.auth import CandidateLoginRequest
from app.services.candidate_login_service import candidate_login


@pytest.mark.parametrize("csrf", [b"\xff", b"x" * 500, b"", b"wrong"])
def test_malformed_csrf_denied_without_breaking_session(
    client: TestClient, approved_user: User, login_headers: dict[str, str], csrf: bytes
) -> None:
    signed = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    assert signed.status_code == 200
    response = client.post(
        "/api/auth/logout",
        headers=[(b"origin", login_headers["Origin"].encode()), (b"x-csrf-token", csrf)],
    )
    assert response.status_code == 403
    assert client.get("/api/me").status_code == 200


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_login_rejects_non_json_before_authentication(
    client: TestClient,
    login_headers: dict[str, str],
    content_type: str | None,
    db_factory: sessionmaker[Session],
) -> None:
    headers = {**login_headers, **({"Content-Type": content_type} if content_type else {})}
    response = client.post(
        "/api/auth/google", headers=headers, content='{"credential":"test-valid-credential"}'
    )
    assert response.status_code == 415
    with db_factory() as db:
        assert db.scalar(select(AuthSession)) is None
        assert db.scalar(select(LoginThrottle)) is None


def test_oversized_or_compressed_input_is_rejected_safely(
    client: TestClient,
    login_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "PRIVATE" * 4000}
    )
    assert response.status_code == 413
    assert "PRIVATE" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/auth/google",
            content=b"gzip data",
            headers={**login_headers, "Content-Encoding": "gzip"},
        ).status_code
        == 415
    )


@pytest.mark.parametrize("declared", [None, "1", "9" * 5000])
def test_streamed_body_limit_does_not_trust_declared_length(declared: str | None) -> None:
    reached_app = False
    sent: list[Message] = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"x" * 8000, "more_body": True},
            {"type": "http.request", "body": b"y" * 9000, "more_body": False},
        ]
    )

    async def receive() -> Message:
        return next(chunks)

    async def send(message: Message) -> None:
        sent.append(message)

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal reached_app
        reached_app = True

    headers = [(b"content-type", b"application/json")]
    if declared is not None:
        headers.append((b"content-length", declared.encode()))
    scope: Scope = {"type": "http", "path": "/api/auth/google", "headers": headers}
    asyncio.run(RequestLimitsMiddleware(downstream, max_bytes=2097152)(scope, receive, send))
    assert not reached_app
    assert sent[0]["status"] == 413


@pytest.mark.parametrize(
    "path,status", [("/api/health", 200), ("/api/missing", 404), ("/api/me", 401)]
)
def test_security_headers_cover_success_and_errors(
    client: TestClient, path: str, status: int
) -> None:
    response = client.get(path)
    assert response.status_code == status
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers


def test_unexpected_error_is_safe_and_has_security_headers(application: FastAPI) -> None:
    @application.get("/api/test-only-failure")
    def fail() -> None:
        raise RuntimeError("PRIVATE traceback and credentials")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/test-only-failure")
    assert response.status_code == 500
    assert "PRIVATE" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_private_exception_does_not_escape_to_server_logs(
    application: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    @application.get("/api/test-only-private-error")
    def fail() -> None:
        raise RuntimeError("PRIVATE credential or candidate answer")

    async def request() -> None:
        # Unlike TestClient(raise_server_exceptions=False), this fails if any
        # handled exception is re-raised to the server after the JSON response.
        async with AsyncClient(
            transport=ASGITransport(app=application, raise_app_exceptions=True),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/test-only-private-error")
            assert response.status_code == 500
            assert "PRIVATE" not in response.text
            assert response.headers["cache-control"] == "no-store"

    asyncio.run(request())
    assert "error_type=RuntimeError" in caplog.text
    assert "PRIVATE" not in caplog.text


def test_production_hides_docs_and_uses_hsts() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        session_cookie_secure=True,
        frontend_origin="https://test.cck.example",
        allowed_hosts=["test.cck.example"],
        database_url="postgresql+psycopg://cck:separate-password@db/cck",
    )
    with TestClient(create_app(settings), base_url="https://test.cck.example") as client:
        for path in ["/docs", "/openapi.json"]:
            assert client.get(path).status_code == 404
        assert client.get("/api/health").headers["strict-transport-security"] == "max-age=31536000"
    assert "separate-password" not in repr(settings)


@pytest.mark.parametrize(
    "origin",
    [
        "https://test.example:invalid",
        "https://test.example:0",
        "https://test.example:65536",
        "https://test. example",
    ],
)
def test_invalid_origin_configuration_denied(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, frontend_origin=origin)


@pytest.mark.parametrize("hosts", [["*.example.com"], ["example.com:8000"], [""], ["bad host"]])
def test_non_explicit_host_configuration_denied(hosts: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_hosts=hosts)


def test_google_throttle_survives_clients_and_does_not_verify_blocked_tokens(
    client: TestClient,
    application: FastAPI,
    settings: Settings,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    settings.google_login_ip_limit = 2
    with patch.object(
        application.state.identity_verifier,
        "verify",
        wraps=application.state.identity_verifier.verify,
    ) as verify:
        for _ in range(2):
            assert (
                client.post(
                    "/api/auth/google", headers=login_headers, json={"credential": "forged"}
                ).status_code
                == 401
            )
        for _ in range(4):
            with TestClient(application) as other:
                response = other.post(
                    "/api/auth/google",
                    headers={**login_headers, "X-Forwarded-For": str(uuid.uuid4())},
                    json={"credential": "forged"},
                )
                assert response.status_code == 429
                assert 1 <= int(response.headers["retry-after"]) <= 900
        assert verify.call_count == 2
    with db_factory() as db:
        assert db.scalar(select(LoginThrottle.attempts)) == 4
        events = list(db.scalars(select(SecurityEvent)))
        assert sorted(event.event_type for event in events) == [
            "LOGIN_FAILURE",
            "LOGIN_FAILURE",
            "LOGIN_THROTTLED",
        ]
        assert all(event.user_id is None for event in events)


def test_blocked_ip_cannot_create_unbounded_roll_buckets(
    client: TestClient,
    settings: Settings,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    settings.candidate_login_ip_limit = 2
    for number in range(8):
        response = client.post(
            "/api/auth/candidate",
            headers=login_headers,
            json={
                "roll_number": f"unknown-{number}",
                "full_name": "Unknown",
                "father_name": "Unknown",
            },
        )
        assert response.status_code == (401 if number < 2 else 429)
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(LoginThrottle)) == 3
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.event_type == "LOGIN_THROTTLED")
            )
            == 1
        )


def test_login_logout_trail_omits_submitted_personal_data(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    signed = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    assert signed.status_code == 200
    assert (
        client.post(
            "/api/auth/logout",
            headers={**login_headers, "X-CSRF-Token": signed.json()["csrf_token"]},
        ).status_code
        == 204
    )
    with db_factory() as db:
        events = list(db.scalars(select(SecurityEvent).order_by(SecurityEvent.server_timestamp)))
        assert {event.event_type for event in events} == {"LOGIN_SUCCESS", "LOGOUT"}
        assert all(event.user_id == approved_user.id for event in events)
        assert set(SecurityEvent.__table__.columns.keys()) == {
            "id",
            "user_id",
            "event_type",
            "method",
            "server_timestamp",
        }


@pytest.mark.parametrize("role", list(Role))
def test_entire_privileged_route_surface_rejects_wrong_roles(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    login_headers: dict[str, str],
    role: Role,
) -> None:
    with db_factory() as db:
        user = User(email="candidate@gmail.com", display_name="Role boundary", role=role)
        db.add(user)
        db.flush()
        if role == Role.CANDIDATE:
            db.add(Candidate(user_id=user.id, full_name="Candidate", roll_number="BOUNDARY-104"))
        db.commit()
    signed = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    headers = {**login_headers, "X-CSRF-Token": signed.json()["csrf_token"]}
    checked = 0
    for template, operations in application.openapi()["paths"].items():
        forbidden = (
            (template.startswith("/api/admin/") and role != Role.ADMIN)
            or (template.startswith("/api/grading/") and role not in {Role.ADMIN, Role.EXAMINER})
            or (template.startswith("/api/proctor/") and role not in {Role.ADMIN, Role.PROCTOR})
            or (template.startswith("/api/candidate/") and role != Role.CANDIDATE)
        )
        if not forbidden:
            # Correct roles still need both Origin and CSRF on every mutation.
            for method in operations:
                if method not in {"post", "put", "delete"} or not template.startswith(
                    ("/api/admin/", "/api/grading/", "/api/candidate/")
                ):
                    continue
                path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), template)
                for invalid_headers in [
                    login_headers,
                    {**headers, "X-CSRF-Token": "wrong"},
                    {**headers, "Origin": "https://untrusted.example"},
                    {"X-CSRF-Token": signed.json()["csrf_token"]},
                ]:
                    response = client.request(
                        method,
                        path,
                        headers=invalid_headers,
                        json={} if method != "delete" else None,
                    )
                    assert response.status_code == 403, (role, method, path, response.text)
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), template)
        for method in operations:
            if method not in {"get", "post", "put", "delete"}:
                continue
            response = client.request(
                method, path, headers=headers, json={} if method in {"post", "put"} else None
            )
            assert response.status_code == 403, (role, method, path, response.text)
            checked += 1
    assert checked >= 10


def test_auth_cleanup_is_bounded_and_preserves_current_session_and_history(
    client: TestClient,
    approved_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    signed = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    assert signed.status_code == 200
    with db_factory() as db:
        user = User(email="expired@gmail.com", display_name="Expired", role=Role.ADMIN)
        db.add(user)
        db.flush()
        db.add(
            AuthSession(
                user_id=user.id,
                token_hash=token_hash("expired"),
                csrf_token="expired",
                expires_at=utc_now() - timedelta(seconds=10),
            )
        )
        for number in range(2):
            db.add(
                LoginThrottle(
                    key=token_hash(str(number)),
                    attempts=1,
                    expires_at=utc_now() - timedelta(seconds=10),
                )
            )
        db.commit()
        assert prune_expired_auth(db, 1) == (1, 1)
        assert prune_expired_auth(db, 1) == (0, 1)
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        assert db.scalar(select(func.count()).select_from(SecurityEvent)) == 1
    assert client.get("/api/me").status_code == 200


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL trigger enforcement"
)
def test_database_rejects_bulk_changes_and_truncation_of_histories(db_engine: Engine) -> None:
    histories = ("audit_events", "session_events", "grading_records", "security_events")
    for table in histories:
        for statement in [
            f"UPDATE {table} SET id = id",
            f"DELETE FROM {table}",
            f"TRUNCATE {table}",
        ]:
            with db_engine.connect() as connection:
                with pytest.raises(DBAPIError) as error:
                    connection.execute(text(statement))
                assert getattr(error.value.orig, "sqlstate", None) == "42501"
                connection.rollback()


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL login row locks")
def test_concurrent_successful_logins_leave_one_session(
    approved_user: User,
    db_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    with db_factory() as db:
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == approved_user.id))
        candidate.father_name = "Test Father"
        db.commit()

    def sign_in(_: int) -> str:
        with db_factory() as db:
            _, token = candidate_login(
                db,
                CandidateLoginRequest(
                    roll_number="CCK-104", full_name="Test Candidate", father_name="Test Father"
                ),
                settings,
                "same-exam-centre",
            )
            return token

    with ThreadPoolExecutor(max_workers=6) as executor:
        tokens = list(executor.map(sign_in, range(6)))
    assert len(set(tokens)) == 6
    with db_factory() as db:
        sessions = list(db.scalars(select(AuthSession)))
        assert len(sessions) == 1
        assert sessions[0].token_hash in {token_hash(token) for token in tokens}
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.event_type == "LOGIN_SUCCESS")
            )
            == 6
        )


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL runtime privileges")
def test_runtime_role_can_append_but_cannot_erase_history_or_change_schema(
    db_engine: Engine,
) -> None:
    role = "cck_test_runtime_" + uuid.uuid4().hex
    with db_engine.begin() as db:
        if not db.scalar(
            text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
        ):
            pytest.skip("TEST_DATABASE_URL role cannot provision an isolated test role")
        schema = db.scalar(text("SELECT current_schema()"))
        db.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOINHERIT'))
    try:
        grants = (
            Path("ops/grant-runtime.psql")
            .read_text()
            .replace(':"schema_name"', f'"{schema}"')
            .replace(':"runtime_role"', f'"{role}"')
        )
        with db_engine.begin() as db:
            db.exec_driver_sql(grants)
            db.execute(text(f'SET LOCAL ROLE "{role}"'))
            db.execute(
                SecurityEvent.__table__.insert().values(
                    id=uuid.uuid4(), event_type="LOGIN_FAILURE", method="GOOGLE"
                )
            )
            assert db.scalar(select(func.count()).select_from(SecurityEvent)) == 1
        for statement in [
            "DELETE FROM security_events",
            "UPDATE grading_records SET id = id",
            "TRUNCATE session_events",
            "DELETE FROM alembic_version",
            "DROP FUNCTION cck_reject_history_change() CASCADE",
            "CREATE TABLE forbidden (id integer)",
        ]:
            with db_engine.connect() as db:
                db.execute(text(f'SET LOCAL ROLE "{role}"'))
                with pytest.raises(DBAPIError) as error:
                    db.execute(text(statement))
                assert getattr(error.value.orig, "sqlstate", None) == "42501"
                db.rollback()
    finally:
        with db_engine.begin() as db:
            db.execute(text(f'DROP OWNED BY "{role}"'))
            db.execute(text(f'DROP ROLE "{role}"'))
