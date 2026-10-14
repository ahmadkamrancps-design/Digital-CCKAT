from math import ceil
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models import (
    AttemptPresence,
    AttemptStatus,
    Candidate,
    CandidateExamAssignment,
    CandidateStatus,
    EventSource,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ProctorExamAssignment,
    Role,
    SessionEvent,
    SessionEventType,
    SubjectAttempt,
    SubjectStatus,
    User,
)
from app.schemas.proctor import (
    MonitoredCandidate,
    MonitoredExam,
    MonitoringResponse,
    PresenceResponse,
    PresenceWrite,
    ProctorAssignmentResponse,
    ProctorStaff,
    SessionEventResponse,
)
from app.services import attempt_service
from app.services.admin_management_service import record_action
from app.services.auth_service import as_utc
from app.services.exam_domain_service import commit, get_record

REVIEW_TYPES = (
    SessionEventType.CONNECTION_LOST,
    SessionEventType.VISIBILITY_HIDDEN,
    SessionEventType.FULLSCREEN_EXIT,
)
CONTACT_SECONDS = 30


def permitted(db: Session, exam_id: UUID, user: User) -> None:
    if user.role == Role.ADMIN:
        get_record(db, Exam, exam_id)
        return
    allowed = db.scalar(
        select(ProctorExamAssignment.id).where(
            ProctorExamAssignment.exam_id == exam_id,
            ProctorExamAssignment.user_id == user.id,
            ProctorExamAssignment.is_active.is_(True),
        )
    )
    if user.role != Role.PROCTOR or not allowed:
        raise HTTPException(404, "The monitored exam was not found.")


def staff(db: Session, limit: int, offset: int) -> list[ProctorStaff]:
    return [
        ProctorStaff(id=user.id, display_name=user.display_name)
        for user in db.scalars(
            select(User)
            .where(User.role == Role.PROCTOR, User.is_active.is_(True))
            .order_by(User.display_name, User.id)
            .limit(limit)
            .offset(offset)
        )
    ]


def assignments(db: Session, exam_id: UUID) -> list[ProctorAssignmentResponse]:
    get_record(db, Exam, exam_id)
    rows = db.execute(
        select(ProctorExamAssignment, User)
        .join(User, User.id == ProctorExamAssignment.user_id)
        .where(ProctorExamAssignment.exam_id == exam_id)
        .order_by(User.display_name, User.id)
    )
    return [
        ProctorAssignmentResponse(
            user_id=user.id,
            display_name=user.display_name,
            is_active=item.is_active,
            user_is_active=user.is_active,
        )
        for item, user in rows
    ]


def assign(
    db: Session, exam_id: UUID, user_id: UUID, active: bool, actor: UUID
) -> list[ProctorAssignmentResponse]:
    get_record(db, Exam, exam_id, lock=True)
    user = get_record(db, User, user_id)
    if user.role != Role.PROCTOR or (active and not user.is_active):
        raise HTTPException(409, "Only an active proctor account can be assigned.")
    item = db.scalar(
        select(ProctorExamAssignment)
        .where(
            ProctorExamAssignment.exam_id == exam_id,
            ProctorExamAssignment.user_id == user_id,
        )
        .with_for_update()
    )
    if item is None:
        item = ProctorExamAssignment(exam_id=exam_id, user_id=user_id, assigned_by=actor)
        db.add(item)
    item.is_active = active
    record_action(db, actor, "PROCTOR_ASSIGNED" if active else "PROCTOR_REVOKED", exam_id)
    commit(db)
    return assignments(db, exam_id)


def exams(db: Session, user: User, limit: int, offset: int) -> list[MonitoredExam]:
    query = select(Exam).order_by(Exam.created_at, Exam.id)
    if user.role == Role.PROCTOR:
        query = query.join(ProctorExamAssignment, ProctorExamAssignment.exam_id == Exam.id).where(
            ProctorExamAssignment.user_id == user.id,
            ProctorExamAssignment.is_active.is_(True),
        )
    return [
        MonitoredExam(
            id=item.id,
            title=item.title,
            is_start_authorized=item.is_start_authorized,
            scheduled_start=attempt_service.time_or_none(item.scheduled_start),
            scheduled_end=attempt_service.time_or_none(item.scheduled_end),
        )
        for item in db.scalars(query.limit(limit).offset(offset))
    ]


def heartbeat(
    db: Session, attempt_id: UUID, candidate_id: UUID, body: PresenceWrite, clock: Clock
) -> PresenceResponse:
    attempt = attempt_service.owned_attempt(db, attempt_id, candidate_id)
    subjects, now = attempt_service.reconcile(db, attempt, clock)
    subject = attempt_service.find_subject(subjects, body.subject_attempt_id)
    if subject.status != SubjectStatus.ACTIVE:
        commit(db)
        raise HTTPException(410, "Monitoring for this subject has closed.")
    count = (
        db.scalar(
            select(func.count())
            .select_from(ExamQuestion)
            .where(
                ExamQuestion.exam_subject_id == subject.exam_subject_id,
            )
        )
        or 0
    )
    if body.question_sequence > count:
        raise HTTPException(422, "The reported position is outside this subject.")
    presence = db.get(AttemptPresence, attempt.id)
    if presence and (now - as_utc(presence.last_seen_at)).total_seconds() < 5:
        raise HTTPException(
            429, "Monitoring updates are arriving too frequently.", headers={"Retry-After": "5"}
        )
    if presence is None:
        presence = AttemptPresence(exam_attempt_id=attempt.id)
        db.add(presence)
    presence.subject_attempt_id, presence.question_sequence, presence.last_seen_at = (
        subject.id,
        body.question_sequence,
        now,
    )
    if body.events:
        received = set(
            db.scalars(
                select(SessionEvent.client_event_id).where(
                    SessionEvent.exam_attempt_id == attempt.id,
                    SessionEvent.client_event_id.in_([item.event_id for item in body.events]),
                )
            )
        )
        db.add_all(
            [
                SessionEvent(
                    exam_attempt_id=attempt.id,
                    subject_attempt_id=subject.id,
                    event_type=SessionEventType(item.event_type),
                    source=EventSource.CLIENT,
                    client_event_id=item.event_id,
                    server_timestamp=now,
                )
                for item in body.events
                if item.event_id not in received
            ]
        )
    commit(db)
    return PresenceResponse(server_time=now)


