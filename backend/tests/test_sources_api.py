"""API tests for the source library and retrieval-augmented generation."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.errors import InvalidInputError
from app.main import create_app
from app.services.sources import library as library_service
from app.services.sources.fetch import FetchedDocument

from .test_sources_units import HTML_PAGE, docx_bytes, multi_page_pdf

BIOLOGY = "\n\n".join(
    [
        "Chapter 1. Cells\n\nCells are the basic unit of life. The nucleus stores DNA and the membrane controls "
        "what enters the cell. " * 6,
        "Chapter 2. Photosynthesis\n\nPlants capture sunlight with chlorophyll in chloroplasts and convert carbon "
        "dioxide and water into glucose and oxygen. " * 6,
        "Chapter 3. Respiration\n\nMitochondria release energy from glucose through cellular respiration, "
        "producing ATP, carbon dioxide and water. " * 6,
        "Chapter 4. Genetics\n\nGenes are sections of DNA that code for proteins. Alleles are different versions "
        "of the same gene inherited from parents. " * 6,
    ]
)


def upload(client, name="biology.txt", data=BIOLOGY.encode(), title=""):
    response = client.post("/api/sources/upload", files={"file": (name, data)}, data={"title": title})
    assert response.status_code == 202, response.text
    return response.json()


def get(client, source_id):
    return client.get(f"/api/sources/{source_id}").json()


# --------------------------------------------------------------------------- library


def test_upload_is_indexed_with_embeddings(client, embedder):
    created = upload(client)
    assert created["status"] == "processing"
    source = get(client, created["id"])  # background task has run by now
    assert source["status"] == "ready"
    assert source["progress"] == 100
    assert source["title"] == "biology"
    assert source["chunk_count"] >= 2
    assert source["char_count"] > 2000
    assert source["semantic_search"] is True
    assert embedder.calls >= 1
    assert [s["id"] for s in client.get("/api/sources").json()] == [created["id"]]


def test_upload_without_api_key_uses_keyword_search(client, embeddings_enabled):
    embeddings_enabled["on"] = False
    source = get(client, upload(client)["id"])
    assert source["status"] == "ready"
    assert source["semantic_search"] is False
    assert "keyword search only" in source["notes"]


@pytest.mark.parametrize(
    "name,data",
    [("doc.pdf", None), ("doc.docx", None)],
)
def test_upload_pdf_and_docx(client, name, data):
    data = (
        multi_page_pdf(
            ["Page one is about cells and the membrane.", "Page two is about photosynthesis and light."]
        )
        if name.endswith(".pdf")
        else docx_bytes()
    )
    source = get(client, upload(client, name, data)["id"])
    assert source["status"] == "ready", source
    assert source["file_type"] == name.rsplit(".", 1)[1]
    if name.endswith(".pdf"):
        assert source["page_count"] == 2


@pytest.mark.parametrize(
    "name,data,fragment",
    [
        ("deck.pptx", b"data", "Unsupported file type"),
        ("empty.txt", b"", "empty"),
    ],
)
def test_upload_validation(client, name, data, fragment):
    response = client.post("/api/sources/upload", files={"file": (name, data)})
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert client.get("/api/sources").json() == []


def test_upload_too_large(client, settings):
    settings.max_library_upload_mb = 0.001
    response = client.post("/api/sources/upload", files={"file": ("big.txt", b"x" * 5000)})
    assert response.status_code == 422
    assert "too large" in response.json()["detail"]


def test_unreadable_file_fails_with_message(client):
    source = get(client, upload(client, "broken.docx", b"not really a docx")["id"])
    assert source["status"] == "failed"
    assert "Word document could not be read" in source["error"]


def test_large_documents_are_capped(client, settings):
    settings.max_library_chars = 10_000
    source = get(client, upload(client, data=(BIOLOGY * 10).encode())["id"])
    assert source["status"] == "ready"
    assert source["char_count"] <= 10_000
    assert "Only the first 10,000 characters" in source["notes"]


def test_rename_and_delete(client):
    source = upload(client)
    renamed = client.patch(f"/api/sources/{source['id']}", json={"title": "Campbell Biology"}).json()
    assert renamed["title"] == "Campbell Biology"
    assert client.patch(f"/api/sources/{source['id']}", json={"title": " "}).status_code == 422
    assert client.delete(f"/api/sources/{source['id']}").status_code == 204
    assert client.get(f"/api/sources/{source['id']}").status_code == 404
    assert client.delete("/api/sources/999").status_code == 404


def test_search_finds_relevant_passage(client):
    source = upload(client)
    hits = client.get(f"/api/sources/{source['id']}/search", params={"q": "mitochondria energy"}).json()
    assert hits
    assert "Mitochondria" in hits[0]["text"]
    assert hits[0]["semantic_score"] is not None
    assert hits[0]["citation"].startswith("biology")
    assert client.get(f"/api/sources/{source['id']}/search").status_code == 422


def test_reindex_adds_embeddings_later(client, embeddings_enabled):
    embeddings_enabled["on"] = False
    source = upload(client)
    assert get(client, source["id"])["semantic_search"] is False
    embeddings_enabled["on"] = True
    response = client.post(f"/api/sources/{source['id']}/reindex")
    assert response.status_code == 202
    refreshed = get(client, source["id"])
    assert refreshed["status"] == "ready"
    assert refreshed["semantic_search"] is True


def test_reindex_of_failed_file_asks_for_reupload(client):
    source = upload(client, "broken.docx", b"nope")
    response = client.post(f"/api/sources/{source['id']}/reindex")
    assert response.status_code == 409
    assert "upload the file again" in response.json()["detail"]


# --------------------------------------------------------------------------- links


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []
    responses = {}

    def fetch(url, **kwargs):
        calls.append(url)
        result = responses.get(url)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise InvalidInputError("The website returned an error (HTTP 404).")
        return result

    monkeypatch.setattr(library_service, "fetch_document", fetch)
    return calls, responses


def test_add_link(client, fake_fetch):
    calls, responses = fake_fetch
    responses["https://site.example/photosynthesis"] = FetchedDocument(
        url="https://site.example/photosynthesis", data=HTML_PAGE, file_type="html"
    )
    created = client.post("/api/sources/url", json={"url": "https://site.example/photosynthesis"})
    assert created.status_code == 202
    source = get(client, created.json()["id"])
    assert source["status"] == "ready"
    assert source["kind"] == "url"
    assert source["title"] == "Photosynthesis - Encyclopedia"  # taken from the page
    assert calls == ["https://site.example/photosynthesis"]


def test_link_with_custom_title_keeps_it(client, fake_fetch):
    _, responses = fake_fetch
    responses["https://site.example/p"] = FetchedDocument(
        url="https://site.example/p", data=HTML_PAGE, file_type="html"
    )
    source = client.post(
        "/api/sources/url", json={"url": "https://site.example/p", "title": "My notes"}
    ).json()
    assert get(client, source["id"])["title"] == "My notes"


def test_failed_link_can_be_retried(client, fake_fetch):
    calls, responses = fake_fetch
    source = client.post("/api/sources/url", json={"url": "https://site.example/later"}).json()
    failed = get(client, source["id"])
    assert failed["status"] == "failed"
    assert "HTTP 404" in failed["error"]
    responses["https://site.example/later"] = FetchedDocument(
        url="https://site.example/later", data=HTML_PAGE, file_type="html"
    )
    assert client.post(f"/api/sources/{source['id']}/reindex").status_code == 202
    assert get(client, source["id"])["status"] == "ready"
    assert len(calls) == 2


@pytest.mark.parametrize("url", ["ftp://x.org/a", "not a url", "https://u:p@site.example/"])
def test_invalid_links_rejected_immediately(client, url):
    response = client.post("/api/sources/url", json={"url": url})
    assert response.status_code == 422


# --------------------------------------------------------------------------- generation (RAG)


def test_generate_from_library_with_focus(client, generator):
    source = upload(client, title="Biology Textbook")
    response = client.post(
        "/api/tests/generate",
        data={
            "source_ids": [str(source["id"])],
            "focus": "photosynthesis chlorophyll",
            "question_count": "3",
        },
    )
    assert response.status_code == 201, response.text
    params = generator.calls[0]
    assert "[S1]" in params.source_text
    assert "chlorophyll" in params.source_text
    assert params.passage_refs and all(
        ref.startswith("Biology Textbook") for ref in params.passage_refs.values()
    )
    assert params.topic == "photosynthesis chlorophyll"
    test = response.json()["test"]
    assert test["title"] == "Biology Textbook — photosynthesis chlorophyll"
    assert all(q["source_ref"].startswith("Biology Textbook") for q in test["questions"])


def test_generate_from_whole_library_covers_document(client, generator):
    first = upload(client, title="Book A")
    second = upload(
        client, "physics.txt", ("Newton's laws describe motion and force. " * 80).encode(), "Book B"
    )
    response = client.post(
        "/api/tests/generate",
        data={
            "source_ids": [str(first["id"]), str(second["id"])],
            "question_count": "5",
            "subject": "Science",
        },
    )
    assert response.status_code == 201, response.text
    refs = set(generator.calls[0].passage_refs.values())
    assert any(r.startswith("Book A") for r in refs) and any(r.startswith("Book B") for r in refs)
    assert response.json()["test"]["title"] == "Science"


def test_citations_flow_into_attempt_results_and_pdf(client):
    source = upload(client, title="Biology Textbook")
    test = client.post(
        "/api/tests/generate", data={"source_ids": [str(source["id"])], "question_count": "2"}
    ).json()["test"]
    client.put(f"/api/tests/{test['id']}", json={**test, "status": "published"})
    attempt = client.post(f"/api/tests/{test['id']}/attempts").json()
    result = client.post(f"/api/attempts/{attempt['id']}/submit", json={}).json()
    assert all(q["source_ref"].startswith("Biology Textbook") for q in result["questions"])
    # Manual edits to the citation are kept.
    detail = client.get(f"/api/tests/{test['id']}").json()
    detail["questions"][0]["source_ref"] = "Chapter 2"
    updated = client.put(f"/api/tests/{test['id']}", json=detail).json()
    assert updated["questions"][0]["source_ref"] == "Chapter 2"

    import io

    from pypdf import PdfReader

    pdf = client.post(f"/api/tests/{test['id']}/pdf", json={}).content
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Source: Chapter 2" in text


def test_generate_focus_without_match_keyword_only(client, embeddings_enabled):
    embeddings_enabled["on"] = False
    source = upload(client)
    response = client.post(
        "/api/tests/generate", data={"source_ids": [str(source["id"])], "focus": "quantum chromodynamics"}
    )
    assert response.status_code == 422
    assert "Nothing in the selected sources matches" in response.json()["detail"]


def test_generate_rejects_unready_missing_or_mixed_sources(client, fake_fetch):
    failed = client.post("/api/sources/url", json={"url": "https://site.example/missing"}).json()
    response = client.post("/api/tests/generate", data={"source_ids": [str(failed["id"])]})
    assert response.status_code == 409
    assert "isn't ready" in response.json()["detail"]

    assert client.post("/api/tests/generate", data={"source_ids": ["999"]}).status_code == 404

    ready = upload(client)
    mixed = client.post(
        "/api/tests/generate",
        data={"source_ids": [str(ready["id"])], "source_text": "Some pasted notes here."},
    )
    assert mixed.status_code == 422
    assert "not both" in mixed.json()["detail"]


def test_budget_scales_with_question_count(client, generator, settings):
    source = upload(client, data=(BIOLOGY * 6).encode())
    client.post("/api/tests/generate", data={"source_ids": [str(source["id"])], "question_count": "2"})
    client.post("/api/tests/generate", data={"source_ids": [str(source["id"])], "question_count": "20"})
    small, large = generator.calls
    assert len(small.source_text) < len(large.source_text)
    assert len(large.source_text) <= settings.max_source_chars + 2000


# --------------------------------------------------------------------------- startup


def test_startup_marks_interrupted_sources_failed(settings, generator, tmp_path):
    settings.database_url = f"sqlite:///{(tmp_path / 'lib.db').as_posix()}"
    app = create_app(settings, generator=generator, embedder_factory=lambda: None, frontend_dist=None)
    with TestClient(app) as client:
        source = upload(client)
    with sqlite3.connect(tmp_path / "lib.db") as connection:
        connection.execute("UPDATE sources SET status='processing' WHERE id=?", (source["id"],))
    app = create_app(settings, generator=generator, embedder_factory=lambda: None, frontend_dist=None)
    with TestClient(app) as client:
        restarted = get(client, source["id"])
    assert restarted["status"] == "failed"
    assert "interrupted" in restarted["error"]


def test_old_database_is_upgraded(settings, generator, tmp_path):
    """A database created before citations existed gains the new columns on startup."""
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tests (id INTEGER PRIMARY KEY, title VARCHAR(200), description TEXT, subject VARCHAR(100),
              topic VARCHAR(150), category VARCHAR(100), difficulty VARCHAR(10), duration_minutes INTEGER,
              marks_per_question FLOAT, negative_marks FLOAT, shuffle_questions BOOLEAN, shuffle_options BOOLEAN,
              status VARCHAR(20), source VARCHAR(20), generation_notes TEXT, created_at DATETIME, updated_at DATETIME);
            CREATE TABLE questions (id INTEGER PRIMARY KEY, test_id INTEGER REFERENCES tests(id) ON DELETE CASCADE,
              position INTEGER, text TEXT, options JSON, correct_option INTEGER, explanation TEXT, topic VARCHAR(150));
            INSERT INTO tests VALUES (1, 'Legacy test', '', 'Math', '', '', 'easy', 10, 1, 0, 0, 0, 'published',
              'manual', '', '2026-10-01 10:00:00', '2026-10-01 10:00:00');
            INSERT INTO questions VALUES (1, 1, 0, '2 + 2?', '["3", "4"]', 1, '', '');
            """
        )
    settings.database_url = f"sqlite:///{path.as_posix()}"
    app = create_app(settings, generator=generator, embedder_factory=lambda: None, frontend_dist=None)
    with TestClient(app) as client:
        test = client.get("/api/tests/1").json()
        assert test["questions"][0]["source_ref"] == ""
        attempt = client.post("/api/tests/1/attempts")
        assert attempt.status_code == 201


def test_document_title_is_used_unless_user_named_it(client):
    markdown = b"# Cell Biology Notes\n\n" + BIOLOGY.encode()
    assert get(client, upload(client, "notes.md", markdown)["id"])["title"] == "Cell Biology Notes"
    assert (
        get(client, upload(client, "notes.md", markdown, title="My own name")["id"])["title"] == "My own name"
    )
