"""Pydantic request/response schemas for the HTTP API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard", "mixed"]
TestStatus = Literal["draft", "published"]
AttemptStatus = Literal["in_progress", "submitted"]
SubmitReason = Literal["manual", "timeout"]

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]
MAX_OPTIONS = 6
MIN_OPTIONS = 2


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- questions


class QuestionIn(BaseModel):
    id: int | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    options: list[str] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    correct_option: int = Field(ge=0)
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)] = ""
    topic: ShortText = ""

    @field_validator("options")
    @classmethod
    def _clean_options(cls, options: list[str]) -> list[str]:
        cleaned = [option.strip() for option in options]
        if any(not option for option in cleaned):
            raise ValueError("Options cannot be empty.")
        if any(len(option) > 500 for option in cleaned):
            raise ValueError("Options must be 500 characters or fewer.")
        if len({option.casefold() for option in cleaned}) != len(cleaned):
            raise ValueError("Options must be unique.")
        return cleaned

    @model_validator(mode="after")
    def _check_correct_option(self) -> "QuestionIn":
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option must point to one of the options.")
        return self


class QuestionOut(ORMModel):
    id: int
    position: int
    text: str
    options: list[str]
    correct_option: int
    explanation: str
    topic: str


# --------------------------------------------------------------------------- tests


class TestSettings(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    subject: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    topic: ShortText = ""
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    difficulty: Difficulty = "medium"
    duration_minutes: int = Field(default=30, ge=1, le=600)
    marks_per_question: float = Field(default=1.0, gt=0, le=100)
    negative_marks: float = Field(default=0.0, ge=0, le=100)
    shuffle_questions: bool = False
    shuffle_options: bool = False

    @model_validator(mode="after")
    def _check_marking(self) -> "TestSettings":
        if self.negative_marks > self.marks_per_question:
            raise ValueError("Negative marks cannot exceed the marks for a correct answer.")
        return self


class TestWrite(TestSettings):
    """Payload for creating or fully replacing a test (including its questions)."""

    status: TestStatus = "draft"
    questions: list[QuestionIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _check_publishable(self) -> "TestWrite":
        if self.status == "published" and not self.questions:
            raise ValueError("A test needs at least one question before it can be published.")
        return self


class TestSummary(ORMModel):
    id: int
    title: str
    description: str
    subject: str
    topic: str
    category: str
    difficulty: Difficulty
    duration_minutes: int
    marks_per_question: float
    negative_marks: float
    status: TestStatus
    source: str
    question_count: int = 0
    attempt_count: int = 0
    best_percentage: float | None = None
    last_attempt_at: datetime | None = None
    in_progress_attempt_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TestDetail(TestSummary):
    shuffle_questions: bool
    shuffle_options: bool
    generation_notes: str
    questions: list[QuestionOut]


class GenerateTestResponse(BaseModel):
    test: TestDetail
    warnings: list[str] = Field(default_factory=list)


class GenerateTestForm(BaseModel):
    """Form fields for AI generation (sent as multipart so a file can be attached)."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    subject: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    topic: ShortText = ""
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    difficulty: Difficulty = "medium"
    question_count: int = Field(default=10, ge=1, le=50)
    source_text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200_000)] = ""
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    marks_per_question: float = Field(default=1.0, gt=0, le=100)
    negative_marks: float = Field(default=0.0, ge=0, le=100)
    quality_review: bool = False

    @model_validator(mode="after")
    def _check(self) -> "GenerateTestForm":
        if self.negative_marks > self.marks_per_question:
            raise ValueError("Negative marks cannot exceed the marks for a correct answer.")
        return self


# --------------------------------------------------------------------------- attempts


class AnswerUpdate(BaseModel):
    selected_option: int | None = Field(default=None, ge=0, lt=MAX_OPTIONS)
    marked_for_review: bool = False
    time_spent_seconds: int = Field(default=0, ge=0, le=86_400)


class AnswerBatchItem(AnswerUpdate):
    position: int = Field(ge=0)


class SubmitRequest(BaseModel):
    reason: SubmitReason = "manual"
    answers: list[AnswerBatchItem] = Field(default_factory=list, max_length=500)


class AttemptQuestion(BaseModel):
    position: int
    text: str
    options: list[str]
    topic: str
    selected_option: int | None
    marked_for_review: bool
    time_spent_seconds: int


class AttemptSummary(ORMModel):
    id: str
    test_id: int | None
    test_title: str
    subject: str
    topic: str
    category: str
    difficulty: str
    status: AttemptStatus
    submit_reason: str | None
    duration_seconds: int
    marks_per_question: float
    negative_marks: float
    started_at: datetime
    deadline_at: datetime
    submitted_at: datetime | None
    score: float | None
    max_score: float
    percentage: float | None
    correct_count: int
    incorrect_count: int
    unanswered_count: int
    question_count: int
    time_spent_seconds: int | None


class AttemptSession(AttemptSummary):
    """What the exam screen needs. Never includes correct answers."""

    server_time: datetime
    questions: list[AttemptQuestion]


class AnswerSaved(BaseModel):
    position: int
    selected_option: int | None
    marked_for_review: bool
    time_spent_seconds: int
    server_time: datetime


class TopicStat(BaseModel):
    topic: str
    total: int
    correct: int
    incorrect: int
    unanswered: int
    accuracy: float | None


class ResultQuestion(BaseModel):
    position: int
    text: str
    options: list[str]
    correct_option: int
    selected_option: int | None
    is_correct: bool | None
    marks_awarded: float
    marked_for_review: bool
    explanation: str
    topic: str
    time_spent_seconds: int


class AttemptResult(AttemptSummary):
    accuracy: float | None
    negative_marks_total: float
    topic_breakdown: list[TopicStat]
    questions: list[ResultQuestion]
    already_submitted: bool = False


# --------------------------------------------------------------------------- analytics


class AnalyticsSummary(BaseModel):
    total_attempts: int
    tests_taken: int
    in_progress_attempts: int
    average_percentage: float | None
    best_percentage: float | None
    accuracy: float | None
    total_correct: int
    total_incorrect: int
    total_unanswered: int
    total_time_seconds: int
    average_time_per_question_seconds: float | None


class SubjectStat(BaseModel):
    subject: str
    attempts: int
    average_percentage: float | None


class TrendPoint(BaseModel):
    attempt_id: str
    test_title: str
    submitted_at: datetime
    percentage: float


class AnalyticsOverview(BaseModel):
    summary: AnalyticsSummary
    topics: list[TopicStat]
    subjects: list[SubjectStat]
    trend: list[TrendPoint]
    recent_attempts: list[AttemptSummary]


class HealthStatus(BaseModel):
    status: Literal["ok"]
    database: bool
    ai_configured: bool
    model: str
