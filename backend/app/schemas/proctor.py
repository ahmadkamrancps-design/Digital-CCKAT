from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models import EventSource, SessionEventType, SubjectStatus
from app.schemas.attempt import Input

ClientEventType = Literal[
    "CONNECTION_LOST",
    "CONNECTION_RESTORED",
    "VISIBILITY_HIDDEN",
    "VISIBILITY_VISIBLE",
    "FULLSCREEN_EXIT",
    "FULLSCREEN_ENTER",
]


class ClientEvent(Input):
    event_id: UUID
    event_type: ClientEventType


class PresenceWrite(Input):
    subject_attempt_id: UUID
    question_sequence: int = Field(strict=True, ge=1, le=200)
    events: list[ClientEvent] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_events(self) -> Self:
        if len({item.event_id for item in self.events}) != len(self.events):
            raise ValueError("Event identifiers must be unique.")
        return self


class PresenceResponse(Input):
    server_time: datetime


class ProctorStaff(Input):
    id: UUID
    display_name: str


class ProctorAssignmentResponse(Input):
    user_id: UUID
    display_name: str
    is_active: bool
    user_is_active: bool


class MonitoredExam(Input):
    id: UUID
    title: str
    is_start_authorized: bool
    scheduled_start: datetime | None
    scheduled_end: datetime | None


class MonitoredCandidate(Input):
    candidate_id: UUID
    roll_number: str
    full_name: str
    access_active: bool
    attempt_id: UUID | None
    state: Literal["NOT_STARTED", "TESTING", "BETWEEN_SUBJECTS", "SUBMITTED"]
    subject_attempt_id: UUID | None
    subject_name: str | None
    subject_status: SubjectStatus | None
    question_count: int
    reported_question_sequence: int | None
    expires_at: datetime | None
    remaining_seconds: int | None
    connection: Literal["ONLINE", "NO_RECENT_CONTACT", "UNKNOWN"]
    last_seen_at: datetime | None
    review_event_count: int


class MonitoringResponse(Input):
    server_time: datetime
    candidates: list[MonitoredCandidate]


class SessionEventResponse(Input):
    id: UUID
    event_type: SessionEventType
    source: EventSource
    subject_attempt_id: UUID | None
    server_timestamp: datetime
