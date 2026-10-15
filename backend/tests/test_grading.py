import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AcceptedAnswer,
    Answer,
    AuditEvent,
    Candidate,
    CandidateExamAssignment,
    Exam,
    ExamQuestion,
    GradingMode,
    GradingRecord,
    Question,
    QuestionType,
    Role,
    SubjectAttempt,
    User,
)
from app.schemas.exam_domain import ExactConfig
from app.schemas.grading import ManualGradeWrite
from app.services import attempt_service, grading_service
from app.services.auto_grading_service import exact, numeric
from tests.test_attempts import Scenario, TestClock, save_body, started, subject_path
from tests.test_attempts import candidate_headers as candidate_headers
from tests.test_attempts import clock as clock
from tests.test_attempts import scenario as scenario
from tests.test_proctor import staff_login


@pytest.mark.parametrize(
    "value,expected",
    [
        (" 24 ", "24"),
        ("+2.4e1", "24"),
        (".5", "0.5"),
        ("-0", "0"),
        ("0e999999", "0"),
        ("1/2", None),
        ("NaN", None),
        ("Infinity", None),
        ("24cm", None),
        ("٢٤", None),
        ("1e101", None),
        ("1e-101", None),
        ("", None),
    ],
)
def test_numeric_parser_is_bounded_and_does_not_evaluate_expressions(
    value: str, expected: str | None
) -> None:
    assert numeric(value) == (Decimal(expected) if expected is not None else None)


def test_exact_grading_obeys_explicit_rules_and_supports_unicode() -> None:
    assert exact(" CAFÉ  ", ExactConfig()) == " CAFÉ  "
    config = ExactConfig(trim_whitespace=True, collapse_whitespace=True, case_sensitive=False)
    assert exact("  CAFE\u0301  text ", config) == "café text"
    assert exact(" محمد   احمد ", config) == "محمد احمد"
    assert exact("e\u0301", ExactConfig(unicode_normalization="NONE")) != "é"


@pytest.fixture
def grading_case(db_factory: sessionmaker[Session], scenario: Scenario) -> Scenario:
    with db_factory() as db:
        subjects = list(db.scalars(select(SubjectAttempt)))
        assert not subjects
        questions = list(
            db.scalars(
                select(Question)
                .where(Question.type == QuestionType.SHORT_ANSWER)
                .order_by(Question.prompt)
            )
        )
        manual = next(question for question in questions if question.language == "en")
        db.execute(delete(AcceptedAnswer).where(AcceptedAnswer.question_id == manual.id))
        db.flush()
        manual.grading_mode = GradingMode.MANUAL
        manual.grading_config = {"mode": "MANUAL"}
        automatic = next(question for question in questions if question.id != manual.id)
        automatic.grading_config = {
            "mode": "EXACT",
            "trim_whitespace": True,
            "case_sensitive": False,
        }
        db.commit()
    return scenario


def finish(
    client: TestClient,
    case: Scenario,
    headers: dict[str, str],
    *,
    manual_text: str = "A written response",
) -> dict[str, Any]:
    attempt, questions = started(client, case, headers)
    for index in range(2):
        path = subject_path(attempt, index)
        if index:
            assert client.post(path + "/start", headers=headers).status_code == 200
            questions = client.get(path + "/questions").json()["questions"]
        for question in questions:
            body = save_body(question)
            if question["type"] == "SHORT_ANSWER":
                body["short_answer_text"] = " secret_accepted_value " if index else manual_text
            elif index:
                body["selected_option_id"] = question["options"][1]["id"]
            response = client.put(
                path + f"/answers/{question['exam_question_id']}", headers=headers, json=body
            )
            assert response.status_code == 200, response.text
        result = client.post(path + "/submit", headers=headers)
        assert result.status_code == 200, result.text
        attempt = result.json()
    assert attempt["status"] == "SUBMITTED"
    return attempt


def manual_id(db_factory: sessionmaker[Session]) -> UUID:
    with db_factory() as db:
        result = db.scalar(
            select(Answer.id)
            .join(Question, Question.id == Answer.question_id)
            .where(Question.grading_mode == GradingMode.MANUAL)
        )
        assert result is not None
        return result


