import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Event
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AcceptedAnswer,
    Answer,
    Candidate,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamSubject,
    GradingMode,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    Subject,
    SubjectAttempt,
    SubjectStatus,
    User,
)
from app.schemas.attempt import AnswerWrite
from app.services import attempt_service as service
from app.services.google_identity import GoogleIdentity
from tests.conftest import FakeIdentityVerifier


class TestClock:
    __test__ = False

    def __init__(self) -> None:
        self.value = datetime(2026, 10, 15, 9, tzinfo=UTC)

    def now(self, db: Session) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass
class Scenario:
    exam_id: uuid.UUID
    candidate_id: uuid.UUID
    admin_id: uuid.UUID


@pytest.fixture
def clock(application: FastAPI) -> TestClock:
    value = TestClock()
    application.state.clock = value
    return value


@pytest.fixture
def scenario(db_factory: sessionmaker[Session], approved_user: User, clock: TestClock) -> Scenario:
    with db_factory() as db:
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == approved_user.id))
        assert candidate is not None
        admin = User(email="admin@gmail.com", display_name="Administrator", role=Role.ADMIN)
        exam = Exam(
            title="Authorized admission test",
            scheduled_start=clock.value,
            scheduled_end=clock.value + timedelta(hours=4),
        )
        db.add_all([admin, exam])
        db.flush()
        for index, name in enumerate(["English", "Urdu"]):
            subject = Subject(name=name, code=f"SUB{index}")
            db.add(subject)
            db.flush()
            paper = ExamSubject(
                exam_id=exam.id,
                subject_id=subject.id,
                duration_minutes=index + 1,
                sequence=index + 1,
            )
            mcq = Question(
                subject_id=subject.id,
                type=QuestionType.MCQ,
                prompt="Choose an option.",
                marks=Decimal(1),
            )
            short = Question(
                subject_id=subject.id,
                type=QuestionType.SHORT_ANSWER,
                prompt="مختصر جواب لکھیں۔" if index else "Write a short answer.",
                marks=Decimal(2),
                direction="rtl" if index else "ltr",
                language="ur" if index else "en",
                grading_mode=GradingMode.EXACT,
                grading_config={"mode": "EXACT"},
            )
            db.add_all([paper, mcq, short])
            db.flush()
            db.add_all(
                [
                    QuestionOption(
                        question_id=mcq.id,
                        option_text="Visible A",
                        display_order=1,
                        is_correct=True,
                    ),
                    QuestionOption(
                        question_id=mcq.id,
                        option_text="Visible B",
                        display_order=2,
                        is_correct=False,
                    ),
                    AcceptedAnswer(
                        question_id=short.id,
                        grading_mode="EXACT",
                        accepted_value="SECRET_ACCEPTED_VALUE",
                    ),
                    ExamQuestion(
                        exam_subject_id=paper.id,
                        subject_id=subject.id,
                        question_id=mcq.id,
                        sequence=1,
                    ),
                    ExamQuestion(
                        exam_subject_id=paper.id,
                        subject_id=subject.id,
                        question_id=short.id,
                        sequence=2,
                    ),
                ]
            )
        db.commit()
        service.assign_candidate(db, exam.id, candidate.id, admin.id, True)
        service.authorize_start(db, exam.id, True)
        return Scenario(exam.id, candidate.id, admin.id)


@pytest.fixture
def candidate_headers(
    client: TestClient, scenario: Scenario, login_headers: dict[str, str]
) -> dict[str, str]:
    result = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    assert result.status_code == 200
    return {**login_headers, "X-CSRF-Token": result.json()["csrf_token"]}


