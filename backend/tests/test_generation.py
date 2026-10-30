import random

import httpx2
import openai
import pytest

from app.config import Settings
from app.errors import AppError, GenerationError
from app.services import generation as gen
from app.services.generation import (
    GenerationParams,
    LLMQuestion,
    LLMQuiz,
    LLMReview,
    OpenAIQuestionGenerator,
    build_generation_prompt,
    sanitize_questions,
)


def llm_q(text="What is 2 + 2?", options=("3", "4", "5", "6"), correct="B", topic="Arithmetic"):
    return LLMQuestion(
        question=text, options=list(options), correct_option=correct, explanation="Because.", topic=topic
    )


def params(**overrides) -> GenerationParams:
    data = dict(subject="Math", topic="Addition", category="", difficulty="easy", count=2)
    data.update(overrides)
    return GenerationParams(**data)


# --------------------------------------------------------------------------- sanitize


def test_sanitize_keeps_correct_answer_after_shuffling():
    for seed in range(20):
        questions, warnings = sanitize_questions([llm_q()], requested=1, rng=random.Random(seed))
        q = questions[0]
        assert q.options[q.correct_option] == "4"
        assert sorted(q.options) == ["3", "4", "5", "6"]
        assert warnings == []


def test_sanitize_strips_consistent_letter_prefixes_only():
    prefixed = llm_q(options=("A) Paris", "B) Rome", "C) Oslo", "D) Bern"), correct="A")
    questions, _ = sanitize_questions([prefixed], requested=1, rng=random.Random(1))
    assert sorted(questions[0].options) == ["Bern", "Oslo", "Paris", "Rome"]
    assert questions[0].options[questions[0].correct_option] == "Paris"

    # "A. Lincoln" is a real answer, not a prefix, because the others are not prefixed.
    mixed = llm_q(text="Who?", options=("A. Lincoln", "Washington", "Adams", "Grant"), correct="A")
    questions, _ = sanitize_questions([mixed], requested=1, rng=random.Random(1))
    assert "A. Lincoln" in questions[0].options


def test_sanitize_drops_invalid_and_duplicate_questions():
    raw = [
        llm_q(),
        llm_q(text="what is 2+2"),  # duplicate after normalisation
        llm_q(text="Three options?", options=("a", "b", "c")),
        llm_q(text="Duplicate options?", options=("a", "A", "b", "c")),
        llm_q(text="   "),
        llm_q(text="Valid two?", options=("w", "x", "y", "z"), correct="D"),
    ]
    questions, warnings = sanitize_questions(raw, requested=5, rng=random.Random(0))
    assert [q.text for q in questions] == ["What is 2 + 2?", "Valid two?"]
    assert any("4 malformed or duplicate" in w for w in warnings)
    assert any("Only 2 of the 5" in w for w in warnings)


def test_sanitize_trims_extra_questions():
    raw = [llm_q(text=f"Question {i}?") for i in range(5)]
    questions, warnings = sanitize_questions(raw, requested=3, rng=random.Random(0))
    assert len(questions) == 3
    assert warnings == []


# --------------------------------------------------------------------------- prompts


def test_prompt_includes_source_and_survives_braces():
    prompt = build_generation_prompt(params(source_text="dict = {'a': 1}", instructions="Focus on syntax"))
    assert "{'a': 1}" in prompt
    assert "Focus on syntax" in prompt
    assert "Number of questions: 2" in prompt
    assert "Easy:" in prompt


def test_prompt_without_source_uses_general_knowledge():
    prompt = build_generation_prompt(params(source_text=None))
    assert "No source material" in prompt


# --------------------------------------------------------------------------- generator


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, openai_api_key="sk-test-not-real")


def fake_invoke(responses):
    calls = []

    def _invoke(self, schema, system_prompt, user_prompt, max_tokens):
        calls.append((schema, user_prompt, max_tokens))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return _invoke, calls


def test_generate_without_review(monkeypatch, settings):
    invoke, calls = fake_invoke([LLMQuiz(questions=[llm_q(), llm_q(text="Second?")])])
    monkeypatch.setattr(OpenAIQuestionGenerator, "_invoke_structured", invoke)
    result = OpenAIQuestionGenerator(settings, rng=random.Random(0)).generate(params())
    assert len(result.questions) == 2
    assert len(calls) == 1
    assert calls[0][2] == 350 * 2 + 800


def test_generate_with_quality_review_uses_revised_questions(monkeypatch, settings):
    revised = [llm_q(text="Revised one?"), llm_q(text="Revised two?")]
    invoke, calls = fake_invoke(
        [
            LLMQuiz(questions=[llm_q(), llm_q(text="Second?")]),
            LLMReview(notes="Fixed wording.", questions=revised),
        ]
    )
    monkeypatch.setattr(OpenAIQuestionGenerator, "_invoke_structured", invoke)
    result = OpenAIQuestionGenerator(settings).generate(params(quality_review=True))
    assert [q.text for q in result.questions] == ["Revised one?", "Revised two?"]
    assert result.notes == "Fixed wording."
    assert calls[1][0] is LLMReview


