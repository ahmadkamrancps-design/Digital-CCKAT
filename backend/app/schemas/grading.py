from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ManualGradeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    marks_awarded: Decimal = Field(ge=0, le=10000, max_digits=8, decimal_places=2)
    notes: str = Field(default="", max_length=2000)


class GradeResponse(BaseModel):
    id: UUID
    answer_id: UUID
    revision: int
    marks_awarded: Decimal
    maximum_marks: Decimal
    method: str
    graded_by: UUID | None
    graded_at: datetime
    notes: str


class GradingExam(BaseModel):
    id: UUID
    title: str
    results_released: bool


class ExaminerStaff(BaseModel):
    id: UUID
    display_name: str


class ExaminerAssignment(BaseModel):
    user_id: UUID
    display_name: str
    is_active: bool


class ManualResponse(BaseModel):
    answer_id: UUID
    attempt_id: UUID
    subject_name: str
    question_number: int
    prompt: str
    direction: Literal["auto", "ltr", "rtl"]
    answer_text: str
    maximum_marks: Decimal
    current_grade: GradeResponse | None


class SubjectResult(BaseModel):
    subject_name: str
    sequence: int
    maximum_marks: Decimal
    marks_awarded: Decimal | None
    pending_answers: int


class AttemptResult(BaseModel):
    attempt_id: UUID
    exam_id: UUID
    exam_title: str
    grading_status: Literal["PENDING", "COMPLETE"]
    publication_status: Literal["WITHHELD", "SCHEDULED", "RELEASED"]
    subjects: list[SubjectResult]
    maximum_marks: Decimal | None
    marks_awarded: Decimal | None
    percentage: Decimal | None


class GradingAttempt(BaseModel):
    attempt_id: UUID
    roll_number: str
    full_name: str
    status: str
    grading_status: Literal["PENDING", "COMPLETE"]
    pending_answers: int
    marks_awarded: Decimal | None
    maximum_marks: Decimal