def begin(client: TestClient, scenario: Scenario, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(f"/api/candidate/exams/{scenario.exam_id}/attempt", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def subject_path(attempt: dict[str, Any], index: int = 0) -> str:
    return f"/api/candidate/attempts/{attempt['id']}/subjects/{attempt['subjects'][index]['id']}"


def started(
    client: TestClient, scenario: Scenario, headers: dict[str, str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempt = begin(client, scenario, headers)
    response = client.post(subject_path(attempt) + "/start", headers=headers)
    assert response.status_code == 200, response.text
    paper = client.get(subject_path(attempt) + "/questions")
    assert paper.status_code == 200, paper.text
    return response.json(), paper.json()["questions"]


def save_body(question: dict[str, Any], revision: int = 0, marked: bool = False) -> dict[str, Any]:
    return {
        "expected_revision": revision,
        "selected_option_id": question["options"][0]["id"] if question["type"] == "MCQ" else None,
        "short_answer_text": "حسین" if question["type"] == "SHORT_ANSWER" else None,
        "is_marked_for_review": marked,
    }


def test_assigned_exam_summaries_are_safe_ordered_and_do_not_start_an_attempt(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    response = client.get("/api/candidate/exams")
    assert response.status_code == 200
    exams = response.json()
    assert len(exams) == 1
    assert exams[0]["exam_id"] == str(scenario.exam_id)
    assert exams[0]["attempt_id"] is None
    subjects = exams[0]["subjects"]
    assert [(item["name"], item["duration_minutes"], item["sequence"]) for item in subjects] == [
        ("English", 1, 1),
        ("Urdu", 2, 2),
    ]
    assert all(
        set(item) == {"exam_subject_id", "name", "duration_minutes", "sequence"}
        for item in subjects
    )
    assert "SECRET_ACCEPTED_VALUE" not in response.text
    assert "Choose an option" not in response.text
    assert "is_correct" not in response.text
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(ExamAttempt)) == 0


def test_start_resume_refresh_and_relogin_never_reset_deadline(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
    db_factory: sessionmaker[Session],
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    deadline = attempt["subjects"][0]["expires_at"]
    assert client.get("/api/candidate/exams").json()[0]["attempt_id"] == attempt["id"]
    answer = client.put(
        subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
        headers=candidate_headers,
        json=save_body(questions[0], marked=True),
    )
    assert answer.status_code == 200
    clock.advance(20)
    resumed = begin(client, scenario, candidate_headers)
    assert resumed["id"] == attempt["id"]
    assert resumed["subjects"][0]["expires_at"] == deadline
    repeated = client.post(subject_path(attempt) + "/start", headers=candidate_headers)
    assert repeated.json()["subjects"][0]["expires_at"] == deadline
    raw_cookie = client.cookies.get("cck_session")
    with TestClient(client.app) as reopened:
        reopened.cookies.set("cck_session", raw_cookie)
        assert (
            reopened.get(f"/api/candidate/attempts/{attempt['id']}").json()["subjects"][0][
                "expires_at"
            ]
            == deadline
        )
        paper = reopened.get(subject_path(attempt) + "/questions").json()
        assert paper["questions"][0]["answer"]["is_marked_for_review"] is True
    logged = client.post(
        "/api/auth/google",
        headers={"Origin": candidate_headers["Origin"]},
        json={"credential": "test-valid-credential"},
    )
    relog_headers = {**candidate_headers, "X-CSRF-Token": logged.json()["csrf_token"]}
    assert begin(client, scenario, relog_headers)["subjects"][0]["expires_at"] == deadline
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(ExamAttempt)) == 1
        assert db.scalar(select(func.count()).select_from(Answer)) == 2


def test_ordered_subjects_final_submission_and_locked_answers(
    client: TestClient, scenario: Scenario, candidate_headers: dict[str, str], clock: TestClock
) -> None:
    attempt = begin(client, scenario, candidate_headers)
    assert (
        client.post(subject_path(attempt, 1) + "/start", headers=candidate_headers).status_code
        == 409
    )
    assert client.get(subject_path(attempt, 1) + "/questions").status_code == 409
    assert (
        client.post(subject_path(attempt, 1) + "/submit", headers=candidate_headers).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/candidate/attempts/{attempt['id']}/submit", headers=candidate_headers
        ).status_code
        == 409
    )
    attempt, questions = started(client, scenario, candidate_headers)
    clock.advance(10)
    submitted = client.post(subject_path(attempt) + "/submit", headers=candidate_headers).json()
    assert submitted["subjects"][0]["status"] == "SUBMITTED"
    submitted_at = submitted["subjects"][0]["submitted_at"]
    clock.advance(5)
    assert (
        client.post(subject_path(attempt) + "/submit", headers=candidate_headers).json()[
            "subjects"
        ][0]["submitted_at"]
        == submitted_at
    )
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
            headers=candidate_headers,
            json=save_body(questions[0]),
        ).status_code
        == 410
    )
    next_attempt = client.post(
        subject_path(attempt, 1) + "/start", headers=candidate_headers
    ).json()
    assert next_attempt["subjects"][1]["started_at"] == clock.value.isoformat().replace(
        "+00:00", "Z"
    )
    clock.advance(7)
    final = client.post(subject_path(attempt, 1) + "/submit", headers=candidate_headers).json()
    assert final["status"] == "SUBMITTED"
    clock.advance(50)
    receipt = client.post(
        f"/api/candidate/attempts/{attempt['id']}/submit", headers=candidate_headers
    ).json()
    assert receipt["submitted_at"] == final["submitted_at"]
    assert begin(client, scenario, candidate_headers)["id"] == attempt["id"]


def test_retry_no_duplicate_and_stale_write_conflict(
    client: TestClient, scenario: Scenario, candidate_headers: dict[str, str], clock: TestClock
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    path = subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}"
    body = save_body(questions[0])
    first = client.put(path, headers=candidate_headers, json=body)
    assert first.status_code == 200 and first.json()["answer"]["revision"] == 1
    clock.advance(1)
    retry = client.put(path, headers=candidate_headers, json=body)
    assert retry.json()["answer"] == first.json()["answer"]
    next_body = {**body, "expected_revision": 1, "is_marked_for_review": True}
    newer = client.put(path, headers=candidate_headers, json=next_body)
    assert newer.json()["answer"]["revision"] == 2
    stale = client.put(path, headers=candidate_headers, json=body)
    assert (
        stale.status_code == 409
        and stale.json()["detail"]["current_answer"] == newer.json()["answer"]
    )
    assert (
        client.put(
            path, headers=candidate_headers, json={**next_body, "expected_revision": 3}
        ).status_code
        == 409
    )
    cleared = client.put(
        path,
        headers=candidate_headers,
        json={**next_body, "expected_revision": 2, "selected_option_id": None},
    )
    assert cleared.json()["answer"]["is_marked_for_review"] is True
    assert cleared.json()["answer"]["selected_option_id"] is None


@pytest.mark.parametrize("elapsed,expected", [(59.999, 200), (60, 410), (61, 410)])
def test_deadline_boundary_rejects_late_offline_answer(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
    db_factory: sessionmaker[Session],
    elapsed: float,
    expected: int,
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    clock.advance(elapsed)
    result = client.put(
        subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
        headers=candidate_headers,
        json=save_body(questions[0]),
    )
    assert result.status_code == expected
    with db_factory() as db:
        subject = db.get(SubjectAttempt, uuid.UUID(attempt["subjects"][0]["id"]))
        assert subject is not None
        if expected == 410:
            assert (
                subject.status == SubjectStatus.EXPIRED
                and subject.submitted_at == subject.expires_at
            )
            assert (
                db.scalar(
                    select(Answer.revision).where(
                        Answer.exam_question_id == uuid.UUID(questions[0]["exam_question_id"])
                    )
                )
                == 0
            )


def test_worker_expires_without_browser_and_next_timer_is_independent(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
    db_factory: sessionmaker[Session],
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    clock.advance(60)
    with db_factory() as db:
        assert service.expire_due(db, clock) == 1
        assert service.expire_due(db, clock) == 0
    state = client.get(f"/api/candidate/attempts/{attempt['id']}").json()
    assert state["subjects"][0]["status"] == "EXPIRED"
    assert state["subjects"][1]["status"] == "NOT_STARTED"
    clock.advance(5)
    next_attempt = client.post(
        subject_path(attempt, 1) + "/start", headers=candidate_headers
    ).json()
    assert datetime.fromisoformat(
        next_attempt["subjects"][1]["expires_at"]
    ) - clock.value == timedelta(minutes=2)
    clock.advance(120)
    with db_factory() as db:
        assert service.expire_due(db, clock) == 1
    assert client.get(f"/api/candidate/attempts/{attempt['id']}").json()["status"] == "SUBMITTED"


def test_window_cutoff_closes_started_and_unstarted_subjects(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
    db_factory: sessionmaker[Session],
) -> None:
    # Operator fixture defines a shorter schedule before any attempts exist.
    with db_factory() as db:
        exam = db.get(Exam, scenario.exam_id)
        assert exam is not None
        exam.scheduled_end = clock.value + timedelta(seconds=20)
        db.commit()
    attempt, _ = started(client, scenario, candidate_headers)
    assert datetime.fromisoformat(attempt["subjects"][0]["expires_at"]) == clock.value + timedelta(
        seconds=20
    )
    clock.advance(20)
    with db_factory() as db:
        assert service.expire_due(db, clock) == 1
    result = client.get(f"/api/candidate/attempts/{attempt['id']}").json()
    assert result["status"] == "SUBMITTED"
    assert [item["status"] for item in result["subjects"]] == ["EXPIRED", "EXPIRED"]
    assert result["subjects"][1]["started_at"] is None
    assert client.get(subject_path(attempt, 1) + "/questions").status_code == 409


def test_candidate_paper_has_no_keys_and_preserves_unicode(
    client: TestClient, scenario: Scenario, candidate_headers: dict[str, str]
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    result = client.get(subject_path(attempt) + "/questions")
    for private in [
        "is_correct",
        "accepted_answers",
        "grading_mode",
        "grading",
        "SECRET_ACCEPTED_VALUE",
    ]:
        assert private not in result.text
    answer = client.put(
        subject_path(attempt) + f"/answers/{questions[1]['exam_question_id']}",
        headers=candidate_headers,
        json=save_body(questions[1], marked=True),
    )
    assert answer.json()["answer"]["short_answer_text"] == "حسین"
    restored = client.get(subject_path(attempt) + "/questions").json()
    assert restored["questions"][1]["answer"]["short_answer_text"] == "حسین"


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"short_answer_text": "wrong type"}, 422),
        ({"selected_option_id": str(uuid.uuid4())}, 422),
        ({"expected_revision": -1}, 422),
        ({"expected_revision": True}, 422),
        ({"is_marked_for_review": "false"}, 422),
        ({"client_time": "2099-01-01"}, 422),
    ],
)
def test_invalid_answers(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    change: dict[str, Any],
    expected: int,
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    response = client.put(
        subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
        headers=candidate_headers,
        json={**save_body(questions[0]), **change},
    )
    assert response.status_code == expected


def test_unassigned_revoked_and_other_candidate_access(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    with db_factory() as db:
        other = User(email="other@gmail.com", display_name="Other", role=Role.CANDIDATE)
        db.add(other)
        db.flush()
        candidate = Candidate(user_id=other.id, full_name="Other", roll_number="OTHER-105")
        db.add(candidate)
        other_exam = Exam(title="Unassigned")
        db.add(other_exam)
        db.commit()
        with pytest.raises(HTTPException) as failure:
            service.resume_exam(db, uuid.UUID(attempt["id"]), candidate.id, TestClock())
        assert failure.value.status_code == 404
        db.rollback()
        other_id = other_exam.id
    assert (
        client.post(
            f"/api/candidate/exams/{other_id}/attempt", headers=candidate_headers
        ).status_code
        == 403
    )
    with db_factory() as db:
        service.assign_candidate(
            db, scenario.exam_id, scenario.candidate_id, scenario.admin_id, False
        )
    assert client.get(f"/api/candidate/attempts/{attempt['id']}").status_code == 403
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
            headers=candidate_headers,
            json=save_body(questions[0]),
        ).status_code
        == 403
    )
    with db_factory() as db:
        service.assign_candidate(
            db, scenario.exam_id, scenario.candidate_id, scenario.admin_id, True
        )
    assert begin(client, scenario, candidate_headers)["id"] == attempt["id"]