def test_automatic_grades_preserve_raw_answers_and_are_idempotent(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    attempt = finish(client, grading_case, candidate_headers)
    with db_factory() as db:
        grades = list(db.scalars(select(GradingRecord)))
        assert len(grades) == 3
        assert sum(row.marks_awarded for row in grades) == Decimal(3)
        assert all(row.graded_by is None for row in grades)
        raw = db.scalar(select(Answer).where(Answer.id == manual_id(db_factory)))
        assert raw.short_answer_text == "A written response" and raw.revision == 1
        actor = db.get(User, grading_case.admin_id)
        assert grading_service.grade_attempt(db, UUID(attempt["id"]), actor, clock) == 0
        assert db.scalar(select(func.count()).select_from(GradingRecord)) == 3
    result = client.get("/api/candidate/results").json()[0]
    assert result["grading_status"] == "PENDING"
    assert result["subjects"] == [] and result["marks_awarded"] is None
    assert "accepted_answers" not in str(result) and "notes" not in str(result)


def test_manual_review_history_retry_stale_write_release_and_candidate_visibility(
    client: TestClient,
    application: FastAPI,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    finish(client, grading_case, candidate_headers)
    answer_id = manual_id(db_factory)
    with TestClient(application) as examiner_client, TestClient(application) as admin_client:
        examiner, examiner_headers = staff_login(
            examiner_client, application, db_factory, candidate_headers, Role.EXAMINER
        )
        _, admin_headers = staff_login(
            admin_client, application, db_factory, candidate_headers, Role.ADMIN
        )
        queue = f"/api/grading/exams/{grading_case.exam_id}/queue"
        grade_path = f"/api/grading/answers/{answer_id}/grade"
        assert examiner_client.get(queue).status_code == 404
        assert (
            examiner_client.post(
                grade_path,
                headers=examiner_headers,
                json={"expected_revision": 0, "marks_awarded": "1.50"},
            ).status_code
            == 404
        )
        grant = f"/api/admin/exams/{grading_case.exam_id}/examiners/{examiner.id}"
        assert (
            admin_client.put(grant, json={"is_active": True}, headers=admin_headers).status_code
            == 200
        )
        row = examiner_client.get(queue).json()[0]
        assert row["answer_text"] == "A written response" and row["current_grade"] is None
        assert "accepted_answers" not in row
        assert (
            examiner_client.post(
                grade_path, json={"expected_revision": 0, "marks_awarded": "1.50"}
            ).status_code
            == 403
        )
        assert (
            examiner_client.post(
                grade_path,
                json={"expected_revision": 0, "marks_awarded": "2.01"},
                headers=examiner_headers,
            ).status_code
            == 422
        )
        body = {"expected_revision": 0, "marks_awarded": "1.50", "notes": "Initial review"}
        grade = examiner_client.post(grade_path, json=body, headers=examiner_headers)
        assert grade.status_code == 200, grade.text
        assert (
            examiner_client.post(grade_path, json=body, headers=examiner_headers).json()["id"]
            == grade.json()["id"]
        )
        assert examiner_client.get(queue).json() == []
        assert len(examiner_client.get(queue, params={"include_graded": True}).json()) == 1
        changed = {
            **body,
            "expected_revision": 1,
            "marks_awarded": "2",
            "notes": "Rubric correction",
        }
        assert (
            examiner_client.post(grade_path, json=changed, headers=examiner_headers).status_code
            == 200
        )
        assert (
            examiner_client.post(grade_path, json=body, headers=examiner_headers).status_code == 409
        )
        history = examiner_client.get(f"/api/grading/answers/{answer_id}/history").json()
        assert [row["revision"] for row in history] == [1, 2]
        assert all(row["graded_by"] == str(examiner.id) for row in history)
        path = f"/api/admin/exams/{grading_case.exam_id}/result-release"
        assert client.get("/api/candidate/results").json()[0]["marks_awarded"] is None
        assert (
            admin_client.post(path, json={"released": True}, headers=admin_headers).status_code
            == 409
        )
        assert (
            admin_client.post(
                f"/api/admin/exams/{grading_case.exam_id}/start-authorization",
                json={"authorized": False},
                headers=admin_headers,
            ).status_code
            == 200
        )
        future = (clock.value + timedelta(minutes=1)).isoformat()
        assert (
            admin_client.post(
                path, json={"released": True, "result_release_at": future}, headers=admin_headers
            ).status_code
            == 200
        )
        assert client.get("/api/candidate/results").json()[0]["publication_status"] == "SCHEDULED"
        assert client.get("/api/candidate/results").json()[0]["marks_awarded"] is None
        assert (
            examiner_client.post(
                grade_path, json={**changed, "expected_revision": 2}, headers=examiner_headers
            ).status_code
            == 409
        )
        clock.advance(60)
        result = client.get("/api/candidate/results").json()[0]
        assert result["publication_status"] == "RELEASED" and result["marks_awarded"] == "5.00"
        assert result["maximum_marks"] == "6.00" and result["percentage"] == "83.33"
        assert [row["marks_awarded"] for row in result["subjects"]] == ["3.00", "2.00"]
        assert "notes" not in str(result) and "correct" not in str(result)
        assert (
            admin_client.post(path, json={"released": False}, headers=admin_headers).status_code
            == 200
        )
        assert client.get("/api/candidate/results").json()[0]["marks_awarded"] is None
        assert (
            admin_client.put(grant, json={"is_active": False}, headers=admin_headers).status_code
            == 200
        )
        assert examiner_client.get(queue).status_code == 404
        assert examiner_client.get(f"/api/grading/answers/{answer_id}/history").status_code == 404
    with db_factory() as db:
        assert db.get(Answer, answer_id).short_answer_text == "A written response"
        assert db.scalar(select(func.count()).select_from(GradingRecord)) == 5
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "MANUAL_GRADE_RECORDED")
            )
            == 2
        )


