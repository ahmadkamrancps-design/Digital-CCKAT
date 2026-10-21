from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from app.models import CandidateStatus, ExamStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CandidateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    full_name: Annotated[Text, Field(max_length=200)]
    father_name: Annotated[Text, Field(max_length=200)] | None = None
    roll_number: Annotated[Text, Field(max_length=64)]
    google_subject: Annotated[Text, Field(max_length=255)] | None = None
    status: CandidateStatus = CandidateStatus.APPROVED

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class CandidateResponse(CandidateWrite):
    id: UUID
    user_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CandidateImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[CandidateWrite] = Field(min_length=1, max_length=500)


class PublicationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published: bool = Field(strict=True)


class ReleaseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    released: bool = Field(strict=True)
    result_release_at: AwareDatetime | None = None


class StaffActionResponse(BaseModel):
    id: UUID
    user_id: UUID
    actor_name: str | None = None
    event_type: str
    entity_id: UUID
    server_timestamp: datetime


class OverviewExam(BaseModel):
    id: UUID
    title: str
    status: ExamStatus
    is_published: bool
    is_start_authorized: bool
    results_released: bool
    scheduled_start: datetime | None


class OverviewAction(BaseModel):
    id: UUID
    event_type: str
    actor_name: str
    server_timestamp: datetime


class AdminOverview(BaseModel):
    candidate_count: int
    approved_candidates: int
    exam_count: int
    published_exams: int
    question_count: int
    active_questions: int
    subject_count: int
    active_subjects: int
    recent_exams: list[OverviewExam]
    recent_actions: list[OverviewAction]
