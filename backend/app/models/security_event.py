import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecurityEvent(Base):
    """Minimal authentication trail. Never stores submitted identity fields or credentials."""

    __tablename__ = "security_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('LOGIN_SUCCESS','LOGIN_FAILURE','LOGIN_THROTTLED','LOGOUT')",
            name="event_type",
        ),
        CheckConstraint("method IN ('ADMISSIONS','GOOGLE','SESSION','PASSWORD')", name="method"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(10))
    server_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
