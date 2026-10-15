"""Automatic scoring uses immutable paper configuration and never edits answers."""

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcceptedAnswer,
    Answer,
    ExamQuestion,
    GradingMode,
    GradingRecord,
    Question,
    QuestionOption,
    QuestionType,
    SubjectAttempt,
    SubjectStatus,
)
from app.schemas.exam_domain import ExactConfig, GradingConfig, NumericConfig

grading_config: TypeAdapter[GradingConfig] = TypeAdapter(GradingConfig)


def numeric(value: str) -> Decimal | None:
    text = value.strip()
    if len(text) > 500 or not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text
    ):
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite() or (result and not -100 <= result.adjusted() <= 100):
        return None
    return result if result else Decimal(0)


def exact(value: str, config: ExactConfig) -> str:
    if config.unicode_normalization == "NFC":
        value = unicodedata.normalize("NFC", value)
    if config.trim_whitespace:
        value = value.strip()
    if config.collapse_whitespace:
        value = " ".join(value.split())
    return value if config.case_sensitive else value.casefold()


def automatic_score(
    answer: Answer, question: Question, keys: list[UUID], values: list[str]
) -> tuple[bool, str] | None:
    if question.type == QuestionType.MCQ:
        if len(keys) != 1:
            return None
        return answer.selected_option_id == keys[0], "MCQ"
    try:
        config = grading_config.validate_python(question.grading_config)
    except ValidationError:
        return None
    if config.mode != question.grading_mode:
        return None
    if not (answer.short_answer_text or "").strip():
        return False, "UNANSWERED"
    if question.grading_mode == GradingMode.MANUAL:
        return None
    if not values:
        return None
    if isinstance(config, ExactConfig):
        return any(
            exact(answer.short_answer_text or "", config) == exact(value, config)
            for value in values
        ), "EXACT"
    if isinstance(config, NumericConfig):
        keys_numeric = [numeric(value) for value in values]
        if any(value is None for value in keys_numeric):
            return None
        supplied = numeric(answer.short_answer_text or "")
        # 500 input digits and bounded adjusted exponents need more than default 28-digit precision.
        with localcontext() as context:
            context.prec = 1024
            correct = supplied is not None and any(
                abs(supplied - value) <= config.absolute_tolerance
                for value in keys_numeric
                if value is not None
            )
        return correct, "NUMERIC"
    return None


def latest_grade(db: Session, answer: Answer) -> GradingRecord | None:
    return db.scalar(
        select(GradingRecord)
        .where(GradingRecord.answer_id == answer.id)
        .order_by(GradingRecord.revision.desc())
        .limit(1)
    )


def grade_closed_subject(db: Session, subject: SubjectAttempt, now: datetime) -> int:
    if subject.status not in {SubjectStatus.SUBMITTED, SubjectStatus.EXPIRED}:
        return 0
    created = 0
    rows = db.execute(
        select(Answer, Question, ExamQuestion)
        .join(Question, Question.id == Answer.question_id)
        .join(ExamQuestion, ExamQuestion.id == Answer.exam_question_id)
        .where(Answer.subject_attempt_id == subject.id)
    ).all()
    if not rows:
        return 0
    # Bulk-load private keys and existing grades; subject submission must not need
    # one extra network round trip per question to retrieve configuration.
    known = set(
        db.scalars(
            select(GradingRecord.answer_id).where(
                GradingRecord.answer_id.in_([answer.id for answer, _, _ in rows])
            )
        )
    )
    ids = [question.id for _, question, _ in rows]
    keys: dict[UUID, list[UUID]] = defaultdict(list)
    accepted: dict[UUID, list[str]] = defaultdict(list)
    for question_id, option_id in db.execute(
        select(QuestionOption.question_id, QuestionOption.id).where(
            QuestionOption.question_id.in_(ids), QuestionOption.is_correct.is_(True)
        )
    ):
        keys[question_id].append(option_id)
    for question_id, value in db.execute(
        select(AcceptedAnswer.question_id, AcceptedAnswer.accepted_value).where(
            AcceptedAnswer.question_id.in_(ids)
        )
    ):
        accepted[question_id].append(value)
    for answer, question, entry in rows:
        if answer.id in known:
            continue
        score = automatic_score(answer, question, keys[question.id], accepted[question.id])
        if score is None:
            # A manual response or invalid configuration remains pending. Closing the
            # exam must succeed even if grading needs administrative attention.
            continue
        correct, method = score
        maximum = entry.marks_override if entry.marks_override is not None else question.marks
        db.add(
            GradingRecord(
                answer_id=answer.id,
                revision=1,
                answer_revision=answer.revision,
                marks_awarded=maximum if correct else Decimal(0),
                maximum_marks=maximum,
                method=method,
                graded_at=now,
            )
        )
        created += 1
    db.flush()
    return created
