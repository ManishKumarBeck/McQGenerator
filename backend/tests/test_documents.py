import io

import pytest
from pypdf import PdfWriter

from app.errors import InvalidInputError
from app.services.documents import extract_text_from_upload, normalize_text, prepare_source_text

MB = 1024 * 1024


def make_text_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF containing `text`."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
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


def test_extracts_text_from_pdf():
    text = extract_text_from_upload("notes.PDF", make_text_pdf("Photosynthesis uses sunlight"), max_bytes=MB)
    assert "Photosynthesis uses sunlight" in text


def test_image_only_pdf_gives_helpful_error():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(InvalidInputError, match="Scanned"):
        extract_text_from_upload("scan.pdf", buffer.getvalue(), max_bytes=MB)


def test_corrupted_pdf():
    with pytest.raises(InvalidInputError, match="could not be read"):
        extract_text_from_upload("broken.pdf", b"%PDF-1.4 this is not really a pdf", max_bytes=MB)


def test_text_file_utf8_with_bom_and_braces():
    data = "﻿Sets use {braces} in Python.\r\nNext line".encode()
    assert extract_text_from_upload("a.txt", data, max_bytes=MB) == "Sets use {braces} in Python.\nNext line"


def test_text_file_windows_encoding_fallback():
    data = "Café – naïve".encode("cp1252")
    assert extract_text_from_upload("a.md", data, max_bytes=MB) == "Café – naïve"


@pytest.mark.parametrize(
    "name,data,match",
    [
        ("a.docx", b"data", "Unsupported"),
        ("a.txt", b"", "empty"),
        ("a.txt", b"   \n\t ", "no text"),
        ("big.txt", b"x" * (MB + 1), "too large"),
    ],
)
def test_rejects_invalid_uploads(name, data, match):
    with pytest.raises(InvalidInputError, match=match):
        extract_text_from_upload(name, data, max_bytes=MB)


def test_normalize_collapses_whitespace():
    assert normalize_text("a  \t b\n\n\n\nc\x00") == "a b\n\nc"


def test_prepare_source_text_truncates_with_warning():
    prepared = prepare_source_text("word " * 1000, max_chars=1000)
    assert len(prepared.text) <= 1000
    assert not prepared.text.endswith(" ")
    assert prepared.warnings and "1,000" in prepared.warnings[0]


def test_prepare_source_text_short_input_untouched():
    prepared = prepare_source_text("short text", max_chars=1000)
    assert prepared.text == "short text"
    assert prepared.warnings == []
