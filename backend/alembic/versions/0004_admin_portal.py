"""Exam publication, result controls, and staff action records.

Revision ID: 0004_admin_portal
Revises: 0003_attempt_engine
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_admin_portal"
down_revision: str | None = "0003_attempt_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exams", sa.Column("is_published", sa.Boolean(), server_default="true", nullable=False)
    )
    op.add_column(
        "exams", sa.Column("results_released", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "exams", sa.Column("result_release_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "server_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_column("exams", "result_release_at")
    op.drop_column("exams", "results_released")
    op.drop_column("exams", "is_published")