def test_authorization_window_and_configuration_freeze(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
    db_factory: sessionmaker[Session],
) -> None:
    with db_factory() as db:
        service.authorize_start(db, scenario.exam_id, False)
    assert (
        client.post(
            f"/api/candidate/exams/{scenario.exam_id}/attempt", headers=candidate_headers
        ).status_code
        == 403
    )
    with db_factory() as db:
        service.authorize_start(db, scenario.exam_id, True)
    clock.advance(-1)
    assert (
        client.post(
            f"/api/candidate/exams/{scenario.exam_id}/attempt", headers=candidate_headers
        ).status_code
        == 409
    )
    clock.advance(1)
    attempt, questions = started(client, scenario, candidate_headers)
    with db_factory() as db:
        service.authorize_start(db, scenario.exam_id, False)
    # Revoking start authorization does not erase the live timer or stop saves.
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
            headers=candidate_headers,
            json=save_body(questions[0]),
        ).status_code
        == 200
    )
    client.post(subject_path(attempt) + "/submit", headers=candidate_headers)
    assert (
        client.post(subject_path(attempt, 1) + "/start", headers=candidate_headers).status_code
        == 403
    )
    with db_factory() as db:
        from app.services.exam_domain_service import draft_exam

        with pytest.raises(HTTPException) as failure:
            draft_exam(db, scenario.exam_id)
        assert failure.value.status_code == 409


