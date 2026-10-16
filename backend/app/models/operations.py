from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerHeartbeat(Base):
    """Operational liveness, separate from append-only examination/audit history."""

    __tablename__ = "worker_heartbeats"
    __table_args__ = (CheckConstraint("processed_count >= 0", name="processed_count"),)

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int]
