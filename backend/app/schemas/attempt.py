from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import AttemptStatus, QuestionType, SubjectStatus


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssignmentWrite(Input):
    is_active: bool = Field(default=True, strict=True)


class AssignmentResponse(AssignmentWrite):
    id: UUID
    candidate_id: UUID
    exam_id: UUID
    assigned_by: UUID


class StartAuthorizationWrite(Input):
    authorized: bool = Field(strict=True)


class StartAuthorizationResponse(Input):
    exam_id: UUID
    is_start_authorized: bool


class SubjectAttemptResponse(Input):
    id: UUID
    exam_subject_id: UUID
    subject_name: str
    sequence: int
    duration_minutes: int
    status: SubjectStatus
    started_at: datetime | None
    expires_at: datetime | None
    submitted_at: datetime | None


class AttemptResponse(Input):
    id: UUID
    exam_id: UUID
    status: AttemptStatus
    started_at: datetime
    submitted_at: datetime | None
    server_time: datetime
    subjects: list[SubjectAttemptResponse]


class AssignedSubjectResponse(Input):
    exam_subject_id: UUID
    name: str
    duration_minutes: int
    sequence: int


class AssignedExamResponse(Input):
    exam_id: UUID
    title: str
    is_start_authorized: bool
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    attempt_id: UUID | None
    subjects: list[AssignedSubjectResponse]


class AnswerWrite(Input):
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    selected_option_id: UUID | None
    short_answer_text: str | None = Field(max_length=500)
    is_marked_for_review: bool = Field(strict=True)


class AnswerResponse(Input):
    exam_question_id: UUID
    selected_option_id: UUID | None
    short_answer_text: str | None
    is_marked_for_review: bool
    revision: int
    last_saved_at: datetime | None


class AnswerSaveResponse(Input):
    answer: AnswerResponse
    server_time: datetime


class CandidateOption(Input):
    id: UUID
    text: str


class CandidateQuestion(Input):
    exam_question_id: UUID
    question_id: UUID
    type: QuestionType
    prompt: str
    direction: Literal["auto", "ltr", "rtl"]
    language: str | None
    marks: Decimal
    sequence: int
    options: list[CandidateOption]
    answer: AnswerResponse


class SubjectPaperResponse(Input):
    subject: SubjectAttemptResponse
    server_time: datetime
    questions: list[CandidateQuestion]
