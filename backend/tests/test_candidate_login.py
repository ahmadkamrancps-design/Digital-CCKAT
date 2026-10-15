import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.core.security import token_hash, utc_now
from app.models import AuthSession, Candidate, CandidateStatus, LoginThrottle, Role, User

DETAILS = {"roll_number": "CCK-104", "full_name": "Test Candidate", "father_name": "Test Father"}


@pytest.fixture
def admissions_user(approved_user: User, db_factory: sessionmaker[Session]) -> User:
    with db_factory() as db:
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == approved_user.id))
        assert candidate is not None
        candidate.father_name = "Test Father"
        user = db.get(User, approved_user.id)
        assert user is not None
        user.email = None
        db.commit()
    return approved_user


def test_admissions_login_cookie_refresh_logout(
    client: TestClient,
    admissions_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    response = client.post("/api/auth/candidate", json=DETAILS, headers=login_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["candidate"]["roll_number"] == "CCK-104"
    assert data["user"]["email"] is None
    assert data["user"]["role"] == "CANDIDATE"
    assert "father_name" not in data["candidate"]  # Never echo login verification details.
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api" in cookie
    token = client.cookies.get("cck_session")
    assert token and token not in response.text
    with db_factory() as db:
        assert db.scalar(select(AuthSession.token_hash)) == token_hash(token)
        assert db.get(User, admissions_user.id).google_subject is None
    with TestClient(client.app) as refreshed:
        refreshed.cookies.set("cck_session", token)
        assert refreshed.get("/api/me").json() == data
        assert refreshed.get("/api/candidate/me").status_code == 200
        assert refreshed.get("/api/admin/candidates").status_code == 403
        assert refreshed.get("/api/proctor/exams").status_code == 403
    assert client.post("/api/auth/logout", headers=login_headers).status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={**login_headers, "X-CSRF-Token": data["csrf_token"]}
        ).status_code
        == 204
    )
    client.cookies.set("cck_session", token)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"roll_number": "unknown"},
        {"full_name": "Test"},
        {"full_name": "Wrong Candidate"},
        {"father_name": "Wrong Father"},
    ],
)
def test_invalid_details_never_issue_session_or_echo_record(
    client: TestClient,
    admissions_user: User,
    login_headers: dict[str, str],
    overrides: dict[str, str],
) -> None:
    response = client.post(
        "/api/auth/candidate", json={**DETAILS, **overrides}, headers=login_headers
    )
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Unable to sign in. Check your admissions details or contact admissions."
    }
    assert "cck_session" not in client.cookies


def test_unknown_identity_never_registers(
    client: TestClient, login_headers: dict[str, str], db_factory: sessionmaker[Session]
) -> None:
    assert (
        client.post("/api/auth/candidate", json=DETAILS, headers=login_headers).status_code == 401
    )
    with db_factory() as db:
        assert db.scalar(select(User)) is None
        assert db.scalar(select(Candidate)) is None
        assert db.scalar(select(AuthSession)) is None


@pytest.mark.parametrize(
    "state", ["disabled", "inactive", "legacy", "ADMIN", "PROCTOR", "EXAMINER"]
)
def test_ineligible_and_staff_records_cannot_use_admissions_login(
    client: TestClient,
    admissions_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    state: str,
) -> None:
    with db_factory() as db:
        user = db.get(User, admissions_user.id)
        candidate = db.scalar(select(Candidate))
        if state == "disabled":
            candidate.status = CandidateStatus.DISABLED
        elif state == "inactive":
            user.is_active = False
        elif state == "legacy":
            candidate.father_name = None
        else:
            user.role = Role(state)
        db.commit()
    response = client.post("/api/auth/candidate", json=DETAILS, headers=login_headers)
    assert response.status_code == 401
    assert "cck_session" not in client.cookies


