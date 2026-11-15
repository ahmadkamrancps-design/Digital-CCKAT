import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.railway import configure_environment, create_web_app, normalize_database_url


@pytest.fixture
def static_directory(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!doctype html><title>CCK production frontend</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("console.log('CCK');")
    (tmp_path / ".env").write_text("PRIVATE_VALUE=not-public")
    return tmp_path


@pytest.fixture
def railway_client(settings: Settings, static_directory: Path, db_factory):
    app = create_web_app(settings, static_directory)
    app.state.session_factory = db_factory
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/dashboard", "/admin", "/admin/exams/123", "/exam"])
def test_frontend_routes_survive_direct_navigation(railway_client, path):
    response = railway_client.get(path)
    assert response.status_code == 200
    assert "CCK production frontend" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "form-action 'self'" in response.headers["content-security-policy"]


def test_api_routes_keep_real_authentication_and_do_not_fall_back_to_html(railway_client):
    assert railway_client.get("/api/health").json() == {"status": "ok"}
    assert railway_client.get("/api/me").status_code == 401
    assert railway_client.get("/api/admin/questions").status_code == 401
    assert railway_client.get("/api/not-an-endpoint").status_code == 404
    assert railway_client.post("/api/local-management", json={}).status_code == 405


@pytest.mark.parametrize(
    "path",
    ["/.env", "/app/config.py", "/api/local-management", "/preview/admin", "/assets/missing.js"],
)
def test_no_source_secrets_preview_or_sandbox_routes(railway_client, path):
    response = railway_client.get(path)
    assert response.status_code == 404
    assert "PRIVATE_VALUE" not in response.text
    assert "CCK production frontend" not in response.text


def test_static_assets_and_host_boundary(railway_client):
    assert railway_client.get("/assets/app.js").status_code == 200
    assert railway_client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_missing_frontend_fails_closed(settings: Settings, tmp_path: Path):
    with pytest.raises(RuntimeError, match="Built frontend is missing"):
        create_web_app(settings, tmp_path)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_railway_url_selects_psycopg_without_losing_escaped_password(scheme):
    result = normalize_database_url(
        f"{scheme}://user:p%40ss%2Fword@postgres.railway.internal:5432/db?sslmode=require"
    )
    assert (
        result
        == "postgresql+psycopg://user:p%40ss%2Fword@postgres.railway.internal:5432/db?sslmode=require"
    )


@pytest.mark.parametrize("url", ["sqlite:///data.db", "not-a-url", "mysql://user:secret@db/db"])
def test_invalid_database_url_does_not_echo_secrets(url):
    with pytest.raises(ValueError, match="Invalid PostgreSQL configuration") as error:
        normalize_database_url(url)
    assert "secret" not in str(error.value)


def test_railway_requires_production_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/db")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    with pytest.raises(ValueError, match="requires ENVIRONMENT=production"):
        configure_environment()


def test_migration_uses_owner_secret_and_runtime_keeps_separate_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://cck_runtime:runtime-secret@db/db")
    monkeypatch.setenv("CCK_MIGRATION_DATABASE_URL", "postgresql://owner:owner-secret@db/db")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://cck.example")
    monkeypatch.setenv("ALLOWED_HOSTS", '["cck.example", "healthcheck.railway.app"]')
    monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
    configure_environment()
    assert "cck_runtime:runtime-secret" in os.environ["DATABASE_URL"]
    monkeypatch.setenv("CCK_MIGRATION_DATABASE_URL", "postgresql://owner:owner-secret@db/db")
    configure_environment(migration=True)
    assert "owner:owner-secret" in os.environ["DATABASE_URL"]
