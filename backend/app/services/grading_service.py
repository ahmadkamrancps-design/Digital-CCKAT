from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models import (
    Answer,
    AttemptStatus,
    AuditEvent,
    Candidate,
    Exam,
    ExamAttempt,
    ExaminerExamAssignment,
    ExamQuestion,
    GradingMode,
    GradingRecord,
    Question,
    Role,
    SubjectAttempt,
    SubjectStatus,
    User,
)
from app.schemas.grading import (
    ExaminerAssignment,
    ExaminerStaff,
    GradeResponse,
    GradingAttempt,
    GradingExam,
    ManualGradeWrite,
    ManualResponse,
)
from app.services.auth_service import as_utc
from app.services.auto_grading_service import grade_closed_subject, latest_grade
from app.services.exam_domain_service import commit, get_record
from app.services.result_service import calculate, current_grades


def permitted(db: Session, exam_id: UUID, user: User) -> None:
    if user.role == Role.ADMIN:
        return
    grant = db.scalar(
        select(ExaminerExamAssignment.id).where(
            ExaminerExamAssignment.exam_id == exam_id,
            ExaminerExamAssignment.user_id == user.id,
            ExaminerExamAssignment.is_active.is_(True),
        )
    )
    if user.role != Role.EXAMINER or grant is None:
        raise HTTPException(404, "The grading exam was not found.")


def exams(db: Session, user: User, limit: int, offset: int) -> list[GradingExam]:
    query = select(Exam).order_by(Exam.created_at, Exam.id)
    if user.role != Role.ADMIN:
        query = query.join(ExaminerExamAssignment, ExaminerExamAssignment.exam_id == Exam.id).where(
            ExaminerExamAssignment.user_id == user.id, ExaminerExamAssignment.is_active.is_(True)
        )
    return [
        GradingExam(id=row.id, title=row.title, results_released=row.results_released)
        for row in db.scalars(query.limit(limit).offset(offset))
    ]


def staff(db: Session, limit: int, offset: int) -> list[ExaminerStaff]:
    return [
        ExaminerStaff(id=row.id, display_name=row.display_name)
        for row in db.scalars(
            select(User)
            .where(User.role == Role.EXAMINER, User.is_active.is_(True))
            .order_by(User.display_name, User.id)
            .limit(limit)
            .offset(offset)
        )
    ]


def assignments(db: Session, exam_id: UUID) -> list[ExaminerAssignment]:
    get_record(db, Exam, exam_id)
    rows = db.execute(
        select(ExaminerExamAssignment, User)
        .join(User, User.id == ExaminerExamAssignment.user_id)
        .where(ExaminerExamAssignment.exam_id == exam_id)
        .order_by(User.display_name, User.id)
    )
    return [
        ExaminerAssignment(
            user_id=user.id, display_name=user.display_name, is_active=grant.is_active
        )
        for grant, user in rows
    ]


def assign(
    db: Session, exam_id: UUID, user_id: UUID, active: bool, actor: UUID
) -> list[ExaminerAssignment]:
    get_record(db, Exam, exam_id, lock=True)
    user = get_record(db, User, user_id)
    if user.role != Role.EXAMINER or (active and not user.is_active):
        raise HTTPException(409, "Only an active examiner account can be assigned.")
    grant = db.scalar(
        select(ExaminerExamAssignment)
        .where(ExaminerExamAssignment.exam_id == exam_id, ExaminerExamAssignment.user_id == user_id)
        .with_for_update()
    )
    if grant is None:
        grant = ExaminerExamAssignment(exam_id=exam_id, user_id=user_id, assigned_by=actor)
        db.add(grant)
    grant.is_active = active
    db.add(
        AuditEvent(
            user_id=actor,
            event_type="EXAMINER_ASSIGNED" if active else "EXAMINER_REVOKED",
            entity_id=exam_id,
        )
    )
    commit(db)
    return assignments(db, exam_id)


def grade_response(row: GradingRecord) -> GradeResponse:
    return GradeResponse(
        id=row.id,
        answer_id=row.answer_id,
        revision=row.revision,
        marks_awarded=row.marks_awarded,
        maximum_marks=row.maximum_marks,
        method=row.method,
        graded_by=row.graded_by,
        graded_at=as_utc(row.graded_at),
        notes=row.notes,
    )


def attempts(
    db: Session, exam_id: UUID, user: User, limit: int, offset: int
) -> list[GradingAttempt]:
    permitted(db, exam_id, user)
    exam = get_record(db, Exam, exam_id)
    rows = db.execute(
        select(ExamAttempt, Candidate)
        .join(Candidate, Candidate.id == ExamAttempt.candidate_id)
        .where(ExamAttempt.exam_id == exam_id)
        .order_by(Candidate.roll_number, ExamAttempt.id)
        .limit(limit)
        .offset(offset)
    )
    result: list[GradingAttempt] = []
    for attempt, candidate in rows:
        scores = calculate(db, attempt, exam)
        result.append(
            GradingAttempt(
                attempt_id=attempt.id,
                roll_number=candidate.roll_number,
                full_name=candidate.full_name,
                status=attempt.status,
                grading_status=scores.grading_status,
                pending_answers=sum(row.pending_answers for row in scores.subjects),
                marks_awarded=scores.marks_awarded,
                maximum_marks=scores.maximum_marks or Decimal(0),
            )
        )
    return result


