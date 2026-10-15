"""Admissions candidate login; preserve existing users and exam attempts.

Revision ID: 0006_candidate_login
Revises: 0005_proctor_monitoring
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_candidate_login"
down_revision: str | None = "0005_proctor_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail rather than merge distinct records that would have the same login roll.
    op.create_index(
        "uq_candidates_login_roll",
        "candidates",
        [sa.text("lower(btrim(roll_number))")],
        unique=True,
    )
    op.add_column("candidates", sa.Column("father_name", sa.String(200), nullable=True))
    op.alter_column("users", "email", existing_type=sa.String(254), nullable=True)
    op.create_table(
        "login_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts > 0", name=op.f("ck_login_throttles_positive_attempts")),
    )
    op.create_index("ix_login_throttles_expires_at", "login_throttles", ["expires_at"])


def downgrade() -> None:
    # Restoring NOT NULL deliberately fails if email-less accounts exist. Operators
    # must supply real contact emails first; never invent identities or delete users.
    op.alter_column("users", "email", existing_type=sa.String(254), nullable=False)
    op.drop_table("login_throttles")
    op.drop_column("candidates", "father_name")
    op.drop_index("uq_candidates_login_roll", table_name="candidates")
