import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AcceptedAnswer,
    Candidate,
    ExamQuestion,
    ExamSubject,
    GradingMode,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    User,
)


@pytest.fixture
def admin_headers(
    client: TestClient, db_factory: sessionmaker[Session], login_headers: dict[str, str]
) -> dict[str, str]:
    with db_factory() as db:
        db.add(User(email="candidate@gmail.com", display_name="Admin", role=Role.ADMIN))
        db.commit()
    result = client.post(
        "/api/auth/google", json={"credential": "test-valid-credential"}, headers=login_headers
    )
    assert result.status_code == 200
    return {**login_headers, "X-CSRF-Token": result.json()["csrf_token"]}


def create(
    client: TestClient, headers: dict[str, str], path: str, body: dict[str, Any]
) -> dict[str, Any]:
    result = client.post(f"/api/admin/{path}", json=body, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()


def setup_paper(client: TestClient, headers: dict[str, str]) -> tuple[str, str, str]:
    subject = create(client, headers, "subjects", {"name": "Science", "code": "sci"})
    exam = create(client, headers, "exams", {"title": "Configured admission test"})
    paper = create(
        client,
        headers,
        f"exams/{exam['id']}/subjects",
        {"subject_id": subject["id"], "duration_minutes": 45, "sequence": 1},
    )
    return subject["id"], exam["id"], paper["id"]


def mcq(subject_id: str) -> dict[str, Any]:
    return {
        "subject_id": subject_id,
        "type": "MCQ",
        "prompt": "Select an option.",
        "marks": "2.50",
        "options": [{"text": "First", "is_correct": True}, {"text": "Second", "is_correct": False}],
    }


@pytest.mark.parametrize("role", list(Role))
def test_admin_domain_role_boundary(
    client: TestClient, db_factory: sessionmaker[Session], login_headers: dict[str, str], role: Role
) -> None:
    with db_factory() as db:
        user = User(email="candidate@gmail.com", display_name="Role test", role=role)
        db.add(user)
        db.flush()
        if role == Role.CANDIDATE:
            db.add(Candidate(user_id=user.id, full_name="Candidate", roll_number="ROLE-104"))
        db.commit()
    response = client.post(
        "/api/auth/google", json={"credential": "test-valid-credential"}, headers=login_headers
    )
    headers = {**login_headers, "X-CSRF-Token": response.json()["csrf_token"]}
    expected = 200 if role == Role.ADMIN else 403
    for path in ["subjects", "exams", "questions"]:
        assert client.get(f"/api/admin/{path}").status_code == expected
    created = client.post(
        "/api/admin/subjects", json={"name": "Secret subject", "code": "SECRET"}, headers=headers
    )
    assert created.status_code == (201 if role == Role.ADMIN else 403)
    if role != Role.ADMIN:
        key_response = client.get(f"/api/admin/questions/{uuid.uuid4()}")
        assert key_response.status_code == 403
        assert "is_correct" not in key_response.text


def test_anonymous_admin_denied(client: TestClient) -> None:
    assert client.get("/api/admin/questions").status_code == 401
    assert client.post("/api/admin/subjects", json={"name": "X", "code": "X"}).status_code == 401


def test_mutations_require_origin_and_csrf(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    body = {"name": "Subject", "code": "SUB"}
    assert client.post("/api/admin/subjects", json=body).status_code == 403
    assert (
        client.post(
            "/api/admin/subjects", json=body, headers={"Origin": admin_headers["Origin"]}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/subjects",
            json=body,
            headers={**admin_headers, "Origin": "https://foreign.example"},
        ).status_code
        == 403
    )
    subject = create(client, admin_headers, "subjects", body)
    assert client.put(f"/api/admin/subjects/{subject['id']}", json=body).status_code == 403
    assert client.get("/api/admin/subjects").json()[0]["code"] == "SUB"


def test_configurable_domain_and_atomic_ordered_paper(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject_id, exam_id, paper_id = setup_paper(client, admin_headers)
    first = create(client, admin_headers, "questions", mcq(subject_id))
    second = create(
        client,
        admin_headers,
        "questions",
        {
            "subject_id": subject_id,
            "type": "SHORT_ANSWER",
            "prompt": "مختصر جواب لکھیں۔",
            "direction": "rtl",
            "language": "ur",
            "marks": "3",
            "grading": {"mode": "MANUAL"},
        },
    )
    path = f"/api/admin/exam-subjects/{paper_id}/questions"
    paper = client.put(
        path,
        headers=admin_headers,
        json={
            "questions": [
                {"question_id": second["id"], "marks_override": "4"},
                {"question_id": first["id"]},
            ]
        },
    )
    assert paper.status_code == 200, paper.text
    assert [item["question_id"] for item in paper.json()["questions"]] == [
        second["id"],
        first["id"],
    ]
    assert Decimal(paper.json()["total_marks"]) == Decimal("6.50")
    summary = client.get(f"/api/admin/exams/{exam_id}/subjects").json()[0]
    assert summary["duration_minutes"] == 45 and summary["question_count"] == 2
    assert Decimal(summary["total_marks"]) == Decimal("6.50")
    duplicate = client.put(
        path,
        headers=admin_headers,
        json={"questions": [{"question_id": first["id"]}, {"question_id": first["id"]}]},
    )
    assert duplicate.status_code == 422
    missing = client.put(
        path, headers=admin_headers, json={"questions": [{"question_id": str(uuid.uuid4())}]}
    )
    assert missing.status_code == 404
    assert client.get(path).json() == paper.json()
    assert (
        client.put(
            f"/api/admin/questions/{first['id']}", headers=admin_headers, json=mcq(subject_id)
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/admin/questions/{first['id']}/archive", headers=admin_headers
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/admin/exams/{exam_id}/subjects/{paper_id}", headers=admin_headers
        ).status_code
        == 409
    )
    # Paper replacement can reorder the same questions without unique-sequence collisions.
    reordered = client.put(
        path,
        headers=admin_headers,
        json={"questions": [{"question_id": first["id"]}, {"question_id": second["id"]}]},
    )
    assert reordered.status_code == 200
    assert [item["sequence"] for item in reordered.json()["questions"]] == [1, 2]
    assert client.put(path, headers=admin_headers, json={"questions": []}).status_code == 200
    assert (
        client.delete(
            f"/api/admin/exams/{exam_id}/subjects/{paper_id}", headers=admin_headers
        ).status_code
        == 204
    )


def test_questions_modes_update_and_archive(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject_id, _, _ = setup_paper(client, admin_headers)
    question = create(client, admin_headers, "questions", mcq(subject_id))
    assert sum(item["is_correct"] for item in question["options"]) == 1
    exact = {
        "subject_id": subject_id,
        "type": "SHORT_ANSWER",
        "prompt": "Write a word.",
        "marks": "1",
        "grading": {"mode": "EXACT", "case_sensitive": False},
        "accepted_answers": ["  Beautiful  ", "lovely"],
    }
    updated = client.put(
        f"/api/admin/questions/{question['id']}", json=exact, headers=admin_headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["options"] == []
    assert (
        "  Beautiful  " in updated.json()["accepted_answers"]
    )  # Raw accepted values are preserved.
    numeric = create(
        client,
        admin_headers,
        "questions",
        {
            **exact,
            "grading": {"mode": "NUMERIC", "absolute_tolerance": "0.01"},
            "accepted_answers": ["24"],
        },
    )
    assert numeric["grading"]["absolute_tolerance"] == "0.01"
    assert (
        client.post(f"/api/admin/questions/{question['id']}/archive", headers=admin_headers).json()[
            "is_active"
        ]
        is False
    )
    results = client.get(
        f"/api/admin/questions?subject_id={subject_id}&question_type=SHORT_ANSWER&limit=1&offset=1"
    )
    assert results.status_code == 200 and len(results.json()) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"options": [{"text": "A", "is_correct": False}, {"text": "B", "is_correct": False}]},
        {"options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}]},
        {"options": [{"text": "A", "is_correct": True}, {"text": "A", "is_correct": False}]},
        {"marks": "0"},
        {"marks": "1.001"},
        {"marks": "NaN"},
        {"type": "ESSAY"},
        {"grading": {"mode": "EXACT"}},
        {"correct_option_id": "secret"},
        {"direction": "invalid"},
    ],
)
def test_reject_invalid_mcq(
    client: TestClient, admin_headers: dict[str, str], change: dict[str, Any]
) -> None:
    subject_id, _, _ = setup_paper(client, admin_headers)
    response = client.post(
        "/api/admin/questions", json={**mcq(subject_id), **change}, headers=admin_headers
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Please check the request data."}


@pytest.mark.parametrize(
    "grading,answers",
    [
        ({"mode": "MANUAL"}, ["secret"]),
        ({"mode": "EXACT"}, []),
        ({"mode": "EXACT", "case_sensitive": False}, ["A", "a"]),
        ({"mode": "NUMERIC"}, ["NaN"]),
        ({"mode": "NUMERIC"}, ["Infinity"]),
        ({"mode": "NUMERIC"}, ["2+2"]),
        ({"mode": "NUMERIC"}, ["24", "24.0"]),
        ({"mode": "NUMERIC", "absolute_tolerance": "-1"}, ["24"]),
        ({"mode": "NUMERIC"}, ["1e101"]),
        ({"mode": "EXACT"}, ["   "]),
    ],
)
def test_reject_invalid_short_answers(
    client: TestClient, admin_headers: dict[str, str], grading: dict[str, Any], answers: list[str]
) -> None:
    subject_id, _, _ = setup_paper(client, admin_headers)
    response = client.post(
        "/api/admin/questions",
        headers=admin_headers,
        json={
            "subject_id": subject_id,
            "type": "SHORT_ANSWER",
            "prompt": "Answer",
            "marks": "1",
            "grading": grading,
            "accepted_answers": answers,
        },
    )
    assert response.status_code == 422
    assert "secret" not in response.text


def test_conflicts_archive_and_safe_errors(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject_id, exam_id, paper_id = setup_paper(client, admin_headers)
    duplicate = client.post(
        "/api/admin/subjects", json={"name": "Other name", "code": "SCI"}, headers=admin_headers
    )
    assert duplicate.status_code == 409
    assert "SQL" not in duplicate.text
    assert (
        client.post(
            f"/api/admin/exams/{exam_id}/subjects",
            headers=admin_headers,
            json={"subject_id": subject_id, "duration_minutes": 0, "sequence": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/admin/exams/{exam_id}/subjects",
            headers=admin_headers,
            json={"subject_id": subject_id, "duration_minutes": 60, "sequence": 2},
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/admin/exams/{exam_id}",
            headers=admin_headers,
            json={"title": "Archived", "status": "ARCHIVED"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/admin/exam-subjects/{paper_id}/questions",
            headers=admin_headers,
            json={"questions": []},
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/admin/exams/{exam_id}", headers=admin_headers, json={"title": "Reopened"}
        ).status_code
        == 409
    )


def test_subject_mismatch_inactive_questions_and_owned_paths(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject_id, exam_id, paper_id = setup_paper(client, admin_headers)
    other_subject = create(
        client, admin_headers, "subjects", {"name": "Another subject", "code": "OTHER"}
    )
    wrong = create(client, admin_headers, "questions", mcq(other_subject["id"]))
    path = f"/api/admin/exam-subjects/{paper_id}/questions"
    assert (
        client.put(
            path, headers=admin_headers, json={"questions": [{"question_id": wrong["id"]}]}
        ).status_code
        == 409
    )
    inactive = create(client, admin_headers, "questions", {**mcq(subject_id), "is_active": False})
    assert (
        client.put(
            path, headers=admin_headers, json={"questions": [{"question_id": inactive["id"]}]}
        ).status_code
        == 409
    )
    another_exam = create(client, admin_headers, "exams", {"title": "Other exam"})
    body = {"subject_id": subject_id, "duration_minutes": 60, "sequence": 1}
    assert (
        client.put(
            f"/api/admin/exams/{another_exam['id']}/subjects/{paper_id}",
            headers=admin_headers,
            json=body,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/admin/exams/{another_exam['id']}/subjects/{paper_id}", headers=admin_headers
        ).status_code
        == 404
    )
    assert client.get(f"/api/admin/exams/{exam_id}/subjects").json()[0]["id"] == paper_id


@pytest.mark.parametrize(
    "body",
    [
        {"title": "Exam", "scheduled_start": "2026-10-15T09:00:00Z"},
        {
            "title": "Exam",
            "scheduled_start": "2026-10-15T10:00:00Z",
            "scheduled_end": "2026-10-15T09:00:00Z",
        },
        {
            "title": "Exam",
            "scheduled_start": "2026-10-15T09:00:00",
            "scheduled_end": "2026-10-15T10:00:00",
        },
    ],
)
def test_invalid_schedules(
    client: TestClient, admin_headers: dict[str, str], body: dict[str, Any]
) -> None:
    assert client.post("/api/admin/exams", json=body, headers=admin_headers).status_code == 422


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-10-15T09:00:00Z", "2026-10-15T10:00:00Z"),
        ("2026-10-15T14:00:00+05:00", "2026-10-15T15:00:00+05:00"),
    ],
)
def test_valid_schedule_roundtrip(
    client: TestClient, admin_headers: dict[str, str], start: str, end: str
) -> None:
    body = {
        "title": "Scheduled",
        "scheduled_start": start,
        "scheduled_end": end,
    }
    exam = create(client, admin_headers, "exams", body)
    result = client.get(f"/api/admin/exams/{exam['id']}")
    assert result.status_code == 200, result.text
    assert result.json()["scheduled_start"] == "2026-10-15T09:00:00Z"


def test_database_rejects_cross_subject_attachment(
    client: TestClient, admin_headers: dict[str, str], db_factory: sessionmaker[Session]
) -> None:
    _, _, paper_id = setup_paper(client, admin_headers)
    other = create(client, admin_headers, "subjects", {"name": "Other", "code": "OTHER"})
    question = create(client, admin_headers, "questions", mcq(other["id"]))
    with db_factory() as db:
        paper = db.get(ExamSubject, uuid.UUID(paper_id))
        assert paper is not None
        db.add(
            ExamQuestion(
                exam_subject_id=paper.id,
                subject_id=paper.subject_id,
                question_id=uuid.UUID(question["id"]),
                sequence=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    "mutation", ["second_correct", "option_on_short_answer", "accepted_on_mcq", "zero_marks"]
)
def test_database_question_constraints(
    client: TestClient,
    admin_headers: dict[str, str],
    db_factory: sessionmaker[Session],
    mutation: str,
) -> None:
    subject_id, _, _ = setup_paper(client, admin_headers)
    question = create(client, admin_headers, "questions", mcq(subject_id))
    with db_factory() as db:
        record = db.get(Question, uuid.UUID(question["id"]))
        assert record is not None
        if mutation == "second_correct":
            db.add(
                QuestionOption(
                    question_id=record.id, display_order=3, option_text="Third", is_correct=True
                )
            )
        elif mutation == "option_on_short_answer":
            manual = Question(
                subject_id=uuid.UUID(subject_id),
                type=QuestionType.SHORT_ANSWER,
                prompt="Manual",
                marks=Decimal(1),
                grading_mode=GradingMode.MANUAL,
                grading_config={"mode": "MANUAL"},
            )
            db.add(manual)
            db.flush()
            db.add(
                QuestionOption(
                    question_id=manual.id, display_order=1, option_text="Invalid", is_correct=True
                )
            )
        elif mutation == "accepted_on_mcq":
            db.add(
                AcceptedAnswer(question_id=record.id, grading_mode="EXACT", accepted_value="secret")
            )
        else:
            record.marks = Decimal(0)
        with pytest.raises(IntegrityError):
            db.commit()