def test_review_failure_falls_back_to_original(monkeypatch, settings):
    invoke, _ = fake_invoke([LLMQuiz(questions=[llm_q(), llm_q(text="Second?")]), GenerationError("boom")])
    monkeypatch.setattr(OpenAIQuestionGenerator, "_invoke_structured", invoke)
    result = OpenAIQuestionGenerator(settings).generate(params(quality_review=True))
    assert len(result.questions) == 2
    assert any("quality review step failed" in w for w in result.warnings)


def test_review_changing_count_is_ignored(monkeypatch, settings):
    invoke, _ = fake_invoke(
        [LLMQuiz(questions=[llm_q(), llm_q(text="Second?")]), LLMReview(notes="", questions=[llm_q()])]
    )
    monkeypatch.setattr(OpenAIQuestionGenerator, "_invoke_structured", invoke)
    result = OpenAIQuestionGenerator(settings).generate(params(quality_review=True))
    assert [q.text for q in result.questions] == ["What is 2 + 2?", "Second?"]
    assert any("changed the question count" in w for w in result.warnings)


def test_no_usable_questions_is_an_error(monkeypatch, settings):
    invoke, _ = fake_invoke([LLMQuiz(questions=[llm_q(options=("a", "b"))])])
    monkeypatch.setattr(OpenAIQuestionGenerator, "_invoke_structured", invoke)
    with pytest.raises(GenerationError, match="usable"):
        OpenAIQuestionGenerator(settings).generate(params())


def test_missing_api_key_is_reported_clearly():
    generator = OpenAIQuestionGenerator(Settings(_env_file=None, openai_api_key=None))
    with pytest.raises(AppError) as excinfo:
        generator.generate(params())
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "ai_not_configured"


def test_blank_api_key_counts_as_missing():
    assert not Settings(_env_file=None, openai_api_key="  ").has_openai_key


def test_legacy_openai_key_env_name_is_supported(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_KEY", "sk-legacy")
    settings = Settings(_env_file=None)
    assert settings.openai_api_key.get_secret_value() == "sk-legacy"
    assert "sk-legacy" not in repr(settings)


class _Raw:
    def __init__(self, finish_reason=None, refusal=None):
        self.response_metadata = {"finish_reason": finish_reason}
        self.additional_kwargs = {"refusal": refusal} if refusal else {}


class _FakeRunnable:
    def __init__(self, output):
        self.output = output

    def invoke(self, _messages):
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class _FakeLLM:
    def __init__(self, output):
        self.output = output

    def with_structured_output(self, schema, **kwargs):
        assert kwargs["method"] == "json_schema" and kwargs["include_raw"] is True
        return _FakeRunnable(self.output)


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(
        status, request=httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    )


@pytest.mark.parametrize(
    "error,code,status",
    [
        (openai.AuthenticationError("bad key", response=_response(401), body=None), "ai_auth_failed", 502),
        (
            openai.RateLimitError("insufficient_quota", response=_response(429), body=None),
            "ai_quota_exceeded",
            429,
        ),
        (openai.RateLimitError("slow down", response=_response(429), body=None), "ai_rate_limited", 429),
        (openai.APITimeoutError(request=httpx2.Request("POST", "https://x")), "ai_timeout", 504),
        (openai.APIConnectionError(request=httpx2.Request("POST", "https://x")), "ai_unreachable", 502),
        (openai.BadRequestError("too long", response=_response(400), body=None), "ai_bad_request", 422),
        (RuntimeError("weird"), "generation_failed", 502),
    ],
)
def test_llm_errors_are_translated(monkeypatch, settings, error, code, status):
    monkeypatch.setattr(OpenAIQuestionGenerator, "_create_llm", lambda self, max_tokens: _FakeLLM(error))
    with pytest.raises(AppError) as excinfo:
        OpenAIQuestionGenerator(settings).generate(params())
    assert (excinfo.value.code, excinfo.value.status_code) == (code, status)


@pytest.mark.parametrize(
    "raw,match",
    [
        (_Raw(finish_reason="length"), "cut off"),
        (_Raw(refusal="I can't"), "declined"),
        (_Raw(finish_reason="stop"), "invalid response"),
    ],
)
def test_unparseable_output(monkeypatch, settings, raw, match):
    output = {"parsed": None, "raw": raw, "parsing_error": ValueError("bad json")}
    monkeypatch.setattr(OpenAIQuestionGenerator, "_create_llm", lambda self, max_tokens: _FakeLLM(output))
    with pytest.raises(GenerationError, match=match):
        OpenAIQuestionGenerator(settings).generate(params())


def test_successful_structured_call(monkeypatch, settings):
    output = {
        "parsed": LLMQuiz(questions=[llm_q(), llm_q(text="Two?")]),
        "raw": _Raw("stop"),
        "parsing_error": None,
    }
    monkeypatch.setattr(OpenAIQuestionGenerator, "_create_llm", lambda self, max_tokens: _FakeLLM(output))
    result = OpenAIQuestionGenerator(settings).generate(params())
    assert len(result.questions) == 2


def test_chat_model_is_configured_from_settings(settings):
    llm = OpenAIQuestionGenerator(settings)._create_llm(1234)
    assert llm.model_name == settings.openai_model
    assert llm.max_tokens == 1234
    assert gen.OPTIONS_PER_QUESTION == 4