def test_mutation_security_and_role_boundaries(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    verifier: FakeIdentityVerifier,
    login_headers: dict[str, str],
) -> None:
    attempt = begin(client, scenario, candidate_headers)
    assert client.post(subject_path(attempt) + "/start").status_code == 403
    assert (
        client.post(
            subject_path(attempt) + "/start",
            headers={**candidate_headers, "Origin": "https://foreign.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/admin/exams/{scenario.exam_id}/start-authorization",
            headers=candidate_headers,
            json={"authorized": True},
        ).status_code
        == 403
    )
    verifier.identity = GoogleIdentity("admin-sub", "admin@gmail.com", True)
    login = client.post(
        "/api/auth/google", headers=login_headers, json={"credential": "test-valid-credential"}
    )
    assert login.status_code == 200
    assert client.get("/api/candidate/exams").status_code == 403
    admin_headers = {**login_headers, "X-CSRF-Token": login.json()["csrf_token"]}
    assert (
        client.post(
            f"/api/admin/exams/{scenario.exam_id}/start-authorization",
            json={"authorized": False},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/admin/exams/{scenario.exam_id}/start-authorization", json={"authorized": True}
        ).status_code
        == 403
    )


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL row-lock test")
def test_concurrent_start_and_answer_writes(
    db_factory: sessionmaker[Session], scenario: Scenario, clock: TestClock
) -> None:
    def begin_one() -> str:
        with db_factory() as db:
            return str(service.begin_exam(db, scenario.exam_id, scenario.candidate_id, clock).id)

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(lambda _: begin_one(), range(4)))
    assert len(set(ids)) == 1
    with db_factory() as db:
        attempt = service.resume_exam(db, uuid.UUID(ids[0]), scenario.candidate_id, clock)
        subject_id = attempt.subjects[0].id

    def start_one() -> str:
        with db_factory() as db:
            result = service.begin_subject(db, attempt.id, subject_id, scenario.candidate_id, clock)
            return str(result.subjects[0].expires_at)

    with ThreadPoolExecutor(max_workers=4) as executor:
        deadlines = list(executor.map(lambda _: start_one(), range(4)))
    assert len(set(deadlines)) == 1
    with db_factory() as db:
        paper = service.subject_paper(db, attempt.id, subject_id, scenario.candidate_id, clock)
        question = paper.questions[0]

    def save_one(marked: bool) -> int:
        with db_factory() as db:
            try:
                service.save_answer(
                    db,
                    attempt.id,
                    subject_id,
                    question.exam_question_id,
                    scenario.candidate_id,
                    AnswerWrite(
                        expected_revision=0,
                        selected_option_id=question.options[0].id,
                        short_answer_text=None,
                        is_marked_for_review=marked,
                    ),
                    clock,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        codes = list(executor.map(save_one, [False, True]))
    assert sorted(codes) == [200, 409]
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(ExamAttempt)) == 1
        assert db.scalar(select(func.count()).select_from(Answer)) == 2
        assert (
            db.scalar(
                select(Answer.revision).where(Answer.exam_question_id == question.exam_question_id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "violation",
    [
        "duplicate_answer",
        "foreign_option",
        "second_active",
        "missing_deadline",
        "negative_revision",
        "wrong_shape",
        "duplicate_attempt",
    ],
)
def test_database_attempt_and_answer_constraints(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
    violation: str,
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    with db_factory() as db:
        answer = db.scalar(
            select(Answer).where(
                Answer.subject_attempt_id == uuid.UUID(attempt["subjects"][0]["id"]),
                Answer.question_type == "MCQ",
            )
        )
        assert answer is not None
        if violation == "duplicate_answer":
            db.add(
                Answer(
                    subject_attempt_id=answer.subject_attempt_id,
                    exam_subject_id=answer.exam_subject_id,
                    exam_question_id=answer.exam_question_id,
                    question_id=answer.question_id,
                    question_type="MCQ",
                )
            )
        elif violation == "foreign_option":
            answer.selected_option_id = db.scalar(
                select(QuestionOption.id).where(QuestionOption.question_id != answer.question_id)
            )
        elif violation in {"second_active", "missing_deadline"}:
            subject = db.get(
                SubjectAttempt,
                uuid.UUID(attempt["subjects"][1 if violation == "second_active" else 0]["id"]),
            )
            assert subject is not None
            subject.status, subject.started_at = SubjectStatus.ACTIVE, clock.value
            subject.expires_at = (
                clock.value + timedelta(minutes=1) if violation == "second_active" else None
            )
        elif violation == "duplicate_attempt":
            saved = db.get(ExamAttempt, uuid.UUID(attempt["id"]))
            assert saved is not None
            db.add(
                ExamAttempt(
                    assignment_id=saved.assignment_id,
                    candidate_id=saved.candidate_id,
                    exam_id=saved.exam_id,
                    started_at=clock.value,
                )
            )
        elif violation == "negative_revision":
            answer.revision = -1
        else:
            answer.short_answer_text = "An MCQ cannot have a short answer"
        with pytest.raises(IntegrityError):
            db.commit()


def test_configuration_and_ownership_guards(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    from app.schemas.exam_domain import ExamWrite, SubjectWrite
    from app.services.exam_domain_service import write_exam, write_subject

    with db_factory() as db:
        subject = db.scalar(
            select(Subject).join(ExamSubject).where(ExamSubject.exam_id == scenario.exam_id)
        )
        assert subject is not None
        with pytest.raises(HTTPException) as failed:
            write_subject(db, SubjectWrite(name="Changed", code=subject.code), subject.id)
        assert failed.value.status_code == 409
        db.rollback()
        with pytest.raises(HTTPException) as failed:
            write_exam(db, ExamWrite(title="Changed"), scenario.exam_id)
        assert failed.value.status_code == 409
        db.rollback()
        empty = Exam(title="Empty draft")
        db.add(empty)
        db.commit()
        with pytest.raises(HTTPException) as failed:
            service.authorize_start(db, empty.id, True)
        assert failed.value.status_code == 409
    attempt, questions = started(client, scenario, candidate_headers)
    bad_path = subject_path(attempt) + f"/answers/{uuid.uuid4()}"
    assert (
        client.put(bad_path, headers=candidate_headers, json=save_body(questions[0])).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/candidate/attempts/{attempt['id']}/subjects/{uuid.uuid4()}/start",
            headers=candidate_headers,
        ).status_code
        == 404
    )
    with db_factory() as db:
        foreign = db.scalar(
            select(QuestionOption.id).where(
                QuestionOption.question_id != uuid.UUID(questions[0]["question_id"])
            )
        )
    body = {**save_body(questions[0]), "selected_option_id": str(foreign)}
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
            headers=candidate_headers,
            json=body,
        ).status_code
        == 422
    )
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{questions[1]['exam_question_id']}",
            headers=candidate_headers,
            json=body,
        ).status_code
        == 422
    )


