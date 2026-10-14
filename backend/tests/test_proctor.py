import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AttemptPresence,
    CandidateExamAssignment,
    Exam,
    ExamAttempt,
    ProctorExamAssignment,
    Role,
    SessionEvent,
    SessionEventType,
    User,
)
from app.schemas.proctor import PresenceWrite
from app.services import proctor_service
from app.services.auth_service import as_utc
from app.services.google_identity import GoogleIdentity
from tests.test_attempts import Scenario, TestClock, save_body, started, subject_path
from tests.test_attempts import candidate_headers as candidate_headers
from tests.test_attempts import clock as clock
from tests.test_attempts import scenario as scenario


def staff_login(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    origin: dict[str, str],
    role: Role = Role.PROCTOR,
) -> tuple[User, dict[str, str]]:
    with db_factory() as db:
        user = User(
            email=f"monitoring-{role.lower()}@gmail.com", display_name="Monitoring staff", role=role
        )
        db.add(user)
        db.commit()
    application.state.identity_verifier.identity = GoogleIdentity(
        f"google-{role}", user.email, True
    )
    signed = client.post(
        "/api/auth/google", headers=origin, json={"credential": "test-valid-credential"}
    )
    assert signed.status_code == 200
    return user, {**origin, "X-CSRF-Token": signed.json()["csrf_token"]}


def presence(attempt: dict[str, Any], events: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "subject_attempt_id": attempt["subjects"][0]["id"],
        "question_sequence": 1,
        "events": events or [],
    }


def scope(db_factory: sessionmaker[Session], scenario: Scenario, proctor: User) -> None:
    with db_factory() as db:
        proctor_service.assign(db, scenario.exam_id, proctor.id, True, scenario.admin_id)


@pytest.mark.parametrize("role", [Role.CANDIDATE, Role.EXAMINER])
def test_monitoring_requires_staff_role(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    candidate_headers: dict[str, str],
    role: Role,
) -> None:
    if role != Role.CANDIDATE:
        staff_login(client, application, db_factory, candidate_headers, role)
    assert client.get("/api/proctor/exams").status_code == 403


def test_anonymous_monitoring_denied(client: TestClient) -> None:
    assert client.get("/api/proctor/exams").status_code == 401


