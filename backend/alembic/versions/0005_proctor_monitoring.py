"""Scoped proctor access, presence, and session events.

Revision ID: 0005_proctor_monitoring
Revises: 0004_admin_portal
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_proctor_monitoring"
down_revision: str | None = "0004_admin_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proctor_exam_assignments",
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
        "attempt_presence",
        sa.Column(
            "exam_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("exam_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "subject_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("subject_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("question_sequence", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "question_sequence BETWEEN 1 AND 200",
            name=op.f("ck_attempt_presence_question_position"),
        ),
    )
    op.create_table(
        "session_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "exam_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("exam_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subject_attempt_id",
            sa.Uuid(),
            sa.ForeignKey("subject_attempts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "EXAM_OPENED",
                "SUBJECT_STARTED",
                "ANSWER_SAVED",
                "QUESTION_FLAGGED",
                "QUESTION_UNFLAGGED",
                "SUBJECT_SUBMITTED",
                "SUBJECT_AUTO_SUBMITTED",
                "EXAM_SUBMITTED",
                "CONNECTION_LOST",
                "CONNECTION_RESTORED",
                "VISIBILITY_HIDDEN",
                "VISIBILITY_VISIBLE",
                "FULLSCREEN_EXIT",
                "FULLSCREEN_ENTER",
                native_enum=False,
                create_constraint=True,
                name="session_event_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "SERVER", "CLIENT", native_enum=False, create_constraint=True, name="event_source"
            ),
            nullable=False,
        ),
        sa.Column("client_event_id", sa.Uuid(), nullable=True),
        sa.Column("server_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("exam_attempt_id", "client_event_id"),
        sa.CheckConstraint(
            "(source = 'CLIENT' AND client_event_id IS NOT NULL AND event_type IN "
            "('CONNECTION_LOST','CONNECTION_RESTORED','VISIBILITY_HIDDEN',"
            "'VISIBILITY_VISIBLE','FULLSCREEN_EXIT','FULLSCREEN_ENTER')) OR "
            "(source = 'SERVER' AND client_event_id IS NULL AND event_type IN "
            "('EXAM_OPENED','SUBJECT_STARTED','ANSWER_SAVED','QUESTION_FLAGGED',"
            "'QUESTION_UNFLAGGED','SUBJECT_SUBMITTED','SUBJECT_AUTO_SUBMITTED','EXAM_SUBMITTED'))",
            name=op.f("ck_session_events_source_event_type"),
        ),
    )
    op.create_index(
        "ix_session_events_attempt_time", "session_events", ["exam_attempt_id", "server_timestamp"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_events_attempt_time", table_name="session_events")
    op.drop_table("session_events")
    op.drop_table("attempt_presence")
    op.drop_table("proctor_exam_assignments")
