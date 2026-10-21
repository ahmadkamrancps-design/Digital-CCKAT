import importlib.util
import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.models import AuthSession, Role, User

specification = importlib.util.spec_from_file_location(
    "management_sandbox", Path(__file__).resolve().parents[2] / "ops/management_sandbox.py"
)
assert specification is not None and specification.loader is not None
sandbox = importlib.util.module_from_spec(specification)
specification.loader.exec_module(sandbox)
DATABASE_NAME = "cck_management_012345abcdef_rehearsal"


def configuration(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "development",
        "database_url": f"postgresql+psycopg://local:local@localhost/{DATABASE_NAME}",
        "frontend_origin": "http://localhost:5175",
        "session_cookie_name": sandbox.COOKIE_NAME,
        "session_ttl_seconds": 7200,
    }
    return Settings(**{**values, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "test"},
        {
            "environment": "production",
            "frontend_origin": "https://digital.cckat.edu.pk",
            "session_cookie_secure": True,
        },
        {"database_url": "postgresql+psycopg://local:local@localhost/cck_digital_test"},
        {"database_url": f"postgresql+psycopg://local:local@external.example/{DATABASE_NAME}"},
        {"frontend_origin": "https://digital.cckat.edu.pk"},
        {"session_cookie_name": "cck_session"},
        {"session_cookie_secure": True},
    ],
)
def test_sandbox_factory_rejects_regular_or_nonlocal_configuration(overrides) -> None:
    with pytest.raises(ValueError, match="isolated localhost"):
        sandbox.create_sandbox_app(configuration(**overrides), uuid4())


def test_regular_application_has_no_management_entry(client: TestClient) -> None:
    assert client.get(sandbox.ENTRY_PATH).status_code == 404
    assert client.post(sandbox.ENTRY_PATH).status_code == 404


def nonce_from(response) -> str:
    match = re.search('name="nonce" value="([A-Za-z0-9_-]+)"', response.text)
    assert match is not None
    return match.group(1)


def test_local_entry_issues_real_admin_session_and_enforces_csrf(db_factory, monkeypatch) -> None:
    with db_factory() as db:
        user = User(display_name="Local Test Administrator", role=Role.ADMIN)
        db.add(user)
        db.commit()
        administrator_id = user.id
    app = sandbox.create_sandbox_app(configuration(), administrator_id)
    app.state.session_factory = db_factory
    # Common test fixtures use SQLite or a random PostgreSQL schema, not a sandbox DB.
    monkeypatch.setattr(sandbox, "sandbox_database_name", lambda _: DATABASE_NAME)
    with TestClient(app, base_url="http://localhost:5175", client=("127.0.0.1", 1234)) as browser:
        assert browser.get("/api/admin/overview").status_code == 401
        landing = browser.get(sandbox.ENTRY_PATH)
        assert landing.status_code == 200 and "separate test database" in landing.text
        assert "no-store" in landing.headers["cache-control"]
        data = {"nonce": nonce_from(landing)}
        assert browser.post(sandbox.ENTRY_PATH, json=data).status_code == 403
        assert (
            browser.post(
                sandbox.ENTRY_PATH, json=data, headers={"Origin": "http://other.example"}
            ).status_code
            == 403
        )
        headers = {"Origin": "http://localhost:5175"}
        assert (
            browser.post(sandbox.ENTRY_PATH, json={"nonce": "wrong"}, headers=headers).status_code
            == 403
        )
        signed = browser.post(
            sandbox.ENTRY_PATH, json=data, headers=headers, follow_redirects=False
        )
        assert signed.status_code == 204
        cookie = signed.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Path=/api" in cookie and "SameSite=lax" in cookie
        assert cookie.startswith(sandbox.COOKIE_NAME + "=")
        profile = browser.get("/api/me").json()
        assert profile["user"]["role"] == "ADMIN"
        assert browser.get("/api/admin/overview").status_code == 200
        body = {"name": "Local management subject", "code": "LOCAL"}
        assert browser.post("/api/admin/subjects", json=body, headers=headers).status_code == 403
        saved = browser.post(
            "/api/admin/subjects",
            json=body,
            headers={**headers, "X-CSRF-Token": profile["csrf_token"]},
        )
        assert saved.status_code == 201
        assert browser.get("/api/admin/subjects").json()[0]["name"] == body["name"]
        with db_factory() as db:
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_entry_refuses_wrong_database_unapproved_staff_and_remote_clients(
    db_factory, monkeypatch
) -> None:
    with db_factory() as db:
        user = User(display_name="Candidate", role=Role.CANDIDATE)
        db.add(user)
        db.commit()
        user_id = user.id
    app = sandbox.create_sandbox_app(configuration(), user_id)
    app.state.session_factory = db_factory
    monkeypatch.setattr(sandbox, "sandbox_database_name", lambda _: "cck_production")
    with TestClient(app, base_url="http://localhost:5175", client=("127.0.0.1", 1234)) as browser:
        data = {"nonce": nonce_from(browser.get(sandbox.ENTRY_PATH))}
        headers = {"Origin": "http://localhost:5175"}
        assert browser.post(sandbox.ENTRY_PATH, json=data, headers=headers).status_code == 403
        monkeypatch.setattr(sandbox, "sandbox_database_name", lambda _: DATABASE_NAME)
        assert browser.post(sandbox.ENTRY_PATH, json=data, headers=headers).status_code == 403
    with TestClient(app, base_url="http://localhost:5175", client=("192.0.2.1", 1234)) as browser:
        assert browser.get(sandbox.ENTRY_PATH).status_code == 403
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
