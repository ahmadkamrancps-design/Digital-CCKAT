from datetime import timedelta
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.clock import DatabaseClock
from app.core.security import as_utc
from app.models import WorkerHeartbeat


def migration_head() -> str:
    head = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic")).get_current_head()
    if head is None:
        raise RuntimeError("Migration head unavailable")
    return head


def record_worker_success(db: Session, processed: int, name: str = "expiry") -> None:
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    now = DatabaseClock().now(db)
    statement = insert(WorkerHeartbeat).values(
        name=name, last_success_at=now, processed_count=processed
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.name],
            set_={"last_success_at": now, "processed_count": processed},
        )
    )
    db.commit()


def check_worker(db: Session, stale_seconds: int) -> None:
    heartbeat = db.get(WorkerHeartbeat, "expiry")
    now = DatabaseClock().now(db)
    if heartbeat is None or as_utc(heartbeat.last_success_at) < now - timedelta(
        seconds=stale_seconds
    ):
        raise HTTPException(503, "Service is not ready.")


def check_readiness(db: Session, settings: Settings, expected_head: str) -> None:
    db.execute(select(WorkerHeartbeat.name).limit(1))
    if db.get_bind().dialect.name == "postgresql":
        versions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
        if versions != {expected_head}:
            raise HTTPException(503, "Service is not ready.")
    if settings.require_expiry_worker:
        check_worker(db, settings.expiry_worker_stale_seconds)
