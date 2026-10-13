"""Configurable exam subjects questions and papers

Revision ID: 0002_exam_domain
Revises: 0001_auth_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_exam_domain"
down_revision: str | None = "0001_auth_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "ARCHIVED", name="exam_status", native_enum=False, create_constraint=True
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(scheduled_start IS NULL AND scheduled_end IS NULL) OR "
            "(scheduled_start IS NOT NULL AND scheduled_end IS NOT NULL "
            "AND scheduled_end > scheduled_start)",
            name=op.f("ck_exams_schedule_window"),
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_exams_nonempty_title")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exams")),
    )
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code = upper(trim(code)) AND length(code) > 0",
            name=op.f("ck_subjects_normalized_code"),
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_subjects_nonempty_name")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint("code", name=op.f("uq_subjects_code")),
    )
    op.create_table(
        "exam_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_minutes BETWEEN 1 AND 1440", name=op.f("ck_exam_subjects_duration_range")
        ),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_exam_subjects_positive_sequence")),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_exam_subjects_exam_id_exams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_exam_subjects_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_subjects")),
        sa.UniqueConstraint("exam_id", "sequence", name="uq_exam_subjects_exam_sequence"),
        sa.UniqueConstraint("exam_id", "subject_id", name="uq_exam_subjects_exam_subject"),
        sa.UniqueConstraint("id", "subject_id", name=op.f("uq_exam_subjects_id")),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "MCQ",
                "SHORT_ANSWER",
                name="question_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("marks", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("direction", sa.String(length=4), server_default="auto", nullable=False),
        sa.Column("language", sa.String(length=35), nullable=True),
        sa.Column(
            "grading_mode",
            sa.Enum(
                "EXACT",
                "NUMERIC",
                "MANUAL",
                name="grading_mode",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "grading_config",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(type = 'MCQ' AND grading_mode IS NULL AND grading_config IS NULL) OR "
            "(type = 'SHORT_ANSWER' AND grading_mode IS NOT NULL "
            "AND grading_config IS NOT NULL)",
            name=op.f("ck_questions_grading_shape"),
        ),
        sa.CheckConstraint(
            "direction IN ('auto', 'ltr', 'rtl')", name=op.f("ck_questions_direction")
        ),
        sa.CheckConstraint("length(trim(prompt)) > 0", name=op.f("ck_questions_nonempty_prompt")),
        sa.CheckConstraint("marks > 0 AND marks <= 10000", name=op.f("ck_questions_marks_range")),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_questions_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint("id", "grading_mode", name="uq_questions_id_grading"),
        sa.UniqueConstraint("id", "subject_id", name="uq_questions_id_subject"),
        sa.UniqueConstraint("id", "type", name="uq_questions_id_type"),
    )
    op.create_table(
        "accepted_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("grading_mode", sa.String(length=7), nullable=False),
        sa.Column("accepted_value", sa.String(length=500), nullable=False),
        sa.CheckConstraint(
            "grading_mode IN ('EXACT', 'NUMERIC')", name=op.f("ck_accepted_answers_automatic_only")
        ),
        sa.CheckConstraint(
            "length(trim(accepted_value)) > 0", name=op.f("ck_accepted_answers_nonempty_value")
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "grading_mode"],
            ["questions.id", "questions.grading_mode"],
            name=op.f("fk_accepted_answers_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accepted_answers")),
        sa.UniqueConstraint(
            "question_id", "accepted_value", name=op.f("uq_accepted_answers_question_id")
        ),
    )
    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_subject_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("marks_override", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.CheckConstraint(
            "marks_override IS NULL OR (marks_override > 0 AND marks_override <= 10000)",
            name=op.f("ck_exam_questions_marks_range"),
        ),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_exam_questions_positive_sequence")),
        sa.ForeignKeyConstraint(
            ["exam_subject_id", "subject_id"],
            ["exam_subjects.id", "exam_subjects.subject_id"],
            name=op.f("fk_exam_questions_exam_subject_id_exam_subjects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "subject_id"],
            ["questions.id", "questions.subject_id"],
            name=op.f("fk_exam_questions_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_questions")),
        sa.UniqueConstraint(
            "exam_subject_id", "question_id", name="uq_exam_questions_paper_question"
        ),
        sa.UniqueConstraint("exam_subject_id", "sequence", name="uq_exam_questions_paper_sequence"),
    )
    op.create_table(
        "question_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("question_type", sa.String(length=12), server_default="MCQ", nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.CheckConstraint("question_type = 'MCQ'", name=op.f("ck_question_options_mcq_only")),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_question_options_positive_order")),
        sa.CheckConstraint(
            "length(trim(option_text)) > 0", name=op.f("ck_question_options_nonempty_text")
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "question_type"],
            ["questions.id", "questions.type"],
            name=op.f("fk_question_options_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_options")),
        sa.UniqueConstraint(
            "question_id", "display_order", name=op.f("uq_question_options_question_id")
        ),
    )
    op.create_index(
        "uq_question_options_correct",
        "question_options",
        ["question_id"],
        unique=True,
        postgresql_where=sa.text("is_correct"),
        sqlite_where=sa.text("is_correct = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_question_options_correct",
        table_name="question_options",
        postgresql_where=sa.text("is_correct"),
        sqlite_where=sa.text("is_correct = 1"),
    )
    op.drop_table("question_options")
    op.drop_table("exam_questions")
    op.drop_table("accepted_answers")
    op.drop_table("questions")
    op.drop_table("exam_subjects")
    op.drop_table("subjects")
    op.drop_table("exams")
