"""Assignments timed subject attempts and revisioned answers

Revision ID: 0003_attempt_engine
Revises: 0002_exam_domain
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_attempt_engine"
down_revision: str | None = "0002_exam_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Referenced composite keys must exist before creating the dependent tables.
    op.create_unique_constraint(
        "uq_exam_questions_identity", "exam_questions", ["id", "exam_subject_id", "question_id"]
    )
    op.create_unique_constraint("uq_exam_subjects_exam", "exam_subjects", ["id", "exam_id"])
    op.create_unique_constraint(
        "uq_question_options_identity", "question_options", ["id", "question_id"]
    )
    op.add_column(
        "exams",
        sa.Column("is_start_authorized", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "candidate_exam_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_candidate_exam_assignments_assigned_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_exam_assignments_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_candidate_exam_assignments_exam_id_exams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_exam_assignments")),
        sa.UniqueConstraint("candidate_id", "exam_id", name="uq_assignments_candidate_exam"),
        sa.UniqueConstraint("id", "candidate_id", "exam_id", name="uq_assignments_identity"),
    )
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "IN_PROGRESS",
                "SUBMITTED",
                name="attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'IN_PROGRESS' AND submitted_at IS NULL) OR "
            "(status = 'SUBMITTED' AND submitted_at IS NOT NULL AND submitted_at >= started_at)",
            name=op.f("ck_exam_attempts_state_times"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "candidate_id", "exam_id"],
            [
                "candidate_exam_assignments.id",
                "candidate_exam_assignments.candidate_id",
                "candidate_exam_assignments.exam_id",
            ],
            name=op.f("fk_exam_attempts_assignment_id_candidate_exam_assignments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_attempts")),
        sa.UniqueConstraint("assignment_id", name=op.f("uq_exam_attempts_assignment_id")),
        sa.UniqueConstraint("candidate_id", "exam_id", name="uq_exam_attempts_candidate_exam"),
        sa.UniqueConstraint("id", "exam_id", name="uq_exam_attempts_exam"),
    )
    op.create_table(
        "subject_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("exam_subject_id", sa.Uuid(), nullable=False),
        sa.Column("subject_name", sa.String(length=100), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NOT_STARTED",
                "ACTIVE",
                "SUBMITTED",
                "EXPIRED",
                name="subject_attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'NOT_STARTED' AND started_at IS NULL "
            "AND expires_at IS NULL AND submitted_at IS NULL) OR "
            "(status = 'ACTIVE' AND started_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at > started_at AND submitted_at IS NULL) OR "
            "(status = 'SUBMITTED' AND started_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at > started_at AND submitted_at IS NOT NULL "
            "AND submitted_at >= started_at AND submitted_at < expires_at) OR "
            "(status = 'EXPIRED' AND expires_at IS NOT NULL AND submitted_at IS NOT NULL "
            "AND submitted_at = expires_at AND (started_at IS NULL OR expires_at > started_at))",
            name=op.f("ck_subject_attempts_state_times"),
        ),
        sa.CheckConstraint(
            "sequence > 0 AND duration_minutes BETWEEN 1 AND 1440",
            name=op.f("ck_subject_attempts_configuration"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_attempt_id", "exam_id"],
            ["exam_attempts.id", "exam_attempts.exam_id"],
            name=op.f("fk_subject_attempts_exam_attempt_id_exam_attempts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exam_subject_id", "exam_id"],
            ["exam_subjects.id", "exam_subjects.exam_id"],
            name=op.f("fk_subject_attempts_exam_subject_id_exam_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_attempts")),
        sa.UniqueConstraint("exam_attempt_id", "exam_subject_id", name="uq_subject_attempts_paper"),
        sa.UniqueConstraint("exam_attempt_id", "sequence", name="uq_subject_attempts_sequence"),
        sa.UniqueConstraint("id", "exam_subject_id", name="uq_subject_attempts_subject"),
    )
    op.create_index(
        "ix_subject_attempts_expiry",
        "subject_attempts",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "uq_subject_attempts_active",
        "subject_attempts",
        ["exam_attempt_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("exam_subject_id", sa.Uuid(), nullable=False),
        sa.Column("exam_question_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("question_type", sa.String(length=12), nullable=False),
        sa.Column("selected_option_id", sa.Uuid(), nullable=True),
        sa.Column("short_answer_text", sa.Text(), nullable=True),
        sa.Column("is_marked_for_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(question_type = 'MCQ' AND short_answer_text IS NULL) OR "
            "(question_type = 'SHORT_ANSWER' AND selected_option_id IS NULL)",
            name=op.f("ck_answers_shape"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_answers_revision")),
        sa.CheckConstraint(
            "short_answer_text IS NULL OR length(short_answer_text) <= 500",
            name=op.f("ck_answers_short_length"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_question_id", "exam_subject_id", "question_id"],
            ["exam_questions.id", "exam_questions.exam_subject_id", "exam_questions.question_id"],
            name=op.f("fk_answers_exam_question_id_exam_questions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "question_type"],
            ["questions.id", "questions.type"],
            name=op.f("fk_answers_question_id_questions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selected_option_id", "question_id"],
            ["question_options.id", "question_options.question_id"],
            name=op.f("fk_answers_selected_option_id_question_options"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_attempt_id", "exam_subject_id"],
            ["subject_attempts.id", "subject_attempts.exam_subject_id"],
            name=op.f("fk_answers_subject_attempt_id_subject_attempts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint(
            "subject_attempt_id", "exam_question_id", name="uq_answers_attempt_question"
        ),
    )


def downgrade() -> None:
    op.drop_table("answers")
    op.drop_index(
        "uq_subject_attempts_active",
        table_name="subject_attempts",
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_index(
        "ix_subject_attempts_expiry",
        table_name="subject_attempts",
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_table("subject_attempts")
    op.drop_table("exam_attempts")
    op.drop_table("candidate_exam_assignments")
    op.drop_constraint("uq_question_options_identity", "question_options", type_="unique")
    op.drop_column("exams", "is_start_authorized")
    op.drop_constraint("uq_exam_subjects_exam", "exam_subjects", type_="unique")
    op.drop_constraint("uq_exam_questions_identity", "exam_questions", type_="unique")
