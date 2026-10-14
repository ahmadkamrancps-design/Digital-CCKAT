from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    AuthSession,
    Candidate,
    CandidateExamAssignment,
    CandidateStatus,
    Exam,
    ExamStatus,
    Role,
    User,
)
from app.schemas.admin_management import CandidateResponse, CandidateWrite, StaffActionResponse
from app.schemas.attempt import AssignmentResponse
from app.schemas.exam_domain import ExamResponse
from app.services.attempt_service import assignment_response, validate_papers
from app.services.exam_domain_service import commit, exam_response, get_record, utc_timestamp


def record_action(db: Session, actor_id: UUID, event_type: str, entity_id: UUID) -> None:
    db.add(AuditEvent(user_id=actor_id, event_type=event_type, entity_id=entity_id))


def candidate_response(candidate: Candidate, user: User) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        user_id=user.id,
        email=user.email,
        full_name=candidate.full_name,
        roll_number=candidate.roll_number,
        google_subject=user.google_subject,
        status=candidate.status,
        is_active=user.is_active,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def list_candidates(
    db: Session,
    limit: int,
    offset: int,
    search: str,
    status: CandidateStatus | None,
    exam_id: UUID | None,
) -> list[CandidateResponse]:
    query = select(Candidate, User).join(User, User.id == Candidate.user_id)
    if search:
        query = query.where(
            or_(
                Candidate.full_name.icontains(search, autoescape=True),
                Candidate.roll_number.icontains(search, autoescape=True),
                User.email.icontains(search, autoescape=True),
            )
        )
    if status:
        query = query.where(Candidate.status == status)
    if exam_id:
        query = query.join(
            CandidateExamAssignment, CandidateExamAssignment.candidate_id == Candidate.id
        ).where(
            CandidateExamAssignment.exam_id == exam_id, CandidateExamAssignment.is_active.is_(True)
        )
    rows = db.execute(
        query.order_by(Candidate.roll_number, Candidate.id).limit(limit).offset(offset)
    )
    return [candidate_response(candidate, user) for candidate, user in rows]


def write_candidate(
    db: Session,
    body: CandidateWrite,
    actor_id: UUID,
    candidate_id: UUID | None = None,
    *,
    commit_now: bool = True,
) -> CandidateResponse:
    if candidate_id:
        initial = get_record(db, Candidate, candidate_id)
        # Match authentication's user lock order; changing identity revokes old sessions.
        user = get_record(db, User, initial.user_id, lock=True)
        candidate = get_record(db, Candidate, candidate_id, lock=True)
        if user.role != Role.CANDIDATE:
            raise HTTPException(409, "This account is not a candidate account.")
        changed_access = (
            user.email != str(body.email).lower()
            or user.google_subject != body.google_subject
            or candidate.status != body.status
        )
    else:
        user = User(role=Role.CANDIDATE)
        candidate = Candidate()
        changed_access = False
        db.add(user)
    user.email, user.display_name, user.google_subject = (
        str(body.email).lower(),
        body.full_name,
        body.google_subject,
    )
    user.is_active = body.status == CandidateStatus.APPROVED
    try:
        db.flush()
        candidate.user_id, candidate.full_name, candidate.roll_number, candidate.status = (
            user.id,
            body.full_name,
            body.roll_number,
            body.status,
        )
        db.add(candidate)
        db.flush()
    except IntegrityError as cause:
        db.rollback()
        raise HTTPException(
            409,
            "Email, roll number, or Google identity conflicts with an existing account. "
            "No candidates were saved.",
        ) from cause
    if changed_access:
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    record_action(
        db, actor_id, "CANDIDATE_UPDATED" if candidate_id else "CANDIDATE_CREATED", candidate.id
    )
    if commit_now:
        commit(db)
    return candidate_response(candidate, user)


def import_candidates(
    db: Session, entries: list[CandidateWrite], actor_id: UUID
) -> list[CandidateResponse]:
    # One transaction, including action records. A late duplicate rolls back the entire import.
    results = [write_candidate(db, entry, actor_id, commit_now=False) for entry in entries]
    commit(db)
    return results


def assignments(db: Session, candidate_id: UUID) -> list[AssignmentResponse]:
    get_record(db, Candidate, candidate_id)
    return [
        assignment_response(row)
        for row in db.scalars(
            select(CandidateExamAssignment)
            .where(CandidateExamAssignment.candidate_id == candidate_id)
            .order_by(CandidateExamAssignment.exam_id)
        )
    ]


def publish_exam(db: Session, exam_id: UUID, published: bool, actor_id: UUID) -> ExamResponse:
    exam = get_record(db, Exam, exam_id, lock=True)
    if published:
        if exam.status != ExamStatus.DRAFT:
            raise HTTPException(409, "Archived exams cannot be published.")
        validate_papers(db, exam.id)
    else:
        exam.is_start_authorized = False
    exam.is_published = published
    record_action(db, actor_id, "EXAM_PUBLISHED" if published else "EXAM_UNPUBLISHED", exam.id)
    commit(db)
    return exam_response(exam, db)


def release_results(
    db: Session, exam_id: UUID, released: bool, actor_id: UUID, release_at: datetime | None = None
) -> ExamResponse:
    exam = get_record(db, Exam, exam_id, lock=True)
    if released:
        raise HTTPException(
            409,
            "Results cannot be released until grading is implemented and verified in Milestone 8.",
        )
    exam.results_released = False
    exam.result_release_at = utc_timestamp(release_at)
    record_action(db, actor_id, "RESULTS_WITHHELD", exam.id)
    commit(db)
    return exam_response(exam, db)


def actions(db: Session, limit: int, offset: int) -> list[StaffActionResponse]:
    return [
        StaffActionResponse(
            id=row.id,
            user_id=row.user_id,
            event_type=row.event_type,
            entity_id=row.entity_id,
            server_timestamp=row.server_timestamp,
        )
        for row in db.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.server_timestamp.desc(), AuditEvent.id)
            .limit(limit)
            .offset(offset)
        )
    ]
