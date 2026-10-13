import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AttemptStatus(enum.StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"


class SubjectStatus(enum.StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"


class CandidateExamAssignment(TimestampMixin, Base):
    __tablename__ = "candidate_exam_assignments"
    __table_args__ = (
        UniqueConstraint("candidate_id", "exam_id", name="uq_assignments_candidate_exam"),
        UniqueConstraint("id", "candidate_id", "exam_id", name="uq_assignments_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT")
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        UniqueConstraint("candidate_id", "exam_id", name="uq_exam_attempts_candidate_exam"),
        UniqueConstraint("assignment_id"),
        UniqueConstraint("id", "exam_id", name="uq_exam_attempts_exam"),
        ForeignKeyConstraint(
            ["assignment_id", "candidate_id", "exam_id"],
            [
                "candidate_exam_assignments.id",
                "candidate_exam_assignments.candidate_id",
                "candidate_exam_assignments.exam_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(status = 'IN_PROGRESS' AND submitted_at IS NULL) OR "
            "(status = 'SUBMITTED' AND submitted_at IS NOT NULL AND submitted_at >= started_at)",
            name="state_times",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column()
    candidate_id: Mapped[uuid.UUID] = mapped_column()
    exam_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, native_enum=False, create_constraint=True, name="attempt_status"),
        default=AttemptStatus.IN_PROGRESS,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubjectAttempt(Base):
    __tablename__ = "subject_attempts"
    __table_args__ = (
        UniqueConstraint("exam_attempt_id", "exam_subject_id", name="uq_subject_attempts_paper"),
        UniqueConstraint("exam_attempt_id", "sequence", name="uq_subject_attempts_sequence"),
        UniqueConstraint("id", "exam_subject_id", name="uq_subject_attempts_subject"),
        ForeignKeyConstraint(
            ["exam_attempt_id", "exam_id"],
            ["exam_attempts.id", "exam_attempts.exam_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["exam_subject_id", "exam_id"],
            ["exam_subjects.id", "exam_subjects.exam_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence > 0 AND duration_minutes BETWEEN 1 AND 1440", name="configuration"
        ),
        CheckConstraint(
            "(status = 'NOT_STARTED' AND started_at IS NULL "
            "AND expires_at IS NULL AND submitted_at IS NULL) OR "
            "(status = 'ACTIVE' AND started_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at > started_at AND submitted_at IS NULL) OR "
            "(status = 'SUBMITTED' AND started_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at > started_at AND submitted_at IS NOT NULL "
            "AND submitted_at >= started_at AND submitted_at < expires_at) OR "
            "(status = 'EXPIRED' AND expires_at IS NOT NULL AND submitted_at IS NOT NULL "
            "AND submitted_at = expires_at AND (started_at IS NULL OR expires_at > started_at))",
            name="state_times",
        ),
        Index(
            "uq_subject_attempts_active",
            "exam_attempt_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_subject_attempts_expiry",
            "expires_at",
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_attempt_id: Mapped[uuid.UUID] = mapped_column()
    exam_id: Mapped[uuid.UUID] = mapped_column()
    exam_subject_id: Mapped[uuid.UUID] = mapped_column()
    subject_name: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column()
    duration_minutes: Mapped[int] = mapped_column()
    status: Mapped[SubjectStatus] = mapped_column(
        Enum(
            SubjectStatus, native_enum=False, create_constraint=True, name="subject_attempt_status"
        ),
        default=SubjectStatus.NOT_STARTED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
