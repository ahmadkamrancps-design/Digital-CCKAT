"""Authentication trail and database-enforced append-only histories.

Revision ID: 0008_security_hardening
Revises: 0007_grading_results
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_security_hardening"
down_revision: str | None = "0007_grading_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HISTORIES = ("audit_events", "session_events", "grading_records", "security_events")


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column(
            "server_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('LOGIN_SUCCESS','LOGIN_FAILURE','LOGIN_THROTTLED','LOGOUT')",
            name=op.f("ck_security_events_event_type"),
        ),
        sa.CheckConstraint(
            "method IN ('ADMISSIONS','GOOGLE','SESSION')", name=op.f("ck_security_events_method")
        ),
    )
    op.create_index("ix_security_events_server_timestamp", "security_events", ["server_timestamp"])
    # Statement-level guards reject bulk SQL and TRUNCATE, including empty tables.
    # This is not protection against a schema owner/superuser disabling the trigger.
    op.execute("""
        CREATE FUNCTION cck_reject_history_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'History records are append-only' USING ERRCODE = '42501';
        END;
        $$
    """)
    for table in HISTORIES:
        op.execute(f"""
            CREATE TRIGGER cck_append_only BEFORE UPDATE OR DELETE OR TRUNCATE
            ON {table} FOR EACH STATEMENT EXECUTE FUNCTION cck_reject_history_change()
        """)


def downgrade() -> None:
    for table in HISTORIES:
        op.execute(f"DROP TRIGGER cck_append_only ON {table}")
    op.execute("DROP FUNCTION cck_reject_history_change()")
    op.drop_index("ix_security_events_server_timestamp", table_name="security_events")
    op.drop_table("security_events")
