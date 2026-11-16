"""Add optional password credentials for approved staff, preserving existing identities.

Revision ID: 0010_staff_password
Revises: 0009_operational_readiness
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_staff_password"
down_revision: str | None = "0009_operational_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.drop_constraint(op.f("ck_security_events_method"), "security_events", type_="check")
    op.create_check_constraint(
        op.f("ck_security_events_method"),
        "security_events",
        "method IN ('ADMISSIONS','GOOGLE','SESSION','PASSWORD')",
    )


def downgrade() -> None:
    # Preserve append-only password authentication history on rollback. Leaving this
    # widened check is safe for the older application; deleting historical rows is not.
    op.drop_column("users", "password_hash")
