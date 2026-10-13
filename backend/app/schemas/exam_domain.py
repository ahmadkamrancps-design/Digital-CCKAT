import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import ExamStatus, QuestionType

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Marks = Annotated[Decimal, Field(gt=0, le=10000, max_digits=8, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SubjectWrite(Input):
    name: Annotated[Nonempty, Field(max_length=100)]
    code: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9_-]{1,32}$"),
    ]
    is_active: bool = True


class SubjectResponse(SubjectWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ExamWrite(Input):
    title: Annotated[Nonempty, Field(max_length=200)]
    description: str = Field(default="", max_length=10000)
    status: ExamStatus = ExamStatus.DRAFT
    scheduled_start: AwareDatetime | None = None
    scheduled_end: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid_schedule(self) -> Self:
        if (self.scheduled_start is None) != (self.scheduled_end is None):
            raise ValueError("Specify both schedule timestamps or neither.")
        if (
            self.scheduled_start
            and self.scheduled_end
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValueError("The schedule must have a positive window.")
        return self


class ExamResponse(ExamWrite):
    is_start_authorized: bool
    id: UUID
    created_at: datetime
    updated_at: datetime


class ExamSubjectWrite(Input):
    subject_id: UUID
    duration_minutes: int = Field(ge=1, le=1440, strict=True)
    sequence: int = Field(ge=1, le=1000, strict=True)


class ExamSubjectResponse(ExamSubjectWrite):
    id: UUID
    exam_id: UUID
    total_marks: Decimal
    question_count: int


class OptionWrite(Input):
    text: Annotated[Nonempty, Field(max_length=4000)]
    is_correct: bool


class ExactConfig(Input):
    mode: Literal["EXACT"] = "EXACT"
    unicode_normalization: Literal["NFC", "NONE"] = "NFC"
    trim_whitespace: bool = False
    collapse_whitespace: bool = False
    case_sensitive: bool = True


class NumericConfig(Input):
    mode: Literal["NUMERIC"] = "NUMERIC"
    absolute_tolerance: Decimal = Field(
        default=Decimal(0), ge=0, le=1000000, max_digits=24, decimal_places=12
    )


class ManualConfig(Input):
    mode: Literal["MANUAL"] = "MANUAL"


GradingConfig = Annotated[ExactConfig | NumericConfig | ManualConfig, Field(discriminator="mode")]


class QuestionWriteBase(Input):
    subject_id: UUID
    prompt: Annotated[Nonempty, Field(max_length=10000)]
    marks: Marks
    direction: Literal["auto", "ltr", "rtl"] = "auto"
    language: (
        Annotated[
            str, StringConstraints(pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$", max_length=35)
        ]
        | None
    ) = None
    is_active: bool = True


class MCQWrite(QuestionWriteBase):
    type: Literal["MCQ"]
    options: list[OptionWrite] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def valid_options(self) -> Self:
        if sum(option.is_correct for option in self.options) != 1:
            raise ValueError("An MCQ requires exactly one correct option.")
        if len({option.text for option in self.options}) != len(self.options):
            raise ValueError("Option text must be distinct.")
        return self


class ShortAnswerWrite(QuestionWriteBase):
    type: Literal["SHORT_ANSWER"]
    grading: GradingConfig
    accepted_answers: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def valid_answers(self) -> Self:
        if isinstance(self.grading, ManualConfig):
            if self.accepted_answers:
                raise ValueError("Manual questions cannot have accepted answers.")
            return self
        if not self.accepted_answers:
            raise ValueError("Automatic grading requires accepted answers.")
        normalized: list[str | Decimal] = []
        for answer in self.accepted_answers:
            if not answer.strip():
                raise ValueError("Accepted answers must contain non-whitespace text.")
            if isinstance(self.grading, NumericConfig):
                # Deliberately allow decimal/scientific numbers only, not expressions or units.
                if not re.fullmatch(
                    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", answer.strip()
                ):
                    raise ValueError("Accepted numeric values must be decimal numbers.")
                try:
                    number = Decimal(answer)
                except InvalidOperation as exc:
                    raise ValueError("Accepted numeric values must be decimal numbers.") from exc
                if not number.is_finite() or (number and not -100 <= number.adjusted() <= 100):
                    raise ValueError("Numeric value is outside the supported range.")
                normalized.append(number)
            else:
                value = (
                    unicodedata.normalize("NFC", answer)
                    if self.grading.unicode_normalization == "NFC"
                    else answer
                )
                if self.grading.trim_whitespace:
                    value = value.strip()
                if self.grading.collapse_whitespace:
                    value = " ".join(value.split())
                if not self.grading.case_sensitive:
                    value = value.casefold()
                normalized.append(value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("Accepted answers must be distinct under the configured rules.")
        return self


QuestionWrite = Annotated[MCQWrite | ShortAnswerWrite, Field(discriminator="type")]


class OptionResponse(OptionWrite):
    id: UUID
    display_order: int


class AdminQuestionResponse(QuestionWriteBase):
    id: UUID
    type: QuestionType
    options: list[OptionResponse]
    grading: GradingConfig | None
    accepted_answers: list[str]
    created_at: datetime
    updated_at: datetime


class PaperQuestionWrite(Input):
    question_id: UUID
    marks_override: Marks | None = None


class PaperWrite(Input):
    questions: list[PaperQuestionWrite] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        if len({item.question_id for item in self.questions}) != len(self.questions):
            raise ValueError("A paper cannot contain duplicate questions.")
        return self


class PaperQuestionResponse(PaperQuestionWrite):
    id: UUID
    sequence: int
    effective_marks: Decimal


class PaperResponse(Input):
    exam_subject_id: UUID
    questions: list[PaperQuestionResponse]
    total_marks: Decimal
