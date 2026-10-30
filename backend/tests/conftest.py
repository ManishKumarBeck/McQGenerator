"""Shared fixtures. No test ever calls the real OpenAI API."""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import utcnow
from app.main import create_app
from app.services import attempts as attempt_service
from app.services.generation import GeneratedQuestion, GenerationParams, GenerationResult


class FakeGenerator:
    """Deterministic stand-in for the OpenAI generator."""

    def __init__(self) -> None:
        self.calls: list[GenerationParams] = []
        self.error: Exception | None = None
        self.warnings: list[str] = []

    def generate(self, params: GenerationParams) -> GenerationResult:
        self.calls.append(params)
        if self.error:
            raise self.error
        questions = [
            GeneratedQuestion(
                text=f"Generated question {i + 1} about {params.topic or params.subject}?",
                options=[f"Option {i + 1}{letter}" for letter in "ABCD"],
                correct_option=i % 4,
                explanation=f"Explanation {i + 1}",
                topic=["Basics", "Advanced"][i % 2],
            )
            for i in range(params.count)
        ]
        return GenerationResult(questions=questions, warnings=list(self.warnings), notes="Looks good.")


class Clock:
    """Controllable clock patched into the attempt service."""

    def __init__(self) -> None:
        self.now = utcnow()

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        openai_api_key="sk-test-not-real",
        submission_grace_seconds=5,
        max_questions_per_generation=30,
    )


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(attempt_service, "utcnow", fake)
    return fake


@pytest.fixture
def client(settings: Settings, generator: FakeGenerator, clock: Clock) -> Iterator[TestClient]:
    app = create_app(settings, generator=generator, frontend_dist=None)
    with TestClient(app) as test_client:
        yield test_client


def question(text: str, options: list[str], correct: int, topic: str = "", explanation: str = "") -> dict:
    return {
        "text": text,
        "options": options,
        "correct_option": correct,
        "topic": topic,
        "explanation": explanation,
    }


SAMPLE_QUESTIONS = [
    question("2 + 2 = ?", ["3", "4", "5", "6"], 1, "Arithmetic", "Two plus two is four."),
    question("Capital of France?", ["Paris", "Rome", "Madrid", "Berlin"], 0, "Geography"),
    question("5 x 3 = ?", ["8", "15", "53", "2"], 1, "Arithmetic"),
    question("Largest ocean?", ["Atlantic", "Indian", "Pacific", "Arctic"], 2, "Geography"),
]


@pytest.fixture
def make_test(client: TestClient) -> Callable[..., dict]:
    def _make(**overrides) -> dict:
        payload = {
            "title": "Sample test",
            "subject": "General",
            "topic": "Mixed",
            "difficulty": "easy",
            "duration_minutes": 10,
            "marks_per_question": 4,
            "negative_marks": 1,
            "status": "published",
            "questions": SAMPLE_QUESTIONS,
        }
        payload.update(overrides)
        response = client.post("/api/tests", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