def test_case_whitespace_and_unicode_normalization(
    client: TestClient,
    admissions_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    normalized = {
        "roll_number": " cck-104 ",
        "full_name": " TEST   CANDIDATE ",
        "father_name": "Ｔｅｓｔ Father",
    }
    assert (
        client.post("/api/auth/candidate", json=normalized, headers=login_headers).status_code
        == 200
    )
    with db_factory() as db:
        candidate = db.scalar(select(Candidate))
        candidate.full_name, candidate.father_name = "محمد احمد", "محمد کامران"
        db.commit()
    urdu = {**DETAILS, "full_name": " محمد  احمد ", "father_name": "محمد کامران"}
    assert client.post("/api/auth/candidate", json=urdu, headers=login_headers).status_code == 200


@pytest.mark.parametrize("origin", [None, "http://evil.example"])
def test_login_requires_trusted_origin(client: TestClient, origin: str | None) -> None:
    response = client.post(
        "/api/auth/candidate", json=DETAILS, headers={"Origin": origin} if origin else {}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("value", [None, "", "   ", "x" * 201])
def test_invalid_fields_and_extra_privileges_rejected(
    client: TestClient, login_headers: dict[str, str], value: str | None
) -> None:
    response = client.post(
        "/api/auth/candidate", json={**DETAILS, "father_name": value}, headers=login_headers
    )
    assert response.status_code == 422
    assert "Test Candidate" not in response.text
    assert (
        client.post(
            "/api/auth/candidate", json={**DETAILS, "role": "ADMIN"}, headers=login_headers
        ).status_code
        == 422
    )


def test_login_rotates_session_and_eligibility_rechecked(
    client: TestClient,
    admissions_user: User,
    login_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    assert (
        client.post("/api/auth/candidate", json=DETAILS, headers=login_headers).status_code == 200
    )
    original = client.cookies.get("cck_session")
    assert (
        client.post("/api/auth/candidate", json=DETAILS, headers=login_headers).status_code == 200
    )
    current = client.cookies.get("cck_session")
    assert original != current
    client.cookies.clear()
    client.cookies.set("cck_session", original)
    assert client.get("/api/me").status_code == 401
    client.cookies.clear()
    client.cookies.set("cck_session", current)
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        db.scalar(select(Candidate)).status = CandidateStatus.DISABLED
        db.commit()
    assert client.get("/api/me").status_code == 403


def test_persistent_roll_throttle_cannot_be_bypassed_by_new_client_or_case(
    client: TestClient,
    application: FastAPI,
    admissions_user: User,
    login_headers: dict[str, str],
    settings: Settings,
    db_factory: sessionmaker[Session],
) -> None:
    settings.candidate_login_roll_limit = 2
    wrong = {**DETAILS, "father_name": "Incorrect"}
    for _ in range(2):
        assert (
            client.post("/api/auth/candidate", json=wrong, headers=login_headers).status_code == 401
        )
    with TestClient(application) as other:
        response = other.post(
            "/api/auth/candidate",
            json={**DETAILS, "roll_number": " cck-104 "},
            headers=login_headers,
        )
        assert response.status_code == 429
        assert 1 <= int(response.headers["retry-after"]) <= 900
    with db_factory() as db:
        rows = db.scalars(select(LoginThrottle)).all()
        assert len(rows) == 2
        assert all(len(row.key) == 64 for row in rows)
        for row in rows:
            row.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
    assert (
        client.post("/api/auth/candidate", json=DETAILS, headers=login_headers).status_code == 200
    )


def test_ip_throttle_limits_changing_unknown_rolls(
    client: TestClient, login_headers: dict[str, str], settings: Settings
) -> None:
    settings.candidate_login_ip_limit = 2
    for roll in ["one", "two"]:
        assert (
            client.post(
                "/api/auth/candidate", json={**DETAILS, "roll_number": roll}, headers=login_headers
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/candidate", json={**DETAILS, "roll_number": "three"}, headers=login_headers
        ).status_code
        == 429
    )


def test_database_rejects_ambiguous_rolls_and_allows_email_less_candidates(
    admissions_user: User, db_factory: sessionmaker[Session]
) -> None:
    with db_factory() as db:
        user = User(display_name="Other", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        db.add(
            Candidate(
                user_id=user.id, roll_number=" cck-104 ", full_name="Other", father_name="Father"
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="Real PostgreSQL upsert concurrency"
)
@pytest.mark.parametrize("expired_window", [False, True])
def test_parallel_signin_requests_share_atomic_throttle(
    db_factory: sessionmaker[Session], settings: Settings, expired_window: bool
) -> None:
    from fastapi import HTTPException

    from app.schemas.auth import CandidateLoginRequest
    from app.services.candidate_login_service import candidate_login

    settings.candidate_login_roll_limit = 2

    def attempt(_: int) -> int:
        with db_factory() as db:
            try:
                candidate_login(db, CandidateLoginRequest(**DETAILS), settings, "same-client")
            except HTTPException as error:
                return error.status_code
            raise AssertionError("Unknown candidate was authorized")

    if expired_window:
        assert attempt(0) == 401
        with db_factory() as db:
            for bucket in db.scalars(select(LoginThrottle)):
                bucket.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()

    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(executor.map(attempt, range(6)))
    assert sorted(responses) == [401, 401, 429, 429, 429, 429]
    with db_factory() as db:
        # Counts saturate at limit + 2 to avoid overflow and repeated denial events.
        assert sorted(db.scalars(select(LoginThrottle.attempts))) == [4, 6]
