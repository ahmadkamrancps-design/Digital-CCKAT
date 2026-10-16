import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, local

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, load_settings
from app.core.security import utc_now
from app.db.session import create_db_engine
from app.models import (
    Candidate,
    ExamQuestion,
    ExamSubject,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    User,
    WorkerHeartbeat,
)
from app.services import attempt_service
from app.services.operations_service import check_readiness, migration_head, record_worker_success
from tests.test_attempts import Scenario, TestClock
from tests.test_attempts import clock as clock
from tests.test_attempts import scenario as scenario


def test_secret_file_configuration_and_conflicting_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    secret = tmp_path / "database_url"
    secret.write_text("postgresql+psycopg://cck:PRIVATE_DATABASE_PASSWORD@db/cck\n")
    settings = Settings(_env_file=None, database_url_file=secret)
    assert "PRIVATE_DATABASE_PASSWORD" not in repr(settings)
    assert settings.database_url.endswith("@db/cck")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url_file=secret,
            database_url="postgresql+psycopg://cck:x@db/cck",
        )
    monkeypatch.setenv("DATABASE_URL_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError) as failure:
        load_settings()
    assert "PRIVATE" not in str(failure.value)


def test_readiness_tracks_worker_success_and_staleness(
    client: TestClient,
    settings: Settings,
    db_factory: sessionmaker[Session],
) -> None:
    settings.require_expiry_worker = True
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/ready").status_code == 503
    with db_factory() as db:
        record_worker_success(db, 7)
    assert client.get("/api/health/ready").status_code == 200
    with db_factory() as db:
        row = db.get(WorkerHeartbeat, "expiry")
        row.last_success_at = utc_now() - timedelta(seconds=60)
        db.commit()
    assert client.get("/api/health/ready").status_code == 503
    assert client.get("/api/health").status_code == 200


@pytest.fixture
def capacity_case(
    scenario: Scenario, db_factory: sessionmaker[Session]
) -> tuple[Scenario, Candidate]:
    with db_factory() as db:
        attempt_service.authorize_start(db, scenario.exam_id, False)
        for paper in db.scalars(select(ExamSubject).where(ExamSubject.exam_id == scenario.exam_id)):
            for sequence in range(3, 31):
                question = Question(
                    subject_id=paper.subject_id,
                    type=QuestionType.MCQ,
                    prompt=f"Capacity question {sequence}",
                    marks=1,
                )
                db.add(question)
                db.flush()
                db.add_all(
                    [
                        QuestionOption(
                            question_id=question.id,
                            option_text="A",
                            display_order=1,
                            is_correct=True,
                        ),
                        QuestionOption(
                            question_id=question.id,
                            option_text="B",
                            display_order=2,
                            is_correct=False,
                        ),
                        ExamQuestion(
                            exam_subject_id=paper.id,
                            subject_id=paper.subject_id,
                            question_id=question.id,
                            sequence=sequence,
                        ),
                    ]
                )
        user = User(display_name="Second Candidate", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        candidate = Candidate(
            user_id=user.id, full_name=user.display_name, roll_number="CAPACITY-SECOND"
        )
        db.add(candidate)
        db.commit()
        attempt_service.assign_candidate(
            db, scenario.exam_id, candidate.id, scenario.admin_id, True
        )
        attempt_service.authorize_start(db, scenario.exam_id, True)
        return scenario, candidate


def test_first_attempt_query_count_is_bounded_by_subjects_not_questions(
    capacity_case: tuple[Scenario, Candidate],
    clock: TestClock,
    db_factory: sessionmaker[Session],
    db_engine: Engine,
) -> None:
    case, _ = capacity_case
    statements: list[str] = []

    def record(connection, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", record)
    try:
        with db_factory() as db:
            attempt = attempt_service.begin_exam(db, case.exam_id, case.candidate_id, clock)
            assert len(attempt.subjects) == 2
        assert len(statements) <= 25
        assert not any(
            "question_options" in statement or "accepted_answers" in statement
            for statement in statements
        )
    finally:
        event.remove(db_engine, "before_cursor_execute", record)


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL shared configuration locks"
)
def test_distinct_candidates_can_enter_frozen_exam_concurrently(
    capacity_case: tuple[Scenario, Candidate],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    case, second = capacity_case
    barrier = Barrier(2)
    seen = local()

    class ConcurrentClock:
        def now(self, db: Session):
            if not getattr(seen, "entered", False):
                seen.entered = True
                barrier.wait(timeout=10)
            return clock.value

    def start(candidate_id):
        with db_factory() as db:
            return attempt_service.begin_exam(db, case.exam_id, candidate_id, ConcurrentClock()).id

    with ThreadPoolExecutor(max_workers=2) as workers:
        attempts = list(workers.map(start, [case.candidate_id, second.id]))
    assert len(set(attempts)) == 2
    with db_factory() as db:
        attempt_service.authorize_start(db, case.exam_id, False)
        # Pausing still blocks any next subject; shared locks do not bypass control.
        with pytest.raises(HTTPException) as failure:
            first = attempt_service.resume_exam(db, attempts[0], case.candidate_id, clock)
            attempt_service.begin_subject(
                db, first.id, first.subjects[0].id, case.candidate_id, clock
            )
        assert failure.value.status_code == 403


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL runtime options")
def test_readiness_requires_current_schema_and_connection_limits_preserve_search_path(
    db_engine: Engine,
    settings: Settings,
) -> None:
    configured = Settings(
        _env_file=None,
        database_url=db_engine.url.render_as_string(hide_password=False),
        database_pool_size=1,
        database_max_overflow=0,
        database_statement_timeout_ms=12345,
        database_lock_timeout_ms=2345,
    )
    engine = create_db_engine(configured)
    try:
        with Session(engine) as db:
            assert db.scalar(text("SHOW statement_timeout")) == "12345ms"
            assert db.scalar(text("SHOW lock_timeout")) == "2345ms"
            assert db.scalar(text("SELECT current_schema()")).startswith("cck_test_")
            check_readiness(db, settings, migration_head())
            with pytest.raises(HTTPException) as failure:
                check_readiness(db, settings, "outdated-schema")
            assert failure.value.status_code == 503
        assert engine.pool.size() == 1
    finally:
        engine.dispose()