def manual_queue(
    db: Session, exam_id: UUID, user: User, include_graded: bool, limit: int, offset: int
) -> list[ManualResponse]:
    permitted(db, exam_id, user)
    # Filter pending in SQL before pagination, so a fully graded first page cannot hide later work.
    query = (
        select(Answer, Question, SubjectAttempt, ExamQuestion)
        .join(Question, Question.id == Answer.question_id)
        .join(SubjectAttempt, SubjectAttempt.id == Answer.subject_attempt_id)
        .join(ExamAttempt, ExamAttempt.id == SubjectAttempt.exam_attempt_id)
        .join(ExamQuestion, ExamQuestion.id == Answer.exam_question_id)
        .where(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == AttemptStatus.SUBMITTED,
            SubjectAttempt.status.in_([SubjectStatus.SUBMITTED, SubjectStatus.EXPIRED]),
            Question.grading_mode == GradingMode.MANUAL,
            Answer.short_answer_text.is_not(None),
        )
    )
    if not include_graded:
        query = query.where(
            ~select(GradingRecord.id).where(GradingRecord.answer_id == Answer.id).exists()
        )
    rows = db.execute(
        query.order_by(SubjectAttempt.id, ExamQuestion.sequence, Answer.id)
        .limit(limit)
        .offset(offset)
    ).all()
    grades = current_grades(db, [answer for answer, _, _, _ in rows])
    return [
        ManualResponse(
            answer_id=answer.id,
            attempt_id=subject.exam_attempt_id,
            subject_name=subject.subject_name,
            question_number=entry.sequence,
            prompt=question.prompt,
            direction=question.direction,
            answer_text=answer.short_answer_text or "",
            maximum_marks=entry.marks_override
            if entry.marks_override is not None
            else question.marks,
            current_grade=grade_response(grades[answer.id]) if answer.id in grades else None,
        )
        for answer, question, subject, entry in rows
    ]


def answer_context(db: Session, answer_id: UUID, user: User) -> tuple[Answer, SubjectAttempt, Exam]:
    initial = get_record(db, Answer, answer_id)
    subject = get_record(db, SubjectAttempt, initial.subject_attempt_id)
    exam = get_record(db, Exam, subject.exam_id, lock=True)
    permitted(db, exam.id, user)
    attempt = get_record(db, ExamAttempt, subject.exam_attempt_id, lock=True)
    subject = get_record(db, SubjectAttempt, subject.id, lock=True)
    answer = get_record(db, Answer, answer_id, lock=True)
    if attempt.status != AttemptStatus.SUBMITTED or subject.status not in {
        SubjectStatus.SUBMITTED,
        SubjectStatus.EXPIRED,
    }:
        raise HTTPException(409, "Only completed exam responses can be reviewed.")
    if get_record(db, Question, answer.question_id).grading_mode != GradingMode.MANUAL:
        raise HTTPException(409, "This response uses automatic grading.")
    return answer, subject, exam


def history(db: Session, answer_id: UUID, user: User) -> list[GradeResponse]:
    answer, _, _ = answer_context(db, answer_id, user)
    return [
        grade_response(row)
        for row in db.scalars(
            select(GradingRecord)
            .where(GradingRecord.answer_id == answer.id)
            .order_by(GradingRecord.revision)
        )
    ]


def manual_grade(
    db: Session, answer_id: UUID, user: User, body: ManualGradeWrite, clock: Clock
) -> GradeResponse:
    answer, _, exam = answer_context(db, answer_id, user)
    if exam.results_released:
        raise HTTPException(409, "Withhold results before changing marks.")
    question = get_record(db, Question, answer.question_id)
    entry = get_record(db, ExamQuestion, answer.exam_question_id)
    maximum = entry.marks_override if entry.marks_override is not None else question.marks
    if body.marks_awarded > maximum:
        raise HTTPException(422, "Marks exceed the maximum for this question.")
    previous = latest_grade(db, answer)
    revision = previous.revision if previous else 0
    if body.expected_revision != revision:
        if (
            previous
            and revision == body.expected_revision + 1
            and previous.graded_by == user.id
            and previous.marks_awarded == body.marks_awarded
            and previous.notes == body.notes
        ):
            return grade_response(previous)
        raise HTTPException(409, "This grade changed. Reload the response before saving.")
    if previous and not body.notes.strip():
        raise HTTPException(422, "Explain the reason for changing an existing grade.")
    row = GradingRecord(
        answer_id=answer.id,
        revision=revision + 1,
        answer_revision=answer.revision,
        marks_awarded=body.marks_awarded,
        maximum_marks=maximum,
        method="MANUAL",
        graded_by=user.id,
        graded_at=clock.now(db),
        notes=body.notes,
    )
    db.add(row)
    db.flush()
    db.add(AuditEvent(user_id=user.id, event_type="MANUAL_GRADE_RECORDED", entity_id=row.id))
    commit(db)
    return grade_response(row)


def grade_attempt(db: Session, attempt_id: UUID, actor: User, clock: Clock) -> int:
    initial = get_record(db, ExamAttempt, attempt_id)
    exam = get_record(db, Exam, initial.exam_id, lock=True)
    if exam.results_released:
        raise HTTPException(409, "Withhold results before running grading.")
    attempt = get_record(db, ExamAttempt, attempt_id, lock=True)
    if attempt.status != AttemptStatus.SUBMITTED:
        raise HTTPException(409, "Complete this exam attempt before grading.")
    subjects = db.scalars(
        select(SubjectAttempt)
        .where(SubjectAttempt.exam_attempt_id == attempt.id)
        .order_by(SubjectAttempt.id)
        .with_for_update()
    )
    count = sum(grade_closed_subject(db, subject, clock.now(db)) for subject in subjects)
    if count:
        db.add(
            AuditEvent(user_id=actor.id, event_type="AUTOMATIC_GRADING_RUN", entity_id=attempt.id)
        )
    commit(db)
    return count
