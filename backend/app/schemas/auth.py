from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import CandidateStatus, Role


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=1, max_length=8192)


class CandidateProfile(BaseModel):
    id: UUID
    roll_number: str
    full_name: str
    status: CandidateStatus


class UserProfile(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: Role


class MeResponse(BaseModel):
    user: UserProfile
    candidate: CandidateProfile | None
    csrf_token: str
    session_expires_at: datetime
