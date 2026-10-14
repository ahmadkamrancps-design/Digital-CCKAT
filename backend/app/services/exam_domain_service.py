from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AcceptedAnswer,
    AuditEvent,
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamStatus,
    ExamSubject,
    GradingMode,
    Question,
    QuestionOption,
    QuestionType,
    Subject,
)
from app.schemas.exam_domain import (
    AdminQuestionResponse,
    ExamResponse,
    ExamSubjectResponse,
    ExamSubjectWrite,
    ExamWrite,
    GradingConfig,
    MCQWrite,
    OptionResponse,
    PaperQuestionResponse,
    PaperResponse,
    PaperWrite,
    QuestionWrite,
    ShortAnswerWrite,
    SubjectResponse,
    SubjectWrite,
)


def get_record[Model: Base](
    db: Session, model: type[Model], record_id: UUID, *, lock: bool = False
) -> Model:
    record = db.get(model, record_id, with_for_update=lock, populate_existing=lock)
    if record is None:
        raise HTTPException(404, "The requested record was not found.")
    return record


def commit(db: Session) -> None:
    try:
        action = db.info.pop("admin_action", None)
        if action:
            records = list(db.new)
            db.flush()
            actor, event_type, entity_id = action
            if entity_id is None and records:
                entity_id = records[0].id
            if entity_id is not None:
                db.add(AuditEvent(user_id=actor, event_type=event_type, entity_id=entity_id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This change conflicts with existing records.") from exc


def draft_exam(db: Session, exam_id: UUID) -> Exam:
    exam = get_record(db, Exam, exam_id, lock=True)
    if exam.status != ExamStatus.DRAFT:
        raise HTTPException(409, "Archived exams cannot be edited.")
    if exam.is_start_authorized or db.scalar(
        select(ExamAttempt.id).where(ExamAttempt.exam_id == exam.id).limit(1)
    ):
        raise HTTPException(409, "Authorized exams and exams with attempts cannot be edited.")
    return exam


def active_subject(db: Session, subject_id: UUID) -> Subject:
    subject = get_record(db, Subject, subject_id)
    if not subject.is_active:
        raise HTTPException(409, "Choose an active subject.")
    return subject


def subject_response(subject: Subject) -> SubjectResponse:
    return SubjectResponse(
        id=subject.id,
        name=subject.name,
        code=subject.code,
        is_active=subject.is_active,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
    )


def list_subjects(db: Session, limit: int, offset: int) -> list[SubjectResponse]:
    return [
        subject_response(item)
        for item in db.scalars(
            select(Subject).order_by(Subject.code, Subject.id).limit(limit).offset(offset)
        )
    ]


def write_subject(
    db: Session, body: SubjectWrite, subject_id: UUID | None = None
) -> SubjectResponse:
    if subject_id:
        exams = db.scalars(
            select(Exam)
            .join(ExamSubject, ExamSubject.exam_id == Exam.id)
            .where(ExamSubject.subject_id == subject_id)
            .order_by(Exam.id)
            .with_for_update(of=Exam)
        )
        for exam in exams:
            if exam.is_start_authorized or db.scalar(
                select(ExamAttempt.id).where(ExamAttempt.exam_id == exam.id).limit(1)
            ):
                raise HTTPException(
                    409, "Subjects used by authorized exams or attempts cannot be edited."
                )
    subject = get_record(db, Subject, subject_id, lock=True) if subject_id else Subject()
    subject.name, subject.code, subject.is_active = body.name, body.code, body.is_active
    db.add(subject)
    commit(db)
    return subject_response(subject)


def utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # SQLite unit tests omit tzinfo; all writes above normalize to UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def exam_response(exam: Exam, db: Session | None = None) -> ExamResponse:
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        status=exam.status,
        is_start_authorized=exam.is_start_authorized,
        is_published=exam.is_published,
        results_released=exam.results_released,
        result_release_at=utc_timestamp(exam.result_release_at),
        has_attempts=bool(
            db and db.scalar(select(ExamAttempt.id).where(ExamAttempt.exam_id == exam.id).limit(1))
        ),
        scheduled_start=utc_timestamp(exam.scheduled_start),
        scheduled_end=utc_timestamp(exam.scheduled_end),
        created_at=exam.created_at,
        updated_at=exam.updated_at,
    )


def list_exams(db: Session, limit: int, offset: int, search: str = "") -> list[ExamResponse]:
    query = select(Exam).order_by(Exam.created_at, Exam.id)
    if search:
        query = query.where(Exam.title.icontains(search, autoescape=True))
    return [exam_response(item, db) for item in db.scalars(query.limit(limit).offset(offset))]


def write_exam(db: Session, body: ExamWrite, exam_id: UUID | None = None) -> ExamResponse:
    exam = draft_exam(db, exam_id) if exam_id else Exam()
    exam.title, exam.description, exam.status = body.title, body.description, body.status
    exam.is_published = body.is_published
    exam.result_release_at = utc_timestamp(body.result_release_at)
    exam.scheduled_start = body.scheduled_start.astimezone(UTC) if body.scheduled_start else None
    exam.scheduled_end = body.scheduled_end.astimezone(UTC) if body.scheduled_end else None
    db.add(exam)
    commit(db)
    return exam_response(exam, db)


def paper_response(db: Session, exam_subject_id: UUID) -> PaperResponse:
    get_record(db, ExamSubject, exam_subject_id)
    rows = db.execute(
        select(ExamQuestion, Question.marks)
        .join(Question, Question.id == ExamQuestion.question_id)
        .where(ExamQuestion.exam_subject_id == exam_subject_id)
        .order_by(ExamQuestion.sequence)
    ).all()
    questions = [
        PaperQuestionResponse(
            id=item.id,
            question_id=item.question_id,
            sequence=item.sequence,
            marks_override=item.marks_override,
            effective_marks=item.marks_override if item.marks_override is not None else marks,
        )
        for item, marks in rows
    ]
    return PaperResponse(
        exam_subject_id=exam_subject_id,
        questions=questions,
        total_marks=sum((item.effective_marks for item in questions), Decimal(0)),
    )


def exam_subject_response(db: Session, item: ExamSubject) -> ExamSubjectResponse:
    paper = paper_response(db, item.id)
    return ExamSubjectResponse(
        id=item.id,
        exam_id=item.exam_id,
        subject_id=item.subject_id,
        duration_minutes=item.duration_minutes,
        sequence=item.sequence,
        total_marks=paper.total_marks,
        question_count=len(paper.questions),
    )


def list_exam_subjects(db: Session, exam_id: UUID) -> list[ExamSubjectResponse]:
    get_record(db, Exam, exam_id)
    return [
        exam_subject_response(db, item)
        for item in db.scalars(
            select(ExamSubject).where(ExamSubject.exam_id == exam_id).order_by(ExamSubject.sequence)
        )
    ]


def write_exam_subject(
    db: Session, exam_id: UUID, body: ExamSubjectWrite, exam_subject_id: UUID | None = None
) -> ExamSubjectResponse:
    draft_exam(db, exam_id)
    active_subject(db, body.subject_id)
    item = (
        get_record(db, ExamSubject, exam_subject_id)
        if exam_subject_id
        else ExamSubject(exam_id=exam_id)
    )
    if item.exam_id != exam_id:
        raise HTTPException(404, "The requested record was not found.")
    if item.subject_id and item.subject_id != body.subject_id:
        if db.scalar(
            select(ExamQuestion.id).where(ExamQuestion.exam_subject_id == item.id).limit(1)
        ):
            raise HTTPException(409, "Clear this paper before changing its subject.")
    item.subject_id, item.duration_minutes, item.sequence = (
        body.subject_id,
        body.duration_minutes,
        body.sequence,
    )
    db.add(item)
    commit(db)
    return exam_subject_response(db, item)


def remove_exam_subject(db: Session, exam_id: UUID, exam_subject_id: UUID) -> None:
    draft_exam(db, exam_id)
    item = get_record(db, ExamSubject, exam_subject_id)
    if item.exam_id != exam_id:
        raise HTTPException(404, "The requested record was not found.")
    db.delete(item)
    commit(db)  # Restrictive foreign keys reject removal while a paper is attached.


def reorder_subjects(db: Session, exam_id: UUID, ids: list[UUID]) -> list[ExamSubjectResponse]:
    draft_exam(db, exam_id)
    rows = list(db.scalars(select(ExamSubject).where(ExamSubject.exam_id == exam_id)))
    if {row.id for row in rows} != set(ids):
        raise HTTPException(409, "The subject list changed. Reload before reordering.")
    # Temporary positions avoid immediate unique-index collisions during swaps.
    base = max((row.sequence for row in rows), default=0) + 1
    for index, row in enumerate(rows):
        row.sequence = base + index
    db.flush()
    mapping = {row.id: row for row in rows}
    for index, record_id in enumerate(ids):
        mapping[record_id].sequence = index + 1
    commit(db)
    return list_exam_subjects(db, exam_id)


def question_response(db: Session, question: Question) -> AdminQuestionResponse:
    options = [
        OptionResponse(
            id=item.id,
            text=item.option_text,
            display_order=item.display_order,
            is_correct=item.is_correct,
        )
        for item in db.scalars(
            select(QuestionOption)
            .where(QuestionOption.question_id == question.id)
            .order_by(QuestionOption.display_order)
        )
    ]
    answers = list(
        db.scalars(
            select(AcceptedAnswer.accepted_value)
            .where(AcceptedAnswer.question_id == question.id)
            .order_by(AcceptedAnswer.accepted_value)
        )
    )
    grading = (
        TypeAdapter(GradingConfig).validate_python(question.grading_config)
        if question.grading_config is not None
        else None
    )
    return AdminQuestionResponse(
        id=question.id,
        subject_id=question.subject_id,
        type=question.type,
        prompt=question.prompt,
        marks=question.marks,
        direction=question.direction,
        language=question.language,
        is_active=question.is_active,
        options=options,
        grading=grading,
        accepted_answers=answers,
        created_at=question.created_at,
        updated_at=question.updated_at,
    )


def list_questions(
    db: Session,
    limit: int,
    offset: int,
    subject_id: UUID | None,
    question_type: QuestionType | None,
    search: str = "",
    is_active: bool | None = None,
) -> list[AdminQuestionResponse]:
    query = select(Question).order_by(Question.created_at, Question.id)
    if subject_id:
        query = query.where(Question.subject_id == subject_id)
    if question_type:
        query = query.where(Question.type == question_type)
    if search:
        query = query.where(Question.prompt.icontains(search, autoescape=True))
    if is_active is not None:
        query = query.where(Question.is_active.is_(is_active))
    return [question_response(db, item) for item in db.scalars(query.limit(limit).offset(offset))]


def write_question(
    db: Session, body: QuestionWrite, question_id: UUID | None = None
) -> AdminQuestionResponse:
    active_subject(db, body.subject_id)
    question = get_record(db, Question, question_id, lock=True) if question_id else Question()
    if question_id:
        if db.scalar(
            select(ExamQuestion.id).where(ExamQuestion.question_id == question_id).limit(1)
        ):
            raise HTTPException(409, "Remove this question from its papers before editing it.")
        # Delete child keys before changing the parent's type or grading mode.
        db.execute(delete(QuestionOption).where(QuestionOption.question_id == question_id))
        db.execute(delete(AcceptedAnswer).where(AcceptedAnswer.question_id == question_id))
    question.subject_id, question.prompt, question.marks = body.subject_id, body.prompt, body.marks
    question.direction, question.language, question.is_active = (
        body.direction,
        body.language,
        body.is_active,
    )
    question.type = QuestionType(body.type)
    question.grading_mode = (
        GradingMode(body.grading.mode) if isinstance(body, ShortAnswerWrite) else None
    )
    question.grading_config = (
        body.grading.model_dump(mode="json") if isinstance(body, ShortAnswerWrite) else None
    )
    db.add(question)
    db.flush()
    if action := db.info.get("admin_action"):
        db.info["admin_action"] = (action[0], action[1], question.id)
    if isinstance(body, MCQWrite):
        db.add_all(
            [
                QuestionOption(
                    question_id=question.id,
                    option_text=option.text,
                    display_order=index + 1,
                    is_correct=option.is_correct,
                )
                for index, option in enumerate(body.options)
            ]
        )
    else:
        db.add_all(
            [
                AcceptedAnswer(
                    question_id=question.id, grading_mode=body.grading.mode, accepted_value=value
                )
                for value in body.accepted_answers
            ]
        )
    commit(db)
    return question_response(db, question)


def archive_question(db: Session, question_id: UUID) -> AdminQuestionResponse:
    question = get_record(db, Question, question_id, lock=True)
    if db.scalar(select(ExamQuestion.id).where(ExamQuestion.question_id == question_id).limit(1)):
        raise HTTPException(409, "Remove this question from its papers before archiving it.")
    question.is_active = False
    commit(db)
    return question_response(db, question)


def replace_paper(db: Session, exam_subject_id: UUID, body: PaperWrite) -> PaperResponse:
    item = get_record(db, ExamSubject, exam_subject_id)
    draft_exam(db, item.exam_id)
    item = get_record(db, ExamSubject, exam_subject_id, lock=True)
    active_subject(db, item.subject_id)
    # Shared row locks serialize paper attachment against question edits/archival.
    for question_id in sorted(entry.question_id for entry in body.questions):
        question = get_record(db, Question, question_id, lock=True)
        if question.subject_id != item.subject_id or not question.is_active:
            raise HTTPException(409, "Paper questions must be active and match its subject.")
    db.execute(delete(ExamQuestion).where(ExamQuestion.exam_subject_id == item.id))
    db.add_all(
        [
            ExamQuestion(
                exam_subject_id=item.id,
                subject_id=item.subject_id,
                question_id=entry.question_id,
                sequence=index + 1,
                marks_override=entry.marks_override,
            )
            for index, entry in enumerate(body.questions)
        ]
    )
    commit(db)
    return paper_response(db, item.id)
