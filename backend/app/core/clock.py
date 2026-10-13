from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.services.auth_service import as_utc


class Clock(Protocol):
    def now(self, db: Session) -> datetime: ...


class DatabaseClock:
    def now(self, db: Session) -> datetime:
        if db.get_bind().dialect.name == "postgresql":
            value = db.scalar(select(func.clock_timestamp()))
            if not isinstance(value, datetime):
                raise RuntimeError("Database clock unavailable")
            return as_utc(value)
        # SQLite is only used in unit tests, never in the application's configuration.
        return utc_now()