@pytest.mark.parametrize("role", [Role.CANDIDATE, Role.PROCTOR])
def test_candidate_and_proctor_cannot_grade_or_read_queue(
    client: TestClient,
    application: FastAPI,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    role: Role,
) -> None:
    if role == Role.PROCTOR:
        staff_login(client, application, db_factory, candidate_headers, role)
    assert client.get("/api/grading/exams").status_code == 403
    assert client.get(f"/api/grading/exams/{scenario.exam_id}/queue").status_code == 403
    assert client.get("/api/admin/examiners").status_code == 403


def test_blank_manual_response_gets_zero_without_manual_work(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    finish(client, grading_case, candidate_headers, manual_text="   ")
    with db_factory() as db:
        grade = db.scalar(
            select(GradingRecord).where(GradingRecord.answer_id == manual_id(db_factory))
        )
        assert grade.method == "UNANSWERED" and grade.marks_awarded == 0
    assert client.get("/api/candidate/results").json()[0]["grading_status"] == "COMPLETE"


def test_expiry_grades_saved_answers_and_never_started_subject_scores_zero(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    attempt, questions = started(client, grading_case, candidate_headers)
    response = client.put(
        subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}",
        json=save_body(questions[0]),
        headers=candidate_headers,
    )
    assert response.status_code == 200
    clock.advance(4 * 3600)
    assert client.get(f"/api/candidate/attempts/{attempt['id']}").json()["status"] == "SUBMITTED"
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(GradingRecord)) == 2
    assert client.get("/api/candidate/results").json()[0]["grading_status"] == "COMPLETE"


def test_grade_database_constraints(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    finish(client, grading_case, candidate_headers)
    with db_factory() as db:
        db.add(
            GradingRecord(
                answer_id=manual_id(db_factory),
                revision=1,
                answer_revision=1,
                marks_awarded=3,
                maximum_marks=2,
                method="MANUAL",
                graded_by=grading_case.admin_id,
                graded_at=clock.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    "text,correct",
    [
        ("24", True),
        ("24.01", True),
        ("23.99", True),
        ("24.0100000000000000000000000000000000000001", False),
        ("24.011", False),
        ("24cm", False),
        ("24/1", False),
        ("NaN", False),
    ],
)
def test_numeric_tolerance_is_precise(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    text: str,
    correct: bool,
) -> None:
    with db_factory() as db:
        question = db.scalar(
            select(Question).where(
                Question.language == "en", Question.type == QuestionType.SHORT_ANSWER
            )
        )
        question.grading_mode = GradingMode.NUMERIC
        question.grading_config = {"mode": "NUMERIC", "absolute_tolerance": "0.01"}
        db.flush()
        db.add(AcceptedAnswer(question_id=question.id, grading_mode="NUMERIC", accepted_value="24"))
        question_id = question.id
        db.commit()
    finish(client, grading_case, candidate_headers, manual_text=text)
    with db_factory() as db:
        answer = db.scalar(select(Answer).where(Answer.question_id == question_id))
        grade = db.scalar(select(GradingRecord).where(GradingRecord.answer_id == answer.id))
        assert grade.method == "NUMERIC"
        assert grade.marks_awarded == (Decimal(2) if correct else Decimal(0))
        assert answer.short_answer_text == text


def test_active_answers_cannot_be_reviewed(
    client: TestClient,
    application: FastAPI,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    started(client, grading_case, candidate_headers)
    answer_id = manual_id(db_factory)
    with TestClient(application) as admin:
        _, headers = staff_login(admin, application, db_factory, candidate_headers, Role.ADMIN)
        assert admin.get(f"/api/grading/exams/{grading_case.exam_id}/queue").json() == []
        assert (
            admin.post(
                f"/api/grading/answers/{answer_id}/grade",
                headers=headers,
                json={"expected_revision": 0, "marks_awarded": "1"},
            ).status_code
            == 409
        )
        assert (
            admin.post(
                f"/api/admin/exams/{grading_case.exam_id}/result-release",
                headers=headers,
                json={"released": True},
            ).status_code
            == 409
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"marks_awarded": "-1"},
        {"marks_awarded": "NaN"},
        {"marks_awarded": "Infinity"},
        {"marks_awarded": "0.001"},
        {"expected_revision": "0"},
        {"role": "ADMIN"},
    ],
)
def test_manual_grade_validation(
    client: TestClient,
    application: FastAPI,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    fields: dict[str, str],
) -> None:
    finish(client, grading_case, candidate_headers)
    with TestClient(application) as admin:
        _, headers = staff_login(admin, application, db_factory, candidate_headers, Role.ADMIN)
        response = admin.post(
            f"/api/grading/answers/{manual_id(db_factory)}/grade",
            json={"expected_revision": 0, "marks_awarded": "1", **fields},
            headers=headers,
        )
        assert response.status_code == 422


def test_marks_override_and_unanswered_mcq(
    client: TestClient,
    scenario: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    with db_factory() as db:
        entry = db.scalar(
            select(ExamQuestion)
            .join(Question, Question.id == ExamQuestion.question_id)
            .where(Question.language == "en", Question.type == QuestionType.SHORT_ANSWER)
        )
        entry.marks_override = Decimal("3.25")
        db.commit()
    attempt, questions = started(client, scenario, candidate_headers)
    short = next(item for item in questions if item["type"] == "SHORT_ANSWER")
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{short['exam_question_id']}",
            headers=candidate_headers,
            json={**save_body(short), "short_answer_text": "SECRET_ACCEPTED_VALUE"},
        ).status_code
        == 200
    )
    assert (
        client.post(subject_path(attempt) + "/submit", headers=candidate_headers).status_code == 200
    )
    with db_factory() as db:
        grades = list(db.scalars(select(GradingRecord)))
        assert sorted(row.marks_awarded for row in grades) == [Decimal(0), Decimal("3.25")]