def sessions(
    db: Session,
    exam_id: UUID,
    user: User,
    clock: Clock,
    limit: int,
    offset: int,
    search: str,
    active_only: bool,
) -> MonitoringResponse:
    permitted(db, exam_id, user)
    now = clock.now(db)
    query = (
        select(CandidateExamAssignment, Candidate, User, ExamAttempt)
        .join(
            Candidate,
            Candidate.id == CandidateExamAssignment.candidate_id,
        )
        .join(User, User.id == Candidate.user_id)
        .outerjoin(
            ExamAttempt,
            ExamAttempt.assignment_id == CandidateExamAssignment.id,
        )
        .where(CandidateExamAssignment.exam_id == exam_id)
    )
    if search:
        query = query.where(
            or_(
                Candidate.full_name.icontains(search, autoescape=True),
                Candidate.roll_number.icontains(search, autoescape=True),
            )
        )
    if active_only:
        query = query.where(
            select(SubjectAttempt.id)
            .where(
                SubjectAttempt.exam_attempt_id == ExamAttempt.id,
                SubjectAttempt.status == SubjectStatus.ACTIVE,
                SubjectAttempt.expires_at > now,
            )
            .exists()
        )
    rows = db.execute(
        query.order_by(Candidate.roll_number, Candidate.id).limit(limit).offset(offset)
    ).all()
    result: list[MonitoredCandidate] = []
    # Lock attempts in a consistent order even if candidate roll numbers change.
    for assignment, candidate, account, attempt in sorted(
        rows, key=lambda row: str(row[3].id) if row[3] else ""
    ):
        subjects: list[SubjectAttempt] = []
        if attempt:
            attempt = get_record(db, ExamAttempt, attempt.id, lock=True)
            subjects, now = attempt_service.reconcile(db, attempt, clock)
        active = next((item for item in subjects if item.status == SubjectStatus.ACTIVE), None)
        current = active or next(
            (item for item in subjects if item.status == SubjectStatus.NOT_STARTED), None
        )
        if current is None and subjects:
            current = subjects[-1]
        presence = db.get(AttemptPresence, attempt.id) if attempt else None
        last_seen = as_utc(presence.last_seen_at) if presence else None
        contact = (
            "UNKNOWN"
            if active is None or last_seen is None
            else (
                "ONLINE"
                if (now - last_seen).total_seconds() <= CONTACT_SECONDS
                else "NO_RECENT_CONTACT"
            )
        )
        state = (
            "NOT_STARTED"
            if attempt is None
            else "SUBMITTED"
            if attempt.status == AttemptStatus.SUBMITTED
            else "TESTING"
            if active
            else "BETWEEN_SUBJECTS"
        )
        count = (
            db.scalar(
                select(func.count())
                .select_from(ExamQuestion)
                .where(ExamQuestion.exam_subject_id == current.exam_subject_id)
            )
            if current
            else 0
        )
        events = (
            db.scalar(
                select(func.count())
                .select_from(SessionEvent)
                .where(
                    SessionEvent.exam_attempt_id == attempt.id,
                    SessionEvent.event_type.in_(REVIEW_TYPES),
                )
            )
            if attempt
            else 0
        )
        expires = as_utc(active.expires_at) if active and active.expires_at else None
        result.append(
            MonitoredCandidate(
                candidate_id=candidate.id,
                roll_number=candidate.roll_number,
                full_name=candidate.full_name,
                access_active=assignment.is_active
                and account.is_active
                and account.role == Role.CANDIDATE
                and candidate.status == CandidateStatus.APPROVED,
                attempt_id=attempt.id if attempt else None,
                state=state,
                subject_attempt_id=current.id if current else None,
                subject_name=current.subject_name if current else None,
                subject_status=current.status if current else None,
                question_count=count or 0,
                reported_question_sequence=presence.question_sequence
                if presence and active and presence.subject_attempt_id == active.id
                else None,
                expires_at=expires,
                remaining_seconds=max(0, ceil((expires - now).total_seconds()))
                if expires
                else None,
                connection=contact,
                last_seen_at=last_seen,
                review_event_count=events or 0,
            )
        )
    commit(db)
    result.sort(key=lambda row: (row.roll_number, str(row.candidate_id)))
    return MonitoringResponse(server_time=now, candidates=result)


def events(
    db: Session, attempt_id: UUID, user: User, limit: int, offset: int
) -> list[SessionEventResponse]:
    exam_id = db.scalar(select(ExamAttempt.exam_id).where(ExamAttempt.id == attempt_id))
    if exam_id is None:
        raise HTTPException(404, "The monitored exam was not found.")
    permitted(db, exam_id, user)
    return [
        SessionEventResponse(
            id=item.id,
            event_type=item.event_type,
            source=item.source,
            subject_attempt_id=item.subject_attempt_id,
            server_timestamp=as_utc(item.server_timestamp),
        )
        for item in db.scalars(
            select(SessionEvent)
            .where(SessionEvent.exam_attempt_id == attempt_id)
            .order_by(SessionEvent.server_timestamp.desc(), SessionEvent.id)
            .limit(limit)
            .offset(offset)
        )
    ]