def test_unscheduled_authorized_exam_keeps_full_subject_duration(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    with db_factory() as db:
        exam = db.get(Exam, scenario.exam_id)
        assert exam is not None
        exam.scheduled_start = exam.scheduled_end = None
        db.commit()
    attempt, _ = started(client, scenario, candidate_headers)
    assert datetime.fromisoformat(attempt["subjects"][0]["expires_at"]) - clock.value == timedelta(
        minutes=1
    )


@pytest.mark.postgres
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL lock and worker test"
)
def test_waiting_save_rechecks_time_and_worker_skips_locked_attempt(
    db_factory: sessionmaker[Session], db_engine: Engine, scenario: Scenario, clock: TestClock
) -> None:
    with db_factory() as db:
        attempt = service.begin_exam(db, scenario.exam_id, scenario.candidate_id, clock)
        subject_id = attempt.subjects[0].id
        service.begin_subject(db, attempt.id, subject_id, scenario.candidate_id, clock)
        paper = service.subject_paper(db, attempt.id, subject_id, scenario.candidate_id, clock)
    question = paper.questions[0]
    waiting = Event()

    def before_execute(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if "FROM exam_attempts" in statement and "FOR UPDATE" in statement and not waiting.is_set():
            waiting.set()

    def save_waiting() -> int:
        with db_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '10s'"))
            try:
                service.save_answer(
                    db,
                    attempt.id,
                    subject_id,
                    question.exam_question_id,
                    scenario.candidate_id,
                    AnswerWrite(
                        expected_revision=0,
                        selected_option_id=question.options[0].id,
                        short_answer_text=None,
                        is_marked_for_review=False,
                    ),
                    clock,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=1) as executor:
        with db_factory() as locked:
            locked.get(ExamAttempt, attempt.id, with_for_update=True)
            event.listen(db_engine, "before_cursor_execute", before_execute)
            try:
                future = executor.submit(save_waiting)
                assert waiting.wait(5), "Save did not reach its row lock"
                clock.advance(60)
                with db_factory() as worker:
                    assert service.expire_due(worker, clock) == 0
            finally:
                event.remove(db_engine, "before_cursor_execute", before_execute)
                locked.commit()
        assert future.result(timeout=10) == 410
    with db_factory() as db:
        answer = db.scalar(
            select(Answer).where(
                Answer.subject_attempt_id == subject_id,
                Answer.exam_question_id == question.exam_question_id,
            )
        )
        assert answer is not None and answer.revision == 0
        assert db.get(SubjectAttempt, subject_id).status == SubjectStatus.EXPIRED


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Actual PostgreSQL clock")
def test_database_clock_is_not_frozen_at_transaction_start(
    db_factory: sessionmaker[Session],
) -> None:
    from app.core.clock import DatabaseClock

    with db_factory() as db:
        first = DatabaseClock().now(db)
        db.execute(select(func.pg_sleep(0.03)))
        assert DatabaseClock().now(db) > first
