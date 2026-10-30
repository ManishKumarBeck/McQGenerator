import pytest
from fastapi.testclient import TestClient

from app.errors import GenerationError

from .conftest import SAMPLE_QUESTIONS, question
from .test_documents import make_text_pdf


def test_health(client):
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "database": True, "ai_configured": True, "model": "gpt-4o-mini"}


def test_create_and_get_test(client, make_test):
    created = make_test()
    assert created["question_count"] == 4
    assert created["status"] == "published"
    assert created["source"] == "manual"
    fetched = client.get(f"/api/tests/{created['id']}").json()
    assert [q["position"] for q in fetched["questions"]] == [0, 1, 2, 3]
    assert fetched["questions"][0]["correct_option"] == 1


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"title": "  "}, "title"),
        ({"questions": [question("Q?", ["a", ""], 0)]}, "Options cannot be empty"),
        ({"questions": [question("Q?", ["a", "A "], 0)]}, "unique"),
        ({"questions": [question("Q?", ["a"], 0)]}, "at least 2"),
        ({"questions": [question("Q?", ["a", "b"], 2)]}, "correct_option"),
        ({"questions": [question("Q?", ["a", "b"], -1)]}, "greater than or equal"),
        ({"questions": [question("", ["a", "b"], 0)]}, "at least 1 character"),
        ({"status": "published", "questions": []}, "at least one question"),
        ({"negative_marks": 5, "marks_per_question": 1}, "cannot exceed"),
        ({"duration_minutes": 0}, "greater than or equal to 1"),
        ({"difficulty": "extreme"}, "difficulty"),
    ],
)
def test_create_validation(client, overrides, fragment):
    payload = {"title": "T", "status": "draft", "questions": SAMPLE_QUESTIONS[:1]}
    payload.update(overrides)
    response = client.post("/api/tests", json=payload)
    assert response.status_code == 422
    assert fragment in response.text


def test_draft_without_questions_is_allowed(client):
    response = client.post("/api/tests", json={"title": "Empty draft"})
    assert response.status_code == 201
    assert response.json()["question_count"] == 0


def test_list_search_and_filters(client, make_test):
    make_test(title="Algebra basics", subject="Math")
    make_test(title="World capitals", subject="Geography", status="draft")
    assert len(client.get("/api/tests").json()) == 2
    assert [t["title"] for t in client.get("/api/tests", params={"search": "alge"}).json()] == [
        "Algebra basics"
    ]
    assert [t["title"] for t in client.get("/api/tests", params={"status": "draft"}).json()] == [
        "World capitals"
    ]
    assert [t["title"] for t in client.get("/api/tests", params={"subject": "Math"}).json()] == [
        "Algebra basics"
    ]
    assert client.get("/api/tests", params={"status": "bogus"}).status_code == 422


