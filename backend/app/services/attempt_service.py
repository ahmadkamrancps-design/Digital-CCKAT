from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models import (
    Answer,
    AttemptStatus,
    Candidate,
    CandidateExamAssignment,
    CandidateStatus,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamStatus,
    ExamSubject,
    Question,
    QuestionOption,
    QuestionType,
    Role,
    SessionEventType,
    Subject,
    SubjectAttempt,
    SubjectStatus,
    User,
)
from app.schemas.attempt import (
    AnswerResponse,
    AnswerSaveResponse,
    AnswerWrite,
    AssignedExamResponse,
    AssignedSubjectResponse,
    AssignmentResponse,
    AttemptResponse,
    CandidateOption,
    CandidateQuestion,
    StartAuthorizationResponse,
    SubjectAttemptResponse,
    SubjectPaperResponse,
)
from app.schemas.exam_domain import QuestionWrite
from app.services.auth_service import as_utc
from app.services.auto_grading_service import grade_closed_subject
from app.services.exam_domain_service import commit, get_record, question_response
from app.services.session_event_service import record_event

TERMINAL = {SubjectStatus.SUBMITTED, SubjectStatus.EXPIRED}


def time_or_none(value: datetime | None) -> datetime | None:
    return as_utc(value) if value else None


def subject_response(subject: SubjectAttempt) -> SubjectAttemptResponse:
    return SubjectAttemptResponse(
        id=subject.id,
        exam_subject_id=subject.exam_subject_id,
        subject_name=subject.subject_name,
        sequence=subject.sequence,
        duration_minutes=subject.duration_minutes,
        status=subject.status,
        started_at=time_or_none(subject.started_at),
        expires_at=time_or_none(subject.expires_at),
        submitted_at=time_or_none(subject.submitted_at),
    )


def attempt_response(
    attempt: ExamAttempt, subjects: list[SubjectAttempt], now: datetime
) -> AttemptResponse:
    return AttemptResponse(
        id=attempt.id,
        exam_id=attempt.exam_id,
        status=attempt.status,
        started_at=as_utc(attempt.started_at),
        submitted_at=time_or_none(attempt.submitted_at),
        server_time=now,
        subjects=[subject_response(item) for item in subjects],
    )


def assignment_response(item: CandidateExamAssignment) -> AssignmentResponse:
    return AssignmentResponse(
        id=item.id,
        candidate_id=item.candidate_id,
        exam_id=item.exam_id,
        is_active=item.is_active,
        assigned_by=item.assigned_by,
    )


def assign_candidate(
    db: Session, exam_id: UUID, candidate_id: UUID, admin_id: UUID, active: bool
) -> AssignmentResponse:
    # Lock a stable parent to serialize first assignment creation as well as retries.
    get_record(db, Exam, exam_id, lock=True)
    candidate = get_record(db, Candidate, candidate_id)
    user = get_record(db, User, candidate.user_id)
    if active and (
        candidate.status != CandidateStatus.APPROVED
        or not user.is_active
        or user.role != Role.CANDIDATE
    ):
        raise HTTPException(409, "Only an approved candidate can be assigned.")
    item = db.scalar(
        select(CandidateExamAssignment)
        .where(
            CandidateExamAssignment.exam_id == exam_id,
            CandidateExamAssignment.candidate_id == candidate_id,
        )
        .with_for_update()
    )
    if item is None:
        item = CandidateExamAssignment(
            exam_id=exam_id, candidate_id=candidate_id, assigned_by=admin_id
        )
        db.add(item)
    item.is_active = active
    commit(db)
    return assignment_response(item)


