"""Unit tests for the RAG pipeline: extraction, chunking, retrieval and safe URL fetching."""

import io
import random
import socket

import httpx
import numpy as np
import pytest

from app.errors import InvalidInputError
from app.services.sources import fetch as fetch_module
from app.services.sources.chunking import MAX_CHARS, chunk_segments
from app.services.sources.extract import Segment, detect_file_type, extract_document, title_from_filename
from app.services.sources.fetch import fetch_document, validate_url
from app.services.sources.retrieval import BM25, Passage, rank, select_passages, tokenize

from .conftest import FakeEmbedder

PARAGRAPH = (
    "Photosynthesis converts light energy into chemical energy. Chlorophyll in the chloroplasts absorbs "
    "sunlight, and the plant uses it to turn carbon dioxide and water into glucose and oxygen. "
)


# --------------------------------------------------------------------------- sample documents


def multi_page_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one line of text per page."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    font_id = 3 + 2 * len(pages)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, text in enumerate(pages):
        stream = f"BT /F1 11 Tf 40 760 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def docx_bytes() -> bytes:
    from docx import Document

    document = Document()
    document.core_properties.title = "Plant Biology Notes"
    document.add_heading("Photosynthesis", level=1)
    document.add_paragraph(PARAGRAPH)
    document.add_heading("Respiration", level=1)
    document.add_paragraph("Cellular respiration releases energy from glucose inside the mitochondria.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Organelle"
    table.rows[0].cells[1].text = "Mitochondria"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def epub_bytes(tmp_path) -> bytes:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("A Little Book of Cells")
    book.set_language("en")
    chapters = []
    for number, (heading, body) in enumerate(
        [
            ("Cell Structure", "Cells have a membrane, cytoplasm and a nucleus. " * 4),
            ("Cell Division", PARAGRAPH * 2),
        ],
        start=1,
    ):
        chapter = epub.EpubHtml(title=heading, file_name=f"chap_{number}.xhtml", lang="en")
        chapter.content = f"<html><body><h1>{heading}</h1><p>{body}</p></body></html>"
        book.add_item(chapter)
        chapters.append(chapter)
    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = chapters
    path = tmp_path / "book.epub"
    epub.write_epub(str(path), book)
    return path.read_bytes()


HTML_PAGE = b"""<!doctype html><html><head><title>Fallback title</title>
<meta property="og:title" content="Photosynthesis - Encyclopedia"><script>var tracking = 1;</script>
<style>p { color: red }</style></head>
<body><nav><a href="/">Home</a> Menu Sign in</nav>
<article><h1>Photosynthesis</h1><p>%s</p><h2>Light reactions</h2>
<ul><li><p>Water is split to release oxygen during the light-dependent reactions of photosynthesis.</p></li></ul>
</article><footer>Copyright notice and cookie banner</footer></body></html>""" % PARAGRAPH.encode()


# --------------------------------------------------------------------------- extraction


def test_detect_file_type_and_title():
    assert detect_file_type("Book.PDF") == "pdf"
    assert detect_file_type("notes.markdown") == "md"
    assert title_from_filename("my_biology-notes.docx") == "my biology notes"
    with pytest.raises(InvalidInputError, match="Unsupported"):
        detect_file_type("slides.pptx")
    with pytest.raises(InvalidInputError):
        detect_file_type("page.html")  # web pages are added as links, not uploads


def test_pdf_keeps_page_numbers():
    data = multi_page_pdf(
        [f"Page {i} talks about topic number {i} in some detail for testing." for i in range(1, 4)]
    )
    document = extract_document(data, "pdf", fallback_title="fallback")
    assert document.page_count == 3
    assert [s.page for s in document.segments] == [1, 2, 3]
    assert "topic number 2" in document.segments[1].text
    assert document.title == "fallback"


def test_docx_sections_and_tables():
    document = extract_document(docx_bytes(), "docx", fallback_title="x")
    assert document.title == "Plant Biology Notes"
    sections = {s.section for s in document.segments}
    assert {"Photosynthesis", "Respiration"} <= sections
    assert any("Organelle | Mitochondria" in s.text for s in document.segments)


def test_markdown_headings_become_sections():
    text = (
        b"# Biology Guide\n\nIntro paragraph about living things and their cells.\n\n## Photosynthesis\n\n"
        + PARAGRAPH.encode()
    )
    document = extract_document(text, "md", fallback_title="x")
    assert document.title == "Biology Guide"
    assert document.segments[-1].section == "Photosynthesis"


def test_epub_chapters(tmp_path):
    document = extract_document(epub_bytes(tmp_path), "epub", fallback_title="x")
    assert document.title == "A Little Book of Cells"
    assert {"Cell Structure", "Cell Division"} <= {s.section for s in document.segments}


def test_html_strips_boilerplate():
    document = extract_document(HTML_PAGE, "html", fallback_title="https://example.org")
    text = " ".join(s.text for s in document.segments)
    assert document.title == "Photosynthesis - Encyclopedia"
    assert "Chlorophyll" in text and "Water is split" in text
    for noise in ("tracking", "color: red", "Sign in", "cookie banner"):
        assert noise not in text
    assert text.count("Water is split") == 1  # <p> inside <li> not duplicated


@pytest.mark.parametrize(
    "data,file_type,message",
    [
        (b"not a zip", "docx", "Word document could not be read"),
        (b"not a zip", "epub", "EPUB file could not be read"),
        (b"%PDF-1.4 garbage", "pdf", "could not be read"),
        (b"", "txt", "empty"),
        (b"tiny", "txt", "No readable text"),
    ],
)
def test_extraction_errors(data, file_type, message):
    with pytest.raises(InvalidInputError, match=message):
        extract_document(data, file_type, fallback_title="x")


# --------------------------------------------------------------------------- chunking


def test_chunks_track_pages_and_stay_bounded():
    segments = [Segment(text=(PARAGRAPH * 3) + "\n\n" + (PARAGRAPH * 3), page=p) for p in range(1, 11)]
    chunks = chunk_segments(segments)
    assert len(chunks) > 5
    assert all(len(c.text) <= MAX_CHARS + 300 for c in chunks)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 10
    assert all(c.page_start <= c.page_end for c in chunks)
    # Consecutive chunks overlap slightly for context continuity.
    assert chunks[1].text[:80] in chunks[0].text


def test_sections_do_not_bleed_into_each_other():
    segments = [
        Segment(text=PARAGRAPH * 6, section="Chapter 1"),
        Segment(text="Chapter two text. " * 60, section="Chapter 2"),
    ]
    chunks = chunk_segments(segments)
    for chunk in chunks:
        if chunk.section == "Chapter 2":
            assert "Photosynthesis" not in chunk.text


def test_very_long_paragraph_is_split():
    chunks = chunk_segments([Segment(text="word " * 3000)])
    assert len(chunks) >= 5
    assert all(len(c.text) <= MAX_CHARS + 300 for c in chunks)


def test_no_duplicate_tail_chunk():
    chunks = chunk_segments([Segment(text=PARAGRAPH * 8)])
    assert len({c.text for c in chunks}) == len(chunks)


# --------------------------------------------------------------------------- retrieval


def passages(texts: list[str], embed: bool = False) -> list[Passage]:
    result = [Passage(key=(1, i), text=t, citation=f"Book, p. {i + 1}") for i, t in enumerate(texts)]
    if embed:
        vectors = FakeEmbedder().embed(texts)
        for passage, vector in zip(result, vectors, strict=True):
            passage.embedding = vector
    return result


TOPICS = [
    "The French Revolution began in 1789 with the storming of the Bastille in Paris. " * 5,
    "Mitochondria are the powerhouse of the cell and produce energy through respiration. " * 5,
    "Photosynthesis in plants uses chlorophyll to capture sunlight and make glucose. " * 5,
    "Newton's laws of motion describe force, mass and acceleration of moving objects. " * 5,
]


def test_tokenize_stems_and_drops_stopwords():
    assert tokenize("The cells are dividing") == ["cell", "divid"]
    assert tokenize("Photosynthesis") == tokenize("photosynthesis")


def test_bm25_prefers_matching_documents():
    scores = BM25([tokenize(t) for t in TOPICS]).scores(tokenize("chlorophyll sunlight"))
    assert int(np.argmax(scores)) == 2
    assert scores[0] == 0


def test_rank_keyword_only_excludes_non_matching():
    hits = rank(passages(TOPICS), "energy respiration", None)
    assert hits[0].passage.key == (1, 1)
    assert all(hit.keyword_score > 0 for hit in hits)


def test_rank_hybrid_uses_embeddings():
    items = passages(TOPICS, embed=True)
    query_vector = FakeEmbedder().embed(["plants capture sunlight"])[0]
    hits = rank(items, "plants capture sunlight", query_vector)
    assert hits[0].passage.key == (1, 2)
    assert hits[0].semantic_score is not None and hits[0].semantic_score > 0


def test_focused_selection_respects_budget():
    items = passages(TOPICS * 5)
    chosen = select_passages(
        items, query="French Revolution Bastille", query_embedding=None, budget_chars=1000
    )
    assert chosen and all("Bastille" in p.text for p in chosen)
    assert sum(len(p.text) for p in chosen) <= max(1000, len(chosen[0].text))


def test_focused_selection_without_matches_is_an_error():
    with pytest.raises(InvalidInputError, match="Nothing in the selected sources matches"):
        select_passages(
            passages(TOPICS), query="quantum chromodynamics", query_embedding=None, budget_chars=5000
        )


def test_coverage_spreads_across_the_document():
    texts = [f"Section {i}. " + (f"Content about subject matter number {i}. " * 12) for i in range(100)]
    chosen = select_passages(
        passages(texts),
        query=None,
        query_embedding=None,
        budget_chars=5 * len(texts[-1]),
        rng=random.Random(1),
    )
    positions = [p.key[1] for p in chosen]
    assert len(positions) == 5
    assert positions == sorted(positions)
    assert positions[0] < 25 and positions[-1] >= 75  # beginning and end of the book are both covered


def test_coverage_skips_table_of_contents():
    toc = "Contents 1 Intro 3 2 Cells 15 3 Energy 27 4 Plants 41 5 Index 99 " * 6
    texts = [toc, *TOPICS]
    chosen = select_passages(passages(texts), query=None, query_embedding=None, budget_chars=100_000)
    assert all(p.key != (1, 0) for p in chosen)


def test_empty_library_selection():
    with pytest.raises(InvalidInputError, match="no indexed text"):
        select_passages([], query=None, query_embedding=None, budget_chars=1000)


# --------------------------------------------------------------------------- safe fetching


@pytest.fixture
def public_dns(monkeypatch):
    """Pretend every host resolves to a public address (no real DNS in tests)."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        address = {"internal.example": "10.0.0.5", "localhost": "127.0.0.1"}.get(host, "93.184.216.34")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fake_getaddrinfo)


def transport(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handler)


def fetch(url, routes, **kwargs):
    return fetch_document(
        url, max_bytes=kwargs.pop("max_bytes", 1_000_000), timeout=5, transport=transport(routes), **kwargs
    )


@pytest.mark.parametrize(
    "url", ["ftp://example.org/x", "example.org", "https://user:pw@example.org/", "javascript:alert(1)"]
)
def test_invalid_urls(url):
    with pytest.raises(InvalidInputError):
        validate_url(url)


def test_fetch_html_and_follow_redirect(public_dns):
    routes = {
        "https://short.example/a": httpx.Response(301, headers={"location": "https://site.example/article"}),
        "https://site.example/article": httpx.Response(
            200, content=HTML_PAGE, headers={"content-type": "text/html; charset=utf-8"}
        ),
    }
    document = fetch("https://short.example/a", routes)
    assert document.file_type == "html"
    assert document.url == "https://site.example/article"


def test_fetch_detects_pdf(public_dns):
    routes = {
        "https://site.example/book": httpx.Response(
            200, content=b"%PDF", headers={"content-type": "application/pdf"}
        )
    }
    assert fetch("https://site.example/book", routes).file_type == "pdf"


def test_redirect_to_private_address_is_blocked(public_dns):
    routes = {
        "https://site.example/x": httpx.Response(302, headers={"location": "http://internal.example/admin"})
    }
    with pytest.raises(InvalidInputError, match="private or local"):
        fetch("https://site.example/x", routes)


def test_localhost_blocked_unless_allowed(public_dns):
    routes = {
        "http://localhost/page": httpx.Response(200, content=HTML_PAGE, headers={"content-type": "text/html"})
    }
    with pytest.raises(InvalidInputError, match="private or local"):
        fetch("http://localhost/page", routes)
    assert fetch("http://localhost/page", routes, allow_private=True).file_type == "html"


def test_redirect_loop(public_dns):
    routes = {
        "https://site.example/loop": httpx.Response(302, headers={"location": "https://site.example/loop"})
    }
    with pytest.raises(InvalidInputError, match="too many times"):
        fetch("https://site.example/loop", routes)


@pytest.mark.parametrize(
    "response,message",
    [
        (httpx.Response(404), "HTTP 404"),
        (httpx.Response(200, content=b"x" * 2000, headers={"content-type": "text/html"}), "larger than"),
        (
            httpx.Response(200, content=b"PK..", headers={"content-type": "application/zip"}),
            "unsupported kind",
        ),
    ],
)
def test_fetch_errors(public_dns, response, message):
    with pytest.raises(InvalidInputError, match=message):
        fetch("https://site.example/x", {"https://site.example/x": response}, max_bytes=1000)


def test_unresolvable_host(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fail)
    with pytest.raises(InvalidInputError, match="Couldn't find the website"):
        fetch("https://no-such-host.example/", {})


def test_network_error(public_dns):
    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(InvalidInputError, match="Couldn't download"):
        fetch_document(
            "https://site.example/", max_bytes=1000, timeout=5, transport=httpx.MockTransport(boom)
        )
