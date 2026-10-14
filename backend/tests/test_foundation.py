import os

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.config import Settings, load_settings
from app.models import Exam, Role, User


def test_liveness_and_readiness(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/health/ready").json() == {"status": "ready"}


def test_untrusted_host_denied(client: TestClient) -> None:
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_cors_rejects_foreign_origin(client: TestClient) -> None:
    response = client.options(
        "/api/auth/google",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_production_config_requires_security_settings() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    settings = Settings(
        _env_file=None,
        environment="production",
        session_cookie_secure=True,
        google_client_id="test.apps.googleusercontent.com",
        frontend_origin="https://test.cck.example",
        database_url="postgresql+psycopg://cck:separate-password@db/cck",
        allowed_hosts=["test.cck.example"],
    )
    assert settings.session_cookie_secure


def test_startup_config_failure_does_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:SECRET_DATABASE_PASSWORD@db/cck")
    monkeypatch.setenv("FRONTEND_ORIGIN", "invalid-origin")
    with pytest.raises(RuntimeError) as failure:
        load_settings()
    assert "SECRET_DATABASE_PASSWORD" not in str(failure.value)


@pytest.mark.parametrize("origin", ["*", "http://localhost:5173/", "http://localhost:5173/path"])
def test_origins_must_be_exact(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, frontend_origin=origin)


def test_database_email_uniqueness(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        db.add(User(email="same@gmail.com", display_name="First", role=Role.CANDIDATE))
        db.commit()
        db.add(User(email="same@gmail.com", display_name="Second", role=Role.CANDIDATE))
        with pytest.raises(IntegrityError):
            db.commit()


def test_database_email_normalization_constraint(db_factory: sessionmaker[Session]) -> None:
    with db_factory() as db:
        db.add(User(email="UPPER@gmail.com", display_name="Candidate", role=Role.CANDIDATE))
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not supplied"
)
def test_postgres_migration_roundtrip_and_model_match(db_engine: Engine) -> None:
    config = Config("alembic.ini")
    command.check(config)
    with Session(db_engine) as db:
        exam = Exam(title="Preserved domain exam")
        db.add(exam)
        db.commit()
        exam_id = exam.id
    command.downgrade(config, "0003_attempt_engine")
    assert "audit_events" not in inspect(db_engine).get_table_names()
    assert "is_published" not in {
        column["name"] for column in inspect(db_engine).get_columns("exams")
    }
    with Session(db_engine) as db:
        assert db.scalar(select(Exam.title).where(Exam.id == exam_id)) == "Preserved domain exam"
    command.upgrade(config, "head")
    command.check(config)
    with Session(db_engine) as db:
        assert db.get(Exam, exam_id).is_published is True
    command.downgrade(config, "0002_exam_domain")
    assert not {"candidate_exam_assignments", "exam_attempts", "subject_attempts", "answers"} & set(
        inspect(db_engine).get_table_names()
    )
    with Session(db_engine) as db:
        assert db.scalar(select(Exam.title).where(Exam.id == exam_id)) == "Preserved domain exam"
    command.upgrade(config, "head")
    command.check(config)
    assert {
        "users",
        "candidates",
        "auth_sessions",
        "exams",
        "subjects",
        "exam_subjects",
        "questions",
        "question_options",
        "accepted_answers",
        "exam_questions",
        "candidate_exam_assignments",
        "exam_attempts",
        "subject_attempts",
        "answers",
        "audit_events",
    } <= set(inspect(db_engine).get_table_names())
    with Session(db_engine) as db:
        user = User(email="migration@gmail.com", display_name="Preserved admin", role=Role.ADMIN)
        db.add(user)
        db.commit()
        user_id = user.id
    command.downgrade(config, "0001_auth_foundation")
    assert set(inspect(db_engine).get_table_names()) == {
        "users",
        "candidates",
        "auth_sessions",
        "alembic_version",
    }
    with Session(db_engine) as db:
        assert db.get(User, user_id) is not None
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    assert set(inspect(db_engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    command.check(config)
