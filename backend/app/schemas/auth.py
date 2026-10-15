from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CandidateStatus, Role


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=1, max_length=8192)


class CandidateLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    roll_number: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    father_name: str = Field(min_length=1, max_length=200)

    @field_validator("roll_number", "full_name", "father_name")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field is required")
        return value


class CandidateProfile(BaseModel):
    id: UUID
    roll_number: str
    full_name: str
    status: CandidateStatus


class UserProfile(BaseModel):
    id: UUID
    email: str | None
    display_name: str
    role: Role


class MeResponse(BaseModel):
    user: UserProfile
    candidate: CandidateProfile | None
    csrf_token: str
    session_expires_at: datetime