def test_candidate_results_are_owner_scoped_and_revocable(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    attempt = finish(client, grading_case, candidate_headers)
    with db_factory() as db:
        user = User(email="other-result@gmail.com", display_name="Other", role=Role.CANDIDATE)
        db.add(user)
        db.flush()
        other = Candidate(user_id=user.id, roll_number="OTHER-RESULT", full_name="Other")
        db.add(other)
        db.flush()
        other_id = other.id
        db.commit()
        attempt_service.assign_candidate(
            db, grading_case.exam_id, other_id, grading_case.admin_id, True
        )
        second = attempt_service.begin_exam(db, grading_case.exam_id, other_id, clock)
        # A corrupt or legacy release flag alone must never reveal pending grades.
        db.get(Exam, grading_case.exam_id).results_released = True
        db.commit()
    result = client.get("/api/candidate/results", params={"candidate_id": str(other_id)}).json()
    assert [row["attempt_id"] for row in result] == [attempt["id"]]
    assert result[0]["marks_awarded"] is None and result[0]["subjects"] == []
    assert second.id != UUID(attempt["id"])
    with db_factory() as db:
        assignment = db.scalar(
            select(CandidateExamAssignment).where(
                CandidateExamAssignment.candidate_id == grading_case.candidate_id
            )
        )
        assignment.is_active = False
        db.commit()
    assert client.get("/api/candidate/results").json() == []


def test_invalid_grading_configuration_does_not_prevent_submission(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    attempt, questions = started(client, grading_case, candidate_headers)
    short = next(item for item in questions if item["type"] == "SHORT_ANSWER")
    assert (
        client.put(
            subject_path(attempt) + f"/answers/{short['exam_question_id']}",
            headers=candidate_headers,
            json={**save_body(short), "short_answer_text": "Written response"},
        ).status_code
        == 200
    )
    with db_factory() as db:
        question = db.scalar(
            select(Question).where(
                Question.language == "en", Question.type == QuestionType.SHORT_ANSWER
            )
        )
        question.grading_config = {"mode": "EXACT", "unexpected": "invalid"}
        db.commit()
    submitted = client.post(subject_path(attempt) + "/submit", headers=candidate_headers)
    assert submitted.status_code == 200
    assert submitted.json()["subjects"][0]["status"] == "SUBMITTED"
    assert client.get("/api/candidate/results").json()[0]["grading_status"] == "PENDING"


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="PostgreSQL row locks")
def test_parallel_manual_marks_do_not_overwrite_each_other(
    client: TestClient,
    grading_case: Scenario,
    candidate_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    clock: TestClock,
) -> None:
    finish(client, grading_case, candidate_headers)
    answer_id = manual_id(db_factory)

    def grade(mark: str) -> int:
        with db_factory() as db:
            actor = db.get(User, grading_case.admin_id)
            try:
                grading_service.manual_grade(
                    db,
                    answer_id,
                    actor,
                    ManualGradeWrite(expected_revision=0, marks_awarded=mark, notes="Review"),
                    clock,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(grade, ["1", "2"])) == [200, 409]
    with db_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(GradingRecord)
                .where(GradingRecord.answer_id == answer_id)
            )
            == 1
        )
