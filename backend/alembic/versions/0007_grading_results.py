"""Versioned grading history and scoped examiner access.

Revision ID: 0007_grading_results
Revises: 0006_candidate_login
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_grading_results"
down_revision: str | None = "0006_candidate_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "examiner_exam_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "exam_id", sa.Uuid(), sa.ForeignKey("exams.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "assigned_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("exam_id", "user_id"),
    )
    op.create_table(
        "grading_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "answer_id", sa.Uuid(), sa.ForeignKey("answers.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("answer_revision", sa.Integer(), nullable=False),
        sa.Column("marks_awarded", sa.Numeric(8, 2), nullable=False),
        sa.Column("maximum_marks", sa.Numeric(8, 2), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("graded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("answer_id", "revision"),
        sa.CheckConstraint(
            "revision > 0 AND answer_revision >= 0", name=op.f("ck_grading_records_revisions")
        ),
        sa.CheckConstraint(
            "maximum_marks > 0 AND maximum_marks <= 10000 "
            "AND marks_awarded >= 0 AND marks_awarded <= maximum_marks",
            name=op.f("ck_grading_records_marks_range"),
        ),
        sa.CheckConstraint(
            "method IN ('MCQ','EXACT','NUMERIC','MANUAL','UNANSWERED')",
            name=op.f("ck_grading_records_method"),
        ),
        sa.CheckConstraint(
            "(method = 'MANUAL' AND graded_by IS NOT NULL) OR "
            "(method != 'MANUAL' AND graded_by IS NULL)",
            name=op.f("ck_grading_records_grader"),
        ),
        sa.CheckConstraint("length(notes) <= 2000", name=op.f("ck_grading_records_notes_length")),
    )
    # Any historical/directly-set release flags must not publish ungraded attempts.
    op.execute("UPDATE exams SET results_released = false")


def downgrade() -> None:
    op.execute("UPDATE exams SET results_released = false")
    op.drop_table("grading_records")
    op.drop_table("examiner_exam_assignments")