def test_scope_revocation_and_admin_access(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    user, _ = staff_login(client, application, db_factory, candidate_headers)
    path = f"/api/proctor/exams/{scenario.exam_id}/sessions"
    assert client.get("/api/proctor/exams").json() == []
    assert client.get(path).status_code == 404
    assert client.get(f"/api/proctor/attempts/{attempt['id']}/events").status_code == 404
    scope(db_factory, scenario, user)
    assert client.get("/api/proctor/exams").json()[0]["id"] == str(scenario.exam_id)
    assert client.get(path).status_code == 200
    assert client.get(f"/api/proctor/attempts/{attempt['id']}/events").status_code == 200
    with db_factory() as db:
        proctor_service.assign(db, scenario.exam_id, user.id, False, scenario.admin_id)
    assert client.get(path).status_code == 404
    assert client.get("/api/proctor/exams").json() == []
    staff_login(client, application, db_factory, candidate_headers, Role.ADMIN)
    assert client.get(path).status_code == 200


def test_presence_time_position_privacy_and_expiry(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    deadline = attempt["subjects"][0]["expires_at"]
    for question in questions:
        assert (
            client.put(
                subject_path(attempt) + f"/answers/{question['exam_question_id']}",
                headers=candidate_headers,
                json=save_body(question, marked=True),
            ).status_code
            == 200
        )
    path = f"/api/candidate/attempts/{attempt['id']}/presence"
    body = presence(attempt, [{"event_id": str(uuid.uuid4()), "event_type": "FULLSCREEN_EXIT"}])
    body["question_sequence"] = 2
    assert client.post(path, json=body, headers=candidate_headers).status_code == 200
    user, _ = staff_login(client, application, db_factory, candidate_headers)
    scope(db_factory, scenario, user)
    monitoring = f"/api/proctor/exams/{scenario.exam_id}/sessions"
    response = client.get(monitoring)
    item = response.json()["candidates"][0]
    assert item["state"] == "TESTING" and item["connection"] == "ONLINE"
    assert item["reported_question_sequence"] == 2 and item["question_count"] == 2
    assert item["expires_at"] == deadline and item["remaining_seconds"] == 60
    assert item["review_event_count"] == 1
    assert set(item) == {
        "candidate_id",
        "roll_number",
        "full_name",
        "access_active",
        "attempt_id",
        "state",
        "subject_attempt_id",
        "subject_name",
        "subject_status",
        "question_count",
        "reported_question_sequence",
        "expires_at",
        "remaining_seconds",
        "connection",
        "last_seen_at",
        "review_event_count",
    }
    event_response = client.get(f"/api/proctor/attempts/{attempt['id']}/events")
    for forbidden in (
        "SECRET_ACCEPTED_VALUE",
        "حسین",
        "short_answer_text",
        "selected_option_id",
        "is_correct",
        "prompt",
        "email",
    ):
        assert forbidden not in response.text and forbidden not in event_response.text
    assert all(
        set(event) == {"id", "event_type", "source", "subject_attempt_id", "server_timestamp"}
        for event in event_response.json()
    )
    clock.advance(31)
    stale = client.get(monitoring).json()["candidates"][0]
    assert stale["connection"] == "NO_RECENT_CONTACT" and stale["remaining_seconds"] == 29
    clock.advance(30)
    expired = client.get(monitoring).json()["candidates"][0]
    assert expired["state"] == "BETWEEN_SUBJECTS" and expired["subject_name"] == "Urdu"
    assert expired["reported_question_sequence"] is None and expired["remaining_seconds"] is None
    history = client.get(f"/api/proctor/attempts/{attempt['id']}/events").json()
    assert sum(event["event_type"] == "SUBJECT_AUTO_SUBMITTED" for event in history) == 1
    client.get(monitoring)
    assert (
        sum(
            event["event_type"] == "SUBJECT_AUTO_SUBMITTED"
            for event in client.get(f"/api/proctor/attempts/{attempt['id']}/events").json()
        )
        == 1
    )


def test_heartbeat_nonce_rate_limit_and_deadline(
    client: TestClient,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    path = f"/api/candidate/attempts/{attempt['id']}/presence"
    body = presence(attempt, [{"event_id": str(uuid.uuid4()), "event_type": "CONNECTION_LOST"}])
    assert client.post(path, json=body, headers=candidate_headers).status_code == 200
    limited = client.post(path, json=body, headers=candidate_headers)
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "5"
    clock.advance(10)
    assert client.post(path, json=body, headers=candidate_headers).status_code == 200
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttemptPresence)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(SessionEvent)
                .where(SessionEvent.event_type == SessionEventType.CONNECTION_LOST)
            )
            == 1
        )
        stored = db.get(ExamAttempt, uuid.UUID(attempt["id"]))
        assert stored is not None
        assert datetime.fromisoformat(attempt["subjects"][0]["expires_at"]) == as_utc(
            stored.started_at
        ) + timedelta(minutes=1)
    clock.advance(50)
    assert client.post(path, json=body, headers=candidate_headers).status_code == 410


