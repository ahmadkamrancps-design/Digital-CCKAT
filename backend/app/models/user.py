import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Role(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    ADMIN = "ADMIN"
    PROCTOR = "PROCTOR"
    EXAMINER = "EXAMINER"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(trim(email))", name="normalized_email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, create_constraint=True, name="user_role"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
