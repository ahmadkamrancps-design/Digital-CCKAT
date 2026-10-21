from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, Candidate, CandidateStatus, Role, User
from app.services.google_identity import GoogleIdentity
from tests.conftest import FakeIdentityVerifier
from tests.test_exam_domain import create, mcq, setup_paper


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


def registration(roll: str = "CCK-201", email: str = "approved@gmail.com") -> dict[str, Any]:
    return {
        "email": email,
        "full_name": "محمد احمد",
        "roll_number": roll,
        "google_subject": None,
        "status": "APPROVED",
    }


def test_admin_registers_admission_details_without_google_or_email(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    details = {
        "roll_number": "CCK-PORTAL-1",
        "full_name": "محمد احمد",
        "father_name": "محمد کامران",
    }
    saved = create(client, admin_headers, "candidates", details)
    assert saved["email"] is None and saved["google_subject"] is None
    assert saved["father_name"] == details["father_name"]
    # Use a separate client so the administrator session is unaffected.
    with TestClient(client.app) as candidate:
        response = candidate.post(
            "/api/auth/candidate", json=details, headers={"Origin": admin_headers["Origin"]}
        )
        assert response.status_code == 200
        assert response.json()["candidate"]["id"] == saved["id"]
    imported = client.post(
        "/api/admin/candidates/import",
        json={"candidates": [{**details, "roll_number": "CCK-PORTAL-2"}]},
        headers=admin_headers,
    )
    assert imported.status_code == 201
    assert imported.json()[0]["email"] is None


@pytest.mark.parametrize("role", list(Role))
def test_management_rbac(
    client: TestClient, db_factory: sessionmaker[Session], login_headers: dict[str, str], role: Role
) -> None:
    with db_factory() as db:
        user = User(email="candidate@gmail.com", display_name="Role", role=role)
        db.add(user)
        db.flush()
        if role == Role.CANDIDATE:
            db.add(Candidate(user_id=user.id, full_name="Candidate", roll_number="CCK-104"))
        db.commit()
    signed = client.post(
        "/api/auth/google", json={"credential": "test-valid-credential"}, headers=login_headers
    ).json()
    headers = {**login_headers, "X-CSRF-Token": signed["csrf_token"]}
    expected = 200 if role == Role.ADMIN else 403
    for path in ["candidates", "actions", "overview"]:
        assert client.get(f"/api/admin/{path}").status_code == expected
    result = client.post("/api/admin/candidates", json=registration(), headers=headers)
    assert result.status_code == (201 if role == Role.ADMIN else 403)
    if role != Role.ADMIN:
        with db_factory() as db:
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_anonymous_management_denied(client: TestClient) -> None:
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/candidates").status_code == 401
    assert client.post("/api/admin/candidates", json=registration()).status_code == 401


def test_admin_overview_empty_workspace(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/overview")
    assert response.status_code == 200
    assert response.json() == {
        "candidate_count": 0,
        "approved_candidates": 0,
        "exam_count": 0,
        "published_exams": 0,
        "question_count": 0,
        "active_questions": 0,
        "subject_count": 0,
        "active_subjects": 0,
        "recent_exams": [],
        "recent_actions": [],
    }


def test_admin_overview_counts_all_records_and_limits_recent_details(
    client: TestClient,
    admin_headers: dict[str, str],
    db_factory: sessionmaker[Session],
) -> None:
    with db_factory() as db:
        users = [
            User(display_name=f"Candidate {number}", role=Role.CANDIDATE) for number in range(51)
        ]
        db.add_all(users)
        db.flush()
        db.add_all(
            Candidate(
                user_id=user.id,
                full_name=user.display_name,
                father_name="Registered Father",
                roll_number=f"OVERVIEW-{number:03}",
                status=CandidateStatus.DISABLED if number == 50 else CandidateStatus.APPROVED,
            )
            for number, user in enumerate(users)
        )
        db.commit()
    subject, _, _ = setup_paper(client, admin_headers)
    question = create(client, admin_headers, "questions", mcq(subject))
    other = create(
        client,
        admin_headers,
        "questions",
        {**mcq(subject), "prompt": "PRIVATE QUESTION PROMPT"},
    )
    assert (
        client.post(
            f"/api/admin/questions/{other['id']}/archive", headers=admin_headers
        ).status_code
        == 200
    )
    create(
        client,
        admin_headers,
        "subjects",
        {"name": "Archived subject", "code": "OLD", "is_active": False},
    )
    for number in range(6):
        create(
            client,
            admin_headers,
            "exams",
            {"title": f"Another exam {number}", "is_published": False},
        )
    result = client.get("/api/admin/overview").json()
    assert result["candidate_count"] == 51 and result["approved_candidates"] == 50
    assert result["exam_count"] == 7
    assert result["question_count"] == 2 and result["active_questions"] == 1
    assert result["subject_count"] == 2 and result["active_subjects"] == 1
    assert len(result["recent_exams"]) == 5 and len(result["recent_actions"]) == 5
    assert all(action["actor_name"] == "Admin" for action in result["recent_actions"])
    serialized = str(result)
    for private in [
        "is_correct",
        "accepted_answers",
        "PRIVATE QUESTION PROMPT",
        question["prompt"],
        "csrf_token",
        "father_name",
    ]:
        assert private not in serialized
    assert client.get("/api/admin/actions").json()[0]["actor_name"] == "Admin"


def test_create_search_filters_and_actions(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    candidate = create(
        client, admin_headers, "candidates", registration(email=" APPROVED@GMAIL.COM ")
    )
    assert candidate["email"] == "approved@gmail.com"
    assert candidate["full_name"] == "محمد احمد"
    assert (
        client.get("/api/admin/candidates", params={"search": "CCK-201"}).json()[0]["id"]
        == candidate["id"]
    )
    assert client.get("/api/admin/candidates", params={"search": "%"}).json() == []
    assert client.get("/api/admin/candidates", params={"status": "DISABLED"}).json() == []
    assert client.get("/api/admin/candidates", params={"offset": 1, "limit": 1}).json() == []
    assert client.get("/api/admin/candidates", params={"limit": 101}).status_code == 422
    action = client.get("/api/admin/actions").json()[0]
    assert action["event_type"] == "CANDIDATE_CREATED"
    assert action["entity_id"] == candidate["id"]
    assert "email" not in action and "metadata" not in action


@pytest.mark.parametrize("change", ["origin", "csrf", "role"])
def test_creation_checks_origin_csrf_and_shape(
    client: TestClient, admin_headers: dict[str, str], change: str
) -> None:
    headers = dict(admin_headers)
    body = registration()
    if change == "origin":
        headers["Origin"] = "https://evil.example"
    elif change == "csrf":
        headers.pop("X-CSRF-Token")
    else:
        body["role"] = "ADMIN"
    assert client.post("/api/admin/candidates", json=body, headers=headers).status_code == (
        422 if change == "role" else 403
    )
    assert client.get("/api/admin/candidates").json() == []


def test_import_atomic_duplicate_and_audit_rollback(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    before = len(client.get("/api/admin/actions").json())
    rows = [registration(), registration("CCK-202", "APPROVED@gmail.com")]
    result = client.post(
        "/api/admin/candidates/import", json={"candidates": rows}, headers=admin_headers
    )
    assert result.status_code == 409
    assert client.get("/api/admin/candidates").json() == []
    assert len(client.get("/api/admin/actions").json()) == before
    rows[1]["email"] = "second@gmail.com"
    result = client.post(
        "/api/admin/candidates/import", json={"candidates": rows}, headers=admin_headers
    )
    assert result.status_code == 201 and len(result.json()) == 2
    assert len(client.get("/api/admin/actions").json()) == before + 2


def test_import_invalid_row_and_limit_preserve_records(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    rows = [registration(), {**registration("CCK-202", "second@gmail.com"), "email": "invalid"}]
    assert (
        client.post(
            "/api/admin/candidates/import", json={"candidates": rows}, headers=admin_headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/admin/candidates/import",
            json={"candidates": [registration()] * 501},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert client.get("/api/admin/candidates").json() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "new@gmail.com"),
        ("google_subject", "independently-verified-new-sub"),
        ("status", "DISABLED"),
        ("full_name", "Updated Candidate Name"),
        ("father_name", "Verified Father Name"),
        ("roll_number", "CCK-REASSIGNED"),
    ],
)
def test_identity_or_eligibility_change_revokes_session(
    client: TestClient,
    application: FastAPI,
    verifier: FakeIdentityVerifier,
    admin_headers: dict[str, str],
    field: str,
    value: str,
) -> None:
    candidate = create(client, admin_headers, "candidates", registration())
    verifier.identity = GoogleIdentity("approved-sub", "approved@gmail.com", True)
    with TestClient(application) as candidate_client:
        assert (
            candidate_client.post(
                "/api/auth/google",
                json={"credential": "test-valid-credential"},
                headers={"Origin": admin_headers["Origin"]},
            ).status_code
            == 200
        )
        assert candidate_client.get("/api/me").status_code == 200
        body = {**registration(), "google_subject": "approved-sub", field: value}
        updated = client.put(
            f"/api/admin/candidates/{candidate['id']}", json=body, headers=admin_headers
        )
        assert updated.status_code == 200
        assert candidate_client.get("/api/me").status_code == 401
        assert client.get("/api/me").status_code == 200


def test_conflicting_identity_edit_preserves_registration(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    first = create(
        client, admin_headers, "candidates", {**registration(), "google_subject": "subject-first"}
    )
    create(
        client,
        admin_headers,
        "candidates",
        {**registration("CCK-202", "second@gmail.com"), "google_subject": "subject-second"},
    )
    result = client.put(
        f"/api/admin/candidates/{first['id']}",
        json={**registration(), "google_subject": "subject-second"},
        headers=admin_headers,
    )
    assert result.status_code == 409
    assert (
        client.get("/api/admin/candidates", params={"search": "CCK-201"}).json()[0][
            "google_subject"
        ]
        == "subject-first"
    )


def test_assignment_filter_and_disabled_candidate(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    candidate = create(client, admin_headers, "candidates", registration())
    exam = create(client, admin_headers, "exams", {"title": "Assigned", "is_published": False})
    path = f"/api/admin/exams/{exam['id']}/candidates/{candidate['id']}"
    assert client.put(path, json={"is_active": True}, headers=admin_headers).status_code == 200
    assert (
        client.get("/api/admin/candidates", params={"exam_id": exam["id"]}).json()[0]["id"]
        == candidate["id"]
    )
    assert (
        client.get(f"/api/admin/candidates/{candidate['id']}/assignments").json()[0]["is_active"]
        is True
    )
    assert client.put(path, json={"is_active": False}, headers=admin_headers).status_code == 200
    assert client.get("/api/admin/candidates", params={"exam_id": exam["id"]}).json() == []
    assert (
        client.put(
            f"/api/admin/candidates/{candidate['id']}",
            json={**registration(), "status": "DISABLED"},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert client.put(path, json={"is_active": True}, headers=admin_headers).status_code == 409


def test_publication_validates_papers_and_start_gate(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject, exam, paper = setup_paper(client, admin_headers)
    publication = f"/api/admin/exams/{exam}/publication"
    assert (
        client.post(publication, json={"published": True}, headers=admin_headers).status_code == 409
    )
    question = create(client, admin_headers, "questions", mcq(subject))
    assert (
        client.put(
            f"/api/admin/exam-subjects/{paper}/questions",
            json={"questions": [{"question_id": question["id"]}]},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(publication, json={"published": True}, headers=admin_headers).status_code == 200
    )
    assert (
        client.post(
            f"/api/admin/exams/{exam}/start-authorization",
            json={"authorized": True},
            headers=admin_headers,
        ).status_code
        == 200
    )
    hidden = client.post(publication, json={"published": False}, headers=admin_headers).json()
    assert hidden["is_published"] is False and hidden["is_start_authorized"] is False
    assert (
        client.post(
            f"/api/admin/exams/{exam}/start-authorization",
            json={"authorized": True},
            headers=admin_headers,
        ).status_code
        == 409
    )
    events = client.get("/api/admin/actions").json()
    assert any(
        event["event_type"] == "CREATE_QUESTION" and event["entity_id"] == question["id"]
        for event in events
    )
    assert any(
        event["event_type"] == "AUTHORIZE" and event["entity_id"] == exam for event in events
    )


def test_subject_order_swap_atomic_and_locked(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    first_subject, exam, first = setup_paper(client, admin_headers)
    second_subject = create(client, admin_headers, "subjects", {"name": "Urdu", "code": "UR"})
    second = create(
        client,
        admin_headers,
        f"exams/{exam}/subjects",
        {"subject_id": second_subject["id"], "duration_minutes": 15, "sequence": 2},
    )
    path = f"/api/admin/exams/{exam}/subject-order"
    result = client.put(path, json={"subject_ids": [second["id"], first]}, headers=admin_headers)
    assert result.status_code == 200
    assert [item["id"] for item in result.json()] == [second["id"], first]
    assert (
        client.put(path, json={"subject_ids": [first, first]}, headers=admin_headers).status_code
        == 422
    )
    assert client.put(path, json={"subject_ids": [first]}, headers=admin_headers).status_code == 409
    for sid, pid in [(first_subject, first), (second_subject["id"], second["id"])]:
        question = create(client, admin_headers, "questions", mcq(sid))
        assert (
            client.put(
                f"/api/admin/exam-subjects/{pid}/questions",
                json={"questions": [{"question_id": question["id"]}]},
                headers=admin_headers,
            ).status_code
            == 200
        )
    assert (
        client.post(
            f"/api/admin/exams/{exam}/start-authorization",
            json={"authorized": True},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert (
        client.put(
            path, json={"subject_ids": [first, second["id"]]}, headers=admin_headers
        ).status_code
        == 409
    )


def test_results_stay_withheld_and_schedule_is_separate(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    exam = create(client, admin_headers, "exams", {"title": "Ungraded", "is_published": False})
    path = f"/api/admin/exams/{exam['id']}/result-release"
    assert client.post(path, json={"released": True}, headers=admin_headers).status_code == 409
    date = datetime(2026, 12, 20, 9, tzinfo=UTC).isoformat()
    result = client.post(
        path, json={"released": False, "result_release_at": date}, headers=admin_headers
    )
    assert result.status_code == 200
    assert result.json()["results_released"] is False
    assert datetime.fromisoformat(result.json()["result_release_at"]) == datetime.fromisoformat(
        date
    )
    assert (
        client.post(
            path,
            json={"released": False, "result_release_at": "2026-12-20T09:00:00"},
            headers=admin_headers,
        ).status_code
        == 422
    )


def test_exam_and_question_search_literals(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    subject, _, _ = setup_paper(client, admin_headers)
    first = create(client, admin_headers, "questions", {**mcq(subject), "prompt": "A 50% question"})
    create(client, admin_headers, "questions", {**mcq(subject), "prompt": "A different question"})
    result = client.get("/api/admin/questions", params={"search": "%", "is_active": True})
    assert [item["id"] for item in result.json()] == [first["id"]]
    assert client.get("/api/admin/exams", params={"search": "missing"}).json() == []