@pytest.mark.parametrize(
    "change",
    [
        "origin",
        "csrf",
        "position",
        "subject",
        "source",
        "server_type",
        "payload",
        "duplicates",
        "batch",
    ],
)
def test_heartbeat_rejects_untrusted_context(
    client: TestClient, scenario: Scenario, candidate_headers: dict[str, str], change: str
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    body = presence(attempt)
    headers = dict(candidate_headers)
    event = {"event_id": str(uuid.uuid4()), "event_type": "FULLSCREEN_EXIT"}
    expected = 422
    if change in {"origin", "csrf"}:
        headers["Origin" if change == "origin" else "X-CSRF-Token"] = "invalid"
        expected = 403
    elif change == "position":
        body["question_sequence"] = 3
    elif change == "subject":
        body["subject_attempt_id"] = str(uuid.uuid4())
        expected = 404
    elif change == "source":
        body["source"] = "SERVER"
    elif change == "server_type":
        body["events"] = [{**event, "event_type": "EXAM_SUBMITTED"}]
    elif change == "payload":
        body["short_answer_text"] = "sensitive answer"
    elif change == "duplicates":
        body["events"] = [event, event]
    elif change == "batch":
        body["events"] = [{**event, "event_id": str(uuid.uuid4())} for _ in range(9)]
    assert (
        client.post(
            f"/api/candidate/attempts/{attempt['id']}/presence", json=body, headers=headers
        ).status_code
        == expected
    )


def test_heartbeat_ownership_and_revoked_assignment(
    client: TestClient,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
) -> None:
    attempt, _ = started(client, scenario, candidate_headers)
    with db_factory() as db:
        owned = db.get(ExamAttempt, uuid.UUID(attempt["id"]))
        assert owned is not None
        wrong_candidate = uuid.uuid4()
        with pytest.raises(HTTPException) as denied:
            proctor_service.heartbeat(
                db, owned.id, wrong_candidate, PresenceWrite(**presence(attempt)), TestClock()
            )
        assert denied.value.status_code == 404
        assignment = db.scalar(
            select(CandidateExamAssignment).where(
                CandidateExamAssignment.candidate_id == scenario.candidate_id
            )
        )
        assert assignment is not None
        assignment.is_active = False
        db.commit()
    assert (
        client.post(
            f"/api/candidate/attempts/{attempt['id']}/presence",
            json=presence(attempt),
            headers=candidate_headers,
        ).status_code
        == 403
    )


def test_server_events_are_atomic_and_retry_safe(
    client: TestClient,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
    clock: TestClock,
) -> None:
    attempt, questions = started(client, scenario, candidate_headers)
    client.post(subject_path(attempt) + "/start", headers=candidate_headers)
    path = subject_path(attempt) + f"/answers/{questions[0]['exam_question_id']}"
    body = save_body(questions[0], marked=True)
    assert client.put(path, json=body, headers=candidate_headers).status_code == 200
    assert client.put(path, json=body, headers=candidate_headers).status_code == 200
    assert (
        client.put(
            path,
            json={**body, "expected_revision": 0, "is_marked_for_review": False},
            headers=candidate_headers,
        ).status_code
        == 409
    )
    client.post(subject_path(attempt) + "/submit", headers=candidate_headers)
    client.post(subject_path(attempt) + "/submit", headers=candidate_headers)
    with db_factory() as db:
        kinds = list(db.scalars(select(SessionEvent.event_type)))
        for kind in (
            SessionEventType.EXAM_OPENED,
            SessionEventType.SUBJECT_STARTED,
            SessionEventType.ANSWER_SAVED,
            SessionEventType.QUESTION_FLAGGED,
            SessionEventType.SUBJECT_SUBMITTED,
        ):
            assert kinds.count(kind) == 1
    clock.advance(4 * 3600)
    from app.services.attempt_service import expire_due

    with db_factory() as db:
        expire_due(db, clock)
        expire_due(db, clock)
        kinds = list(db.scalars(select(SessionEvent.event_type)))
        assert kinds.count(SessionEventType.SUBJECT_AUTO_SUBMITTED) == 1
        assert kinds.count(SessionEventType.EXAM_SUBMITTED) == 1


def test_admin_assignment_validation_and_pagination(
    client: TestClient,
    application: FastAPI,
    db_factory: sessionmaker[Session],
    scenario: Scenario,
    candidate_headers: dict[str, str],
) -> None:
    user, _ = staff_login(client, application, db_factory, candidate_headers)
    assert client.get("/api/admin/proctors").status_code == 403
    _, admin = staff_login(client, application, db_factory, candidate_headers, Role.ADMIN)
    path = f"/api/admin/exams/{scenario.exam_id}/proctors/{user.id}"
    assert client.put(path, json={"is_active": True}).status_code == 403
    assert client.put(path, json={"is_active": True}, headers=admin).status_code == 200
    assert client.put(path, json={"is_active": True}, headers=admin).status_code == 200
    assert set(client.get("/api/admin/proctors").json()[0]) == {"id", "display_name"}
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(ProctorExamAssignment)) == 1
    assert (
        client.put(
            f"/api/admin/exams/{scenario.exam_id}/proctors/{scenario.admin_id}",
            json={"is_active": True},
            headers=admin,
        ).status_code
        == 409
    )
    assert client.get("/api/proctor/exams", params={"limit": 101}).status_code == 422
    monitor = f"/api/proctor/exams/{scenario.exam_id}/sessions"
    assert client.get(monitor, params={"search": "%"}).json()["candidates"] == []
    assert len(client.get(monitor).json()["candidates"]) == 1
    assert client.get(monitor, params={"offset": 1}).json()["candidates"] == []
    assert client.get(monitor, params={"active_only": True}).json()["candidates"] == []
    with db_factory() as db:
        other = Exam(title="Separate exam")
        db.add(other)
        db.commit()
        assert str(other.id) in {item["id"] for item in client.get("/api/proctor/exams").json()}
