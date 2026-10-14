import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EventSource(enum.StrEnum):
    SERVER = "SERVER"
    CLIENT = "CLIENT"


class SessionEventType(enum.StrEnum):
    EXAM_OPENED = "EXAM_OPENED"
    SUBJECT_STARTED = "SUBJECT_STARTED"
    ANSWER_SAVED = "ANSWER_SAVED"
    QUESTION_FLAGGED = "QUESTION_FLAGGED"
    QUESTION_UNFLAGGED = "QUESTION_UNFLAGGED"
    SUBJECT_SUBMITTED = "SUBJECT_SUBMITTED"
    SUBJECT_AUTO_SUBMITTED = "SUBJECT_AUTO_SUBMITTED"
    EXAM_SUBMITTED = "EXAM_SUBMITTED"
    CONNECTION_LOST = "CONNECTION_LOST"
    CONNECTION_RESTORED = "CONNECTION_RESTORED"
    VISIBILITY_HIDDEN = "VISIBILITY_HIDDEN"
    VISIBILITY_VISIBLE = "VISIBILITY_VISIBLE"
    FULLSCREEN_EXIT = "FULLSCREEN_EXIT"
    FULLSCREEN_ENTER = "FULLSCREEN_ENTER"


class ProctorExamAssignment(TimestampMixin, Base):
    __tablename__ = "proctor_exam_assignments"
    __table_args__ = (UniqueConstraint("exam_id", "user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exams.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")


class AttemptPresence(Base):
    __tablename__ = "attempt_presence"
    __table_args__ = (
        CheckConstraint("question_sequence BETWEEN 1 AND 200", name="question_position"),
    )
    exam_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="RESTRICT"), primary_key=True
    )
    subject_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subject_attempts.id", ondelete="RESTRICT")
    )
    question_sequence: Mapped[int] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionEvent(Base):
    """Allowlisted incident context; contains no answers, prompts, keys, or free text."""

    __tablename__ = "session_events"
    __table_args__ = (
        UniqueConstraint("exam_attempt_id", "client_event_id"),
        Index("ix_session_events_attempt_time", "exam_attempt_id", "server_timestamp"),
        CheckConstraint(
            "(source = 'CLIENT' AND client_event_id IS NOT NULL AND event_type IN "
            "('CONNECTION_LOST','CONNECTION_RESTORED','VISIBILITY_HIDDEN',"
            "'VISIBILITY_VISIBLE','FULLSCREEN_EXIT','FULLSCREEN_ENTER')) OR "
            "(source = 'SERVER' AND client_event_id IS NULL AND event_type IN "
            "('EXAM_OPENED','SUBJECT_STARTED','ANSWER_SAVED','QUESTION_FLAGGED',"
            "'QUESTION_UNFLAGGED','SUBJECT_SUBMITTED','SUBJECT_AUTO_SUBMITTED','EXAM_SUBMITTED'))",
            name="source_event_type",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exam_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_attempts.id", ondelete="RESTRICT")
    )
    subject_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subject_attempts.id", ondelete="RESTRICT")
    )
    event_type: Mapped[SessionEventType] = mapped_column(
        Enum(SessionEventType, native_enum=False, create_constraint=True, name="session_event_type")
    )
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource, native_enum=False, create_constraint=True, name="event_source")
    )
    client_event_id: Mapped[uuid.UUID | None] = mapped_column()
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
