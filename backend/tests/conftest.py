import os
import sqlite3
import uuid
from collections.abc import Iterator

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from alembic import command
from app.config import Settings
from app.db.base import Base
from app.db.session import create_session_factory
from app.main import create_app
from app.models import Candidate, Role, User
from app.services.google_identity import GoogleIdentity, InvalidGoogleCredential


class FakeIdentityVerifier:
    """Test-only dependency injection. No fake authentication endpoint exists in the app."""

    identity = GoogleIdentity("google-sub-104", "candidate@gmail.com", True)

    def verify(self, credential: str) -> GoogleIdentity:
        if credential != "test-valid-credential":
            raise InvalidGoogleCredential
        return self.identity


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        allowed_hosts=["testserver", "localhost"],
        google_client_id="test-client.apps.googleusercontent.com",
    )


@pytest.fixture
def db_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        # Isolate every test in a random schema; never drop or modify public tables.
        schema = "cck_test_" + uuid.uuid4().hex
        admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
        with admin.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
        monkeypatch.setenv("DATABASE_URL", schema_url.render_as_string(hide_password=False))
        engine = create_engine(schema_url, hide_parameters=True)
        try:
            command.upgrade(Config("alembic.ini"), "head")
            yield engine
        finally:
            engine.dispose()
            with admin.connect() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(
            connection: sqlite3.Connection, record: ConnectionPoolEntry
        ) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)  # Unit tests only; app startup never creates tables.
        yield engine
        engine.dispose()


@pytest.fixture
def db_factory(db_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(db_engine)


@pytest.fixture
def verifier() -> FakeIdentityVerifier:
    return FakeIdentityVerifier()


@pytest.fixture
def application(
    settings: Settings,
    db_factory: sessionmaker[Session],
    verifier: FakeIdentityVerifier,
) -> FastAPI:
    app = create_app(settings)
    app.state.session_factory = db_factory
    app.state.identity_verifier = verifier
    return app


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application, raise_server_exceptions=False) as value:
        yield value


@pytest.fixture
def approved_user(db_factory: sessionmaker[Session]) -> User:
    with db_factory() as db:
        user = User(email="candidate@gmail.com", display_name="Test Candidate", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        db.add(Candidate(user_id=user.id, full_name="Test Candidate", roll_number="CCK-104"))
        db.commit()
        return user


@pytest.fixture
def login_headers(settings: Settings) -> dict[str, str]:
    return {"Origin": settings.frontend_origin}
