"""Expiry-worker heartbeat for readiness and monitoring.

Revision ID: 0009_operational_readiness
Revises: 0008_security_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_operational_readiness"
down_revision: str | None = "0008_security_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "processed_count >= 0", name=op.f("ck_worker_heartbeats_processed_count")
        ),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