def test_update_replaces_questions_and_keeps_ids(client, make_test):
    test = make_test()
    questions = test["questions"]
    kept = {**questions[1], "text": "Capital of France (edited)?"}
    new = question("New question?", ["x", "y"], 1)
    payload = {**test, "questions": [kept, new]}
    response = client.put(f"/api/tests/{test['id']}", json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert [q["text"] for q in updated["questions"]] == ["Capital of France (edited)?", "New question?"]
    assert updated["questions"][0]["id"] == questions[1]["id"]
    assert updated["questions"][0]["position"] == 0
    assert updated["question_count"] == 2


def test_missing_test_returns_404(client):
    assert client.get("/api/tests/999").status_code == 404
    assert client.put("/api/tests/999", json={"title": "x"}).json()["code"] == "not_found"
    assert client.delete("/api/tests/999").status_code == 404


def test_duplicate_creates_independent_draft(client, make_test):
    test = make_test()
    copy = client.post(f"/api/tests/{test['id']}/duplicate").json()
    assert copy["id"] != test["id"]
    assert copy["title"] == "Sample test (copy)"
    assert copy["status"] == "draft"
    assert [q["text"] for q in copy["questions"]] == [q["text"] for q in test["questions"]]
    assert {q["id"] for q in copy["questions"]}.isdisjoint({q["id"] for q in test["questions"]})


def test_delete_test(client, make_test):
    test = make_test()
    assert client.delete(f"/api/tests/{test['id']}").status_code == 204
    assert client.get(f"/api/tests/{test['id']}").status_code == 404


# --------------------------------------------------------------------------- generation


def test_generate_from_topic_creates_draft(client, generator):
    response = client.post(
        "/api/tests/generate",
        data={
            "subject": "Biology",
            "topic": "Cells",
            "difficulty": "hard",
            "question_count": "3",
            "negative_marks": "0.25",
            "category": "Grade 10",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    test = body["test"]
    assert test["status"] == "draft"
    assert test["source"] == "ai"
    assert test["title"] == "Biology - Cells"
    assert test["question_count"] == 3
    assert test["negative_marks"] == 0.25
    assert test["generation_notes"] == "Looks good."
    assert test["duration_minutes"] == 5
    call = generator.calls[0]
    assert (call.subject, call.topic, call.difficulty, call.count, call.source_text) == (
        "Biology",
        "Cells",
        "hard",
        3,
        None,
    )


def test_generate_from_uploaded_pdf_and_text(client, generator):
    pdf = make_text_pdf("Mitochondria are the powerhouse of the cell")
    response = client.post(
        "/api/tests/generate",
        data={"question_count": "2", "source_text": "Extra notes."},
        files={"file": ("notes.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    source = generator.calls[0].source_text
    assert source.startswith("Extra notes.")
    assert "Mitochondria are the powerhouse" in source
    assert response.json()["test"]["title"] == "AI generated test"


def test_generate_truncates_long_source(client, generator, settings):
    settings.max_source_chars = 1000
    response = client.post("/api/tests/generate", data={"question_count": "1", "source_text": "word " * 2000})
    assert response.status_code == 201
    assert len(generator.calls[0].source_text) <= 1000
    assert any("first 1,000 characters" in w for w in response.json()["warnings"])


@pytest.mark.parametrize(
    "data,files,fragment",
    [
        ({"question_count": "3"}, None, "Provide a subject or topic"),
        ({"subject": "x", "question_count": "31"}, None, "at most 30"),
        ({"subject": "x", "question_count": "0"}, None, "greater than or equal to 1"),
        ({"subject": "x", "difficulty": "impossible"}, None, "difficulty"),
        ({"subject": "x"}, {"file": ("a.exe", b"MZ", "application/octet-stream")}, "Unsupported file type"),
        ({"subject": "x"}, {"file": ("a.txt", b"", "text/plain")}, "empty"),
    ],
)
def test_generate_validation(client, generator, data, files, fragment):
    response = client.post("/api/tests/generate", data=data, files=files)
    assert response.status_code == 422
    assert fragment in response.text
    assert generator.calls == []


def test_generate_rejects_oversized_upload(client, settings):
    settings.max_upload_mb = 0.001
    response = client.post(
        "/api/tests/generate", data={"subject": "x"}, files={"file": ("a.txt", b"x" * 5000, "text/plain")}
    )
    assert response.status_code == 422
    assert "too large" in response.json()["detail"]


def test_generation_errors_are_returned_cleanly(client, generator):
    generator.error = GenerationError("OpenAI rate limit reached.", code="ai_rate_limited", status_code=429)
    response = client.post("/api/tests/generate", data={"subject": "x", "question_count": "2"})
    assert response.status_code == 429
    assert response.json() == {"detail": "OpenAI rate limit reached.", "code": "ai_rate_limited"}
    assert client.get("/api/tests").json() == []  # nothing half-saved


def test_unexpected_errors_do_not_leak_details(client, generator):
    generator.error = RuntimeError("secret internals")
    client = TestClient(client.app, raise_server_exceptions=False)
    response = client.post("/api/tests/generate", data={"subject": "x", "question_count": "2"})
    assert response.status_code == 500
    assert "secret" not in response.text
