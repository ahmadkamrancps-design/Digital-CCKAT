import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CandidateStatus(enum.StrEnum):
    APPROVED = "APPROVED"
    DISABLED = "DISABLED"


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"
    __table_args__ = (CheckConstraint("length(trim(roll_number)) > 0", name="nonempty_roll"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    roll_number: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # Legacy records stay nullable until admissions supplies this field.
    father_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False, create_constraint=True, name="candidate_status"),
        default=CandidateStatus.APPROVED,
        server_default="APPROVED",
    )


Index("uq_candidates_login_roll", func.lower(func.btrim(Candidate.roll_number)), unique=True)
