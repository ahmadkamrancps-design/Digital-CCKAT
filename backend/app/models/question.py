import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QuestionType(enum.StrEnum):
    MCQ = "MCQ"
    SHORT_ANSWER = "SHORT_ANSWER"


class GradingMode(enum.StrEnum):
    EXACT = "EXACT"
    NUMERIC = "NUMERIC"
    MANUAL = "MANUAL"


class Question(TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("id", "subject_id", name="uq_questions_id_subject"),
        UniqueConstraint("id", "type", name="uq_questions_id_type"),
        UniqueConstraint("id", "grading_mode", name="uq_questions_id_grading"),
        CheckConstraint("length(trim(prompt)) > 0", name="nonempty_prompt"),
        CheckConstraint("marks > 0 AND marks <= 10000", name="marks_range"),
        CheckConstraint("direction IN ('auto', 'ltr', 'rtl')", name="direction"),
        CheckConstraint(
            "(type = 'MCQ' AND grading_mode IS NULL AND grading_config IS NULL) OR "
            "(type = 'SHORT_ANSWER' AND grading_mode IS NOT NULL "
            "AND grading_config IS NOT NULL)",
            name="grading_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, create_constraint=True, name="question_type")
    )
    prompt: Mapped[str] = mapped_column(Text)
    marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    direction: Mapped[str] = mapped_column(String(4), default="auto", server_default="auto")
    language: Mapped[str | None] = mapped_column(String(35))
    grading_mode: Mapped[GradingMode | None] = mapped_column(
        Enum(GradingMode, native_enum=False, create_constraint=True, name="grading_mode")
    )
    grading_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "display_order"),
        UniqueConstraint("id", "question_id", name="uq_question_options_identity"),
        ForeignKeyConstraint(
            ["question_id", "question_type"], ["questions.id", "questions.type"], ondelete="CASCADE"
        ),
        CheckConstraint("question_type = 'MCQ'", name="mcq_only"),
        CheckConstraint("display_order > 0", name="positive_order"),
        CheckConstraint("length(trim(option_text)) > 0", name="nonempty_text"),
        Index(
            "uq_question_options_correct",
            "question_id",
            unique=True,
            postgresql_where=text("is_correct"),
            sqlite_where=text("is_correct = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column()
    question_type: Mapped[str] = mapped_column(String(12), default="MCQ", server_default="MCQ")
    option_text: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column()
    is_correct: Mapped[bool] = mapped_column(Boolean)


class AcceptedAnswer(Base):
    __tablename__ = "accepted_answers"
    __table_args__ = (
        UniqueConstraint("question_id", "accepted_value"),
        ForeignKeyConstraint(
            ["question_id", "grading_mode"],
            ["questions.id", "questions.grading_mode"],
            ondelete="CASCADE",
        ),
        CheckConstraint("grading_mode IN ('EXACT', 'NUMERIC')", name="automatic_only"),
        CheckConstraint("length(trim(accepted_value)) > 0", name="nonempty_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column()
    grading_mode: Mapped[str] = mapped_column(String(7))
    accepted_value: Mapped[str] = mapped_column(String(500))
