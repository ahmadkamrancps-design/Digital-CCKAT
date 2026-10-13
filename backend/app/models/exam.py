import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExamStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    ARCHIVED = "ARCHIVED"


class Exam(TimestampMixin, Base):
    __tablename__ = "exams"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="nonempty_title"),
        CheckConstraint(
            "(scheduled_start IS NULL AND scheduled_end IS NULL) OR "
            "(scheduled_start IS NOT NULL AND scheduled_end IS NOT NULL "
            "AND scheduled_end > scheduled_start)",
            name="schedule_window",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[ExamStatus] = mapped_column(
        Enum(ExamStatus, native_enum=False, create_constraint=True, name="exam_status"),
        default=ExamStatus.DRAFT,
        server_default="DRAFT",
    )
    is_start_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExamSubject(TimestampMixin, Base):
    __tablename__ = "exam_subjects"
    __table_args__ = (
        UniqueConstraint("exam_id", "subject_id", name="uq_exam_subjects_exam_subject"),
        UniqueConstraint("exam_id", "sequence", name="uq_exam_subjects_exam_sequence"),
        UniqueConstraint("id", "subject_id"),
        UniqueConstraint("id", "exam_id", name="uq_exam_subjects_exam"),
        CheckConstraint("duration_minutes BETWEEN 1 AND 1440", name="duration_range"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="RESTRICT"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    duration_minutes: Mapped[int] = mapped_column()
    sequence: Mapped[int] = mapped_column()


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_subject_id", "question_id", name="uq_exam_questions_paper_question"),
        UniqueConstraint("exam_subject_id", "sequence", name="uq_exam_questions_paper_sequence"),
        UniqueConstraint("id", "exam_subject_id", "question_id", name="uq_exam_questions_identity"),
        ForeignKeyConstraint(
            ["exam_subject_id", "subject_id"],
            ["exam_subjects.id", "exam_subjects.subject_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["question_id", "subject_id"],
            ["questions.id", "questions.subject_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint(
            "marks_override IS NULL OR (marks_override > 0 AND marks_override <= 10000)",
            name="marks_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_subject_id: Mapped[uuid.UUID] = mapped_column()
    question_id: Mapped[uuid.UUID] = mapped_column()
    # Composite foreign keys enforce subject compatibility even for direct SQL writes.
    subject_id: Mapped[uuid.UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column()
    marks_override: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