def validate_papers(db: Session, exam_id: UUID) -> list[ExamSubject]:
    papers = list(
        db.scalars(
            select(ExamSubject).where(ExamSubject.exam_id == exam_id).order_by(ExamSubject.sequence)
        )
    )
    if not papers:
        raise HTTPException(409, "Configure at least one subject before authorizing start.")
    catalog = {
        item.id: item
        for item in db.scalars(
            select(Subject)
            .where(Subject.id.in_([paper.subject_id for paper in papers]))
            .order_by(Subject.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    for paper in papers:
        subject = catalog[paper.subject_id]
        if not subject.is_active:
            raise HTTPException(409, "Exam subjects must be active.")
        questions = list(
            db.scalars(
                select(Question)
                .join(ExamQuestion, ExamQuestion.question_id == Question.id)
                .where(ExamQuestion.exam_subject_id == paper.id)
                .order_by(ExamQuestion.sequence)
            )
        )
        if not questions:
            raise HTTPException(409, "Every subject needs a nonempty paper.")
        for question in questions:
            if not question.is_active:
                raise HTTPException(409, "Paper questions must be active.")
            try:
                data = question_response(db, question).model_dump(
                    mode="json", exclude={"id", "created_at", "updated_at"}
                )
                if question.type == QuestionType.MCQ:
                    data.pop("grading")
                    data.pop("accepted_answers")
                    data["options"] = [
                        {"text": item["text"], "is_correct": item["is_correct"]}
                        for item in data["options"]
                    ]
                else:
                    data.pop("options")
                TypeAdapter(QuestionWrite).validate_python(data)
            except ValidationError as exc:
                raise HTTPException(409, "A paper question has invalid configuration.") from exc
    return papers


def authorize_start(db: Session, exam_id: UUID, authorized: bool) -> StartAuthorizationResponse:
    exam = get_record(db, Exam, exam_id, lock=True)
    if authorized:
        if exam.results_released:
            raise HTTPException(409, "Withhold results before enabling exam starts.")
        if not exam.is_published:
            raise HTTPException(409, "Publish this exam before authorizing starts.")
        if exam.status != ExamStatus.DRAFT:
            raise HTTPException(409, "Archived exams cannot be started.")
        validate_papers(db, exam_id)
    exam.is_start_authorized = authorized
    commit(db)
    return StartAuthorizationResponse(exam_id=exam.id, is_start_authorized=exam.is_start_authorized)


def assignment_for(db: Session, exam_id: UUID, candidate_id: UUID) -> CandidateExamAssignment:
    item = db.scalar(
        select(CandidateExamAssignment)
        .where(
            CandidateExamAssignment.exam_id == exam_id,
            CandidateExamAssignment.candidate_id == candidate_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None or not item.is_active:
        raise HTTPException(403, "You are not assigned to this exam.")
    return item


def owned_attempt(db: Session, attempt_id: UUID, candidate_id: UUID) -> ExamAttempt:
    item = get_record(db, ExamAttempt, attempt_id)
    if item.candidate_id != candidate_id:
        raise HTTPException(404, "The requested attempt was not found.")
    assignment_for(db, item.exam_id, candidate_id)
    return get_record(db, ExamAttempt, attempt_id, lock=True)


def reconcile(
    db: Session, attempt: ExamAttempt, clock: Clock
) -> tuple[list[SubjectAttempt], datetime]:
    subjects = list(
        db.scalars(
            select(SubjectAttempt)
            .where(SubjectAttempt.exam_attempt_id == attempt.id)
            .order_by(SubjectAttempt.sequence)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    now = clock.now(db)  # Read after locks: transaction-start time can be stale after waiting.
    exam = get_record(db, Exam, attempt.exam_id)
    end = time_or_none(exam.scheduled_end)
    for subject in subjects:
        if (
            subject.status == SubjectStatus.ACTIVE
            and subject.expires_at
            and as_utc(subject.expires_at) <= now
        ):
            subject.status = SubjectStatus.EXPIRED
            subject.submitted_at = subject.expires_at
            record_event(db, attempt, SessionEventType.SUBJECT_AUTO_SUBMITTED, now, subject)
            grade_closed_subject(db, subject, now)
        elif subject.status == SubjectStatus.NOT_STARTED and end and end <= now:
            # The overall deadline closes papers the candidate never started, too.
            subject.status = SubjectStatus.EXPIRED
            subject.expires_at = end
            subject.submitted_at = end
            record_event(db, attempt, SessionEventType.SUBJECT_AUTO_SUBMITTED, now, subject)
    finalize(db, attempt, subjects, now)
    return subjects, now


def finalize(
    db: Session, attempt: ExamAttempt, subjects: list[SubjectAttempt], now: datetime
) -> None:
    if (
        attempt.status == AttemptStatus.IN_PROGRESS
        and subjects
        and all(item.status in TERMINAL for item in subjects)
    ):
        attempt.status = AttemptStatus.SUBMITTED
        attempt.submitted_at = max(
            as_utc(item.submitted_at) for item in subjects if item.submitted_at
        )
        record_event(db, attempt, SessionEventType.EXAM_SUBMITTED, now)


def check_start(exam: Exam, now: datetime) -> None:
    if (
        not exam.is_published
        or not exam.is_start_authorized
        or exam.results_released
        or exam.status != ExamStatus.DRAFT
    ):
        raise HTTPException(403, "This exam is not authorized to start.")
    if exam.scheduled_start and as_utc(exam.scheduled_start) > now:
        raise HTTPException(409, "The exam has not opened yet.")
    if exam.scheduled_end and as_utc(exam.scheduled_end) <= now:
        raise HTTPException(410, "The exam window has closed.")


def begin_exam(db: Session, exam_id: UUID, candidate_id: UUID, clock: Clock) -> AttemptResponse:
    exam = get_record(db, Exam, exam_id, lock=True)
    assignment = assignment_for(db, exam_id, candidate_id)
    attempt = db.scalar(
        select(ExamAttempt).where(ExamAttempt.assignment_id == assignment.id).with_for_update()
    )
    if attempt is None:
        now = clock.now(db)
        check_start(exam, now)
        papers = validate_papers(db, exam_id)
        attempt = ExamAttempt(
            assignment_id=assignment.id, candidate_id=candidate_id, exam_id=exam_id, started_at=now
        )
        db.add(attempt)
        db.flush()
        record_event(db, attempt, SessionEventType.EXAM_OPENED, now)
        db.add_all(
            [
                SubjectAttempt(
                    exam_attempt_id=attempt.id,
                    exam_id=exam_id,
                    exam_subject_id=paper.id,
                    subject_name=get_record(db, Subject, paper.subject_id).name,
                    sequence=paper.sequence,
                    duration_minutes=paper.duration_minutes,
                )
                for paper in papers
            ]
        )
        db.flush()
    subjects, now = reconcile(db, attempt, clock)
    commit(db)
    return attempt_response(attempt, subjects, now)


def resume_exam(db: Session, attempt_id: UUID, candidate_id: UUID, clock: Clock) -> AttemptResponse:
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    commit(db)
    return attempt_response(attempt, subjects, now)


def find_subject(subjects: list[SubjectAttempt], subject_id: UUID) -> SubjectAttempt:
    subject = next((item for item in subjects if item.id == subject_id), None)
    if subject is None:
        raise HTTPException(404, "The requested subject attempt was not found.")
    return subject


def begin_subject(
    db: Session, attempt_id: UUID, subject_id: UUID, candidate_id: UUID, clock: Clock
) -> AttemptResponse:
    initial = get_record(db, ExamAttempt, attempt_id)
    if initial.candidate_id != candidate_id:
        raise HTTPException(404, "The requested attempt was not found.")
    exam = get_record(db, Exam, initial.exam_id, lock=True)
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    subject = find_subject(subjects, subject_id)
    if subject.status == SubjectStatus.NOT_STARTED:
        try:
            check_start(exam, now)
            if any(
                item.sequence < subject.sequence and item.status not in TERMINAL
                for item in subjects
            ):
                raise HTTPException(409, "Finish the earlier subject first.")
        except HTTPException:
            commit(db)
            raise
        subject.status, subject.started_at = SubjectStatus.ACTIVE, now
        subject.expires_at = now + timedelta(minutes=subject.duration_minutes)
        if exam.scheduled_end:
            subject.expires_at = min(subject.expires_at, as_utc(exam.scheduled_end))
        record_event(db, attempt, SessionEventType.SUBJECT_STARTED, now, subject)
        papers = list(
            db.execute(
                select(ExamQuestion, Question.type)
                .join(Question, Question.id == ExamQuestion.question_id)
                .where(ExamQuestion.exam_subject_id == subject.exam_subject_id)
            ).all()
        )
        db.add_all(
            [
                Answer(
                    subject_attempt_id=subject.id,
                    exam_subject_id=subject.exam_subject_id,
                    exam_question_id=paper.id,
                    question_id=paper.question_id,
                    question_type=question_type.value,
                )
                for paper, question_type in papers
            ]
        )
    commit(db)
    return attempt_response(attempt, subjects, now)


def answer_response(answer: Answer) -> AnswerResponse:
    return AnswerResponse(
        exam_question_id=answer.exam_question_id,
        selected_option_id=answer.selected_option_id,
        short_answer_text=answer.short_answer_text,
        is_marked_for_review=answer.is_marked_for_review,
        revision=answer.revision,
        last_saved_at=time_or_none(answer.last_saved_at),
    )


def subject_paper(
    db: Session, attempt_id: UUID, subject_id: UUID, candidate_id: UUID, clock: Clock
) -> SubjectPaperResponse:
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    subject = find_subject(subjects, subject_id)
    commit(db)
    if subject.started_at is None:
        raise HTTPException(409, "This subject has not been started.")
    rows = db.execute(
        select(ExamQuestion, Question, Answer)
        .join(Question, Question.id == ExamQuestion.question_id)
        .join(Answer, Answer.exam_question_id == ExamQuestion.id)
        .where(Answer.subject_attempt_id == subject.id)
        .order_by(ExamQuestion.sequence)
    ).all()
    # Explicit allowlist: never return ORM question/key/grading objects to candidates.
    questions = [
        CandidateQuestion(
            exam_question_id=paper.id,
            question_id=question.id,
            type=question.type,
            prompt=question.prompt,
            direction=question.direction,
            language=question.language,
            marks=paper.marks_override if paper.marks_override is not None else question.marks,
            sequence=paper.sequence,
            options=[
                CandidateOption(id=option.id, text=option.option_text)
                for option in db.scalars(
                    select(QuestionOption)
                    .where(QuestionOption.question_id == question.id)
                    .order_by(QuestionOption.display_order)
                )
            ],
            answer=answer_response(answer),
        )
        for paper, question, answer in rows
    ]
    return SubjectPaperResponse(
        subject=subject_response(subject), server_time=now, questions=questions
    )


def save_answer(
    db: Session,
    attempt_id: UUID,
    subject_id: UUID,
    exam_question_id: UUID,
    candidate_id: UUID,
    body: AnswerWrite,
    clock: Clock,
) -> AnswerSaveResponse:
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    subject = find_subject(subjects, subject_id)
    if subject.status != SubjectStatus.ACTIVE:
        commit(db)  # Expiry must survive a rejected late write.
        raise HTTPException(
            410 if subject.status in TERMINAL else 409, "This subject is not editable."
        )
    answer = db.scalar(
        select(Answer).where(
            Answer.subject_attempt_id == subject.id, Answer.exam_question_id == exam_question_id
        )
    )
    if answer is None:
        raise HTTPException(404, "The requested question was not found in this subject.")
    if (answer.question_type == "MCQ" and body.short_answer_text is not None) or (
        answer.question_type == "SHORT_ANSWER" and body.selected_option_id is not None
    ):
        raise HTTPException(422, "The answer does not match this question type.")
    if body.selected_option_id:
        option = db.get(QuestionOption, body.selected_option_id)
        if option is None or option.question_id != answer.question_id:
            raise HTTPException(422, "Choose an option from this question.")
    now = clock.now(db)
    if subject.expires_at and as_utc(subject.expires_at) <= now:
        subject.status, subject.submitted_at = SubjectStatus.EXPIRED, subject.expires_at
        record_event(db, attempt, SessionEventType.SUBJECT_AUTO_SUBMITTED, now, subject)
        finalize(db, attempt, subjects, now)
        commit(db)
        raise HTTPException(410, "This subject is not editable.")
    same = (
        answer.selected_option_id == body.selected_option_id
        and answer.short_answer_text == body.short_answer_text
        and answer.is_marked_for_review == body.is_marked_for_review
    )
    if body.expected_revision != answer.revision and not (
        same and body.expected_revision < answer.revision
    ):
        raise HTTPException(
            409,
            {
                "message": "This answer changed. Use the current revision before retrying.",
                "current_answer": answer_response(answer).model_dump(mode="json"),
            },
        )
    if not same:
        if answer.is_marked_for_review != body.is_marked_for_review:
            record_event(
                db,
                attempt,
                SessionEventType.QUESTION_FLAGGED
                if body.is_marked_for_review
                else SessionEventType.QUESTION_UNFLAGGED,
                now,
                subject,
            )
        answer.selected_option_id, answer.short_answer_text = (
            body.selected_option_id,
            body.short_answer_text,
        )
        answer.is_marked_for_review = body.is_marked_for_review
        answer.revision += 1
        answer.last_saved_at = now
        record_event(db, attempt, SessionEventType.ANSWER_SAVED, now, subject)
    commit(db)
    return AnswerSaveResponse(answer=answer_response(answer), server_time=now)


def submit_subject(
    db: Session, attempt_id: UUID, subject_id: UUID, candidate_id: UUID, clock: Clock
) -> AttemptResponse:
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    subject = find_subject(subjects, subject_id)
    if subject.status == SubjectStatus.NOT_STARTED:
        raise HTTPException(409, "Start this subject before submitting it.")
    if subject.status == SubjectStatus.ACTIVE:
        subject.status, subject.submitted_at = SubjectStatus.SUBMITTED, now
        record_event(db, attempt, SessionEventType.SUBJECT_SUBMITTED, now, subject)
        grade_closed_subject(db, subject, now)
        finalize(db, attempt, subjects, now)
    commit(db)
    return attempt_response(attempt, subjects, now)


def submit_exam(db: Session, attempt_id: UUID, candidate_id: UUID, clock: Clock) -> AttemptResponse:
    attempt = owned_attempt(db, attempt_id, candidate_id)
    subjects, now = reconcile(db, attempt, clock)
    commit(db)
    if attempt.status != AttemptStatus.SUBMITTED:
        raise HTTPException(409, "Finish all subjects before final submission.")
    return attempt_response(attempt, subjects, now)


def assigned_exams(db: Session, candidate_id: UUID) -> list[AssignedExamResponse]:
    rows = db.execute(
        select(Exam, ExamAttempt.id)
        .join(CandidateExamAssignment, CandidateExamAssignment.exam_id == Exam.id)
        .outerjoin(ExamAttempt, ExamAttempt.assignment_id == CandidateExamAssignment.id)
        .where(
            CandidateExamAssignment.candidate_id == candidate_id,
            CandidateExamAssignment.is_active.is_(True),
            or_(
                and_(Exam.is_published.is_(True), Exam.status == ExamStatus.DRAFT),
                ExamAttempt.id.is_not(None),
            ),
        )
        .order_by(Exam.created_at, Exam.id)
    ).all()
    summaries: dict[UUID, list[AssignedSubjectResponse]] = {exam.id: [] for exam, _ in rows}
    if summaries:
        for paper, name in db.execute(
            select(ExamSubject, Subject.name)
            .join(Subject, Subject.id == ExamSubject.subject_id)
            .where(ExamSubject.exam_id.in_(summaries))
            .order_by(ExamSubject.sequence)
        ):
            summaries[paper.exam_id].append(
                AssignedSubjectResponse(
                    exam_subject_id=paper.id,
                    name=name,
                    duration_minutes=paper.duration_minutes,
                    sequence=paper.sequence,
                )
            )
    return [
        AssignedExamResponse(
            exam_id=exam.id,
            title=exam.title,
            is_start_authorized=exam.is_start_authorized,
            scheduled_start=time_or_none(exam.scheduled_start),
            scheduled_end=time_or_none(exam.scheduled_end),
            attempt_id=attempt_id,
            subjects=summaries[exam.id],
        )
        for exam, attempt_id in rows
    ]


def expire_due(db: Session, clock: Clock, limit: int = 100) -> int:
    now = clock.now(db)
    active_due = (
        select(SubjectAttempt.id)
        .where(
            SubjectAttempt.exam_attempt_id == ExamAttempt.id,
            SubjectAttempt.status == SubjectStatus.ACTIVE,
            SubjectAttempt.expires_at <= now,
        )
        .exists()
    )
    window_due = (
        select(Exam.id).where(Exam.id == ExamAttempt.exam_id, Exam.scheduled_end <= now).exists()
    )
    attempts = list(
        db.scalars(
            select(ExamAttempt)
            .where(ExamAttempt.status == AttemptStatus.IN_PROGRESS, or_(active_due, window_due))
            .order_by(ExamAttempt.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for attempt in attempts:
        reconcile(db, attempt, clock)
    commit(db)
    return len(attempts)
