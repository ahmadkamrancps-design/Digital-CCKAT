import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExaminerExamAssignment(TimestampMixin, Base):
    __tablename__ = "examiner_exam_assignments"
    __table_args__ = (UniqueConstraint("exam_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class GradingRecord(Base):
    """Append-only through application services; each correction is a new revision."""

    __tablename__ = "grading_records"
    __table_args__ = (
        UniqueConstraint("answer_id", "revision"),
        CheckConstraint("revision > 0 AND answer_revision >= 0", name="revisions"),
        CheckConstraint(
            "maximum_marks > 0 AND maximum_marks <= 10000 "
            "AND marks_awarded >= 0 AND marks_awarded <= maximum_marks",
            name="marks_range",
        ),
        CheckConstraint("method IN ('MCQ','EXACT','NUMERIC','MANUAL','UNANSWERED')", name="method"),
        CheckConstraint(
            "(method = 'MANUAL' AND graded_by IS NOT NULL) OR "
            "(method != 'MANUAL' AND graded_by IS NULL)",
            name="grader",
        ),
        CheckConstraint("length(notes) <= 2000", name="notes_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id", ondelete="RESTRICT"))
    revision: Mapped[int]
    answer_revision: Mapped[int]
    marks_awarded: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    maximum_marks: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    method: Mapped[str] = mapped_column(String(10))
    graded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
