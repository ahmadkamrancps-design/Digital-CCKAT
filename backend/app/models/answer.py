import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint(
            "subject_attempt_id", "exam_question_id", name="uq_answers_attempt_question"
        ),
        ForeignKeyConstraint(
            ["subject_attempt_id", "exam_subject_id"],
            ["subject_attempts.id", "subject_attempts.exam_subject_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["exam_question_id", "exam_subject_id", "question_id"],
            ["exam_questions.id", "exam_questions.exam_subject_id", "exam_questions.question_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["question_id", "question_type"],
            ["questions.id", "questions.type"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["selected_option_id", "question_id"],
            ["question_options.id", "question_options.question_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision >= 0", name="revision"),
        CheckConstraint(
            "(question_type = 'MCQ' AND short_answer_text IS NULL) OR "
            "(question_type = 'SHORT_ANSWER' AND selected_option_id IS NULL)",
            name="shape",
        ),
        CheckConstraint(
            "short_answer_text IS NULL OR length(short_answer_text) <= 500", name="short_length"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_attempt_id: Mapped[uuid.UUID] = mapped_column()
    exam_subject_id: Mapped[uuid.UUID] = mapped_column()
    exam_question_id: Mapped[uuid.UUID] = mapped_column()
    question_id: Mapped[uuid.UUID] = mapped_column()
    question_type: Mapped[str] = mapped_column(String(12))
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column()
    short_answer_text: Mapped[str | None] = mapped_column(Text)
    is_marked_for_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    revision: Mapped[int] = mapped_column(default=0, server_default="0")
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
