from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Answer,
    AttemptStatus,
    Exam,
    ExamAttempt,
    ExamQuestion,
    GradingRecord,
    Question,
    SubjectAttempt,
    SubjectStatus,
)
from app.schemas.grading import AttemptResult, SubjectResult
from app.services.auth_service import as_utc


def current_grades(db: Session, answers: list[Answer]) -> dict[UUID, GradingRecord]:
    if not answers:
        return {}
    previous = aliased(GradingRecord)
    latest = (
        select(func.max(previous.revision))
        .where(previous.answer_id == GradingRecord.answer_id)
        .correlate(GradingRecord)
        .scalar_subquery()
    )
    return {
        row.answer_id: row
        for row in db.scalars(
            select(GradingRecord).where(
                GradingRecord.answer_id.in_([answer.id for answer in answers]),
                GradingRecord.revision == latest,
            )
        )
    }


def calculate(db: Session, attempt: ExamAttempt, exam: Exam) -> AttemptResult:
    subjects = list(
        db.scalars(
            select(SubjectAttempt)
            .where(SubjectAttempt.exam_attempt_id == attempt.id)
            .order_by(SubjectAttempt.sequence)
        )
    )
    results: list[SubjectResult] = []
    for subject in subjects:
        entries = db.execute(
            select(ExamQuestion, Question)
            .join(Question, Question.id == ExamQuestion.question_id)
            .where(ExamQuestion.exam_subject_id == subject.exam_subject_id)
        ).all()
        answers = list(db.scalars(select(Answer).where(Answer.subject_attempt_id == subject.id)))
        by_question = {answer.exam_question_id: answer for answer in answers}
        grades = current_grades(db, answers)
        maximum, awarded = Decimal(0), Decimal(0)
        pending = 0 if entries else 1
        closed = subject.status in {SubjectStatus.SUBMITTED, SubjectStatus.EXPIRED}
        for entry, question in entries:
            marks = entry.marks_override if entry.marks_override is not None else question.marks
            maximum += marks
            if not closed:
                pending += 1
                continue
            if subject.started_at is None:
                # The overall exam cutoff can close a paper that was never opened.
                continue
            answer = by_question.get(entry.id)
            grade = grades.get(answer.id) if answer else None
            if (
                not answer
                or not grade
                or grade.answer_revision != answer.revision
                or grade.maximum_marks != marks
            ):
                pending += 1
            else:
                awarded += grade.marks_awarded
        results.append(
            SubjectResult(
                subject_name=subject.subject_name,
                sequence=subject.sequence,
                maximum_marks=maximum,
                marks_awarded=awarded if pending == 0 else None,
                pending_answers=pending,
            )
        )
    complete = (
        bool(results)
        and attempt.status == AttemptStatus.SUBMITTED
        and all(row.pending_answers == 0 for row in results)
    )
    maximum = sum((row.maximum_marks for row in results), Decimal(0))
    total = (
        sum((row.marks_awarded or Decimal(0) for row in results), Decimal(0)) if complete else None
    )
    percentage = (
        (total / maximum * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total is not None and maximum
        else None
    )
    return AttemptResult(
        attempt_id=attempt.id,
        exam_id=exam.id,
        exam_title=exam.title,
        grading_status="COMPLETE" if complete else "PENDING",
        publication_status="WITHHELD",
        subjects=results,
        maximum_marks=maximum,
        marks_awarded=total,
        percentage=percentage,
    )


def validate_release(db: Session, exam: Exam) -> None:
    if exam.is_start_authorized:
        raise HTTPException(409, "Pause new exam starts before releasing results.")
    attempts = list(
        db.scalars(
            select(ExamAttempt)
            .where(ExamAttempt.exam_id == exam.id)
            .order_by(ExamAttempt.id)
            .with_for_update()
        )
    )
    if not attempts:
        raise HTTPException(409, "There are no submitted attempts to release.")
    for attempt in attempts:
        if calculate(db, attempt, exam).grading_status != "COMPLETE":
            raise HTTPException(
                409, "Close all attempts and complete grading before releasing results."
            )


def candidate_result(db: Session, attempt: ExamAttempt, exam: Exam, now: datetime) -> AttemptResult:
    # Callers supply the authoritative server datetime; results are never derived in React.
    result = calculate(db, attempt, exam)
    if exam.results_released and result.grading_status == "COMPLETE":
        result.publication_status = (
            "SCHEDULED"
            if exam.result_release_at and as_utc(exam.result_release_at) > now
            else "RELEASED"
        )
    if result.publication_status != "RELEASED":
        result.subjects = []
        result.maximum_marks = result.marks_awarded = result.percentage = None
    return result
