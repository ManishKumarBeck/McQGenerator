"""Turn uploaded files and fetched web pages into text segments with page/section metadata."""

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ...errors import InvalidInputError
from ..documents import decode_text, normalize_text

logger = logging.getLogger(__name__)

EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".text": "txt",
    ".md": "md",
    ".markdown": "md",
    ".epub": "epub",
    ".html": "html",
    ".htm": "html",
}
SUPPORTED_UPLOADS = ".pdf, .docx, .txt, .md, .epub"

_BLOCK_TAGS = ["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote", "dt", "dd", "figcaption", "td", "th"]
_HEADING_TAGS = {"h1", "h2", "h3", "h4"}
_NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
    "iframe",
    "button",
]


@dataclass
class Segment:
    text: str
    page: int | None = None
    section: str = ""


@dataclass
class ExtractedDocument:
    title: str
    file_type: str
    segments: list[Segment] = field(default_factory=list)
    page_count: int | None = None

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)


def detect_file_type(filename: str) -> str:
    suffix = PurePath(filename or "").suffix.lower()
    if suffix not in EXTENSIONS or EXTENSIONS[suffix] == "html":
        raise InvalidInputError(f"Unsupported file type. Upload one of: {SUPPORTED_UPLOADS}.")
    return EXTENSIONS[suffix]


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename or "document").stem
    return re.sub(r"[_\-]+", " ", stem).strip()[:300] or "Untitled document"


def _clean(text: str) -> str:
    return normalize_text(text or "")


# --------------------------------------------------------------------------- formats


def _pdf(data: bytes, fallback_title: str) -> ExtractedDocument:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise InvalidInputError("This PDF is password-protected.") from exc
        title = ""
        try:
            title = (reader.metadata.title or "") if reader.metadata else ""
        except Exception:  # broken metadata is common and harmless
            title = ""
        segments = []
        for number, page in enumerate(reader.pages, start=1):
            text = _clean(page.extract_text() or "")
            if text:
                segments.append(Segment(text=text, page=number))
        page_count = len(reader.pages)
    except InvalidInputError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise InvalidInputError("The PDF could not be read. It may be corrupted.") from exc
    return ExtractedDocument(
        title=title.strip()[:300] or fallback_title, file_type="pdf", segments=segments, page_count=page_count
    )


def _docx(data: bytes, fallback_title: str) -> ExtractedDocument:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = Document(io.BytesIO(data))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise InvalidInputError("The Word document could not be read. Is it a valid .docx file?") from exc

    title = (document.core_properties.title or "").strip()
    section = ""
    segments: list[Segment] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        if style.startswith("Heading") or style == "Title":
            section = text[:300]
            if style == "Title" and not title:
                title = text
        segments.append(Segment(text=text, section=section))
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                segments.append(Segment(text=" | ".join(dict.fromkeys(cells)), section=section))
    return ExtractedDocument(title=title[:300] or fallback_title, file_type="docx", segments=segments)


def _plain(data: bytes, fallback_title: str, file_type: str) -> ExtractedDocument:
    text = _clean(decode_text(data))
    if file_type != "md":
        return ExtractedDocument(title=fallback_title, file_type=file_type, segments=[Segment(text=text)])
    segments: list[Segment] = []
    section = ""
    title = ""
    buffer: list[str] = []

    def flush() -> None:
        body = _clean("\n".join(buffer))
        if body:
            segments.append(Segment(text=body, section=section))
        buffer.clear()

    for line in text.splitlines():
        heading = re.match(r"^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush()
            section = heading.group(2).strip()[:300]
            if heading.group(1) == "#" and not title:
                title = section
        buffer.append(line)
    flush()
    return ExtractedDocument(title=title or fallback_title, file_type="md", segments=segments)


def _html_segments(soup: BeautifulSoup) -> list[Segment]:
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    segments: list[Segment] = []
    section = ""
    for element in root.find_all(_BLOCK_TAGS):
        # Skip blocks nested in another block (e.g. <p> inside <li>) to avoid duplicates.
        if element.find_parent(_BLOCK_TAGS):
            continue
        raw = element.get_text(" ", strip=True)
        # Preformatted blocks keep their line breaks; other HTML whitespace is not meaningful.
        text = _clean(raw) if element.name == "pre" else " ".join(raw.split())
        if not text:
            continue
        if element.name in _HEADING_TAGS:
            section = text[:300]
        segments.append(Segment(text=text, section=section))
    if not segments:
        text = _clean(root.get_text("\n", strip=True))
        if text:
            segments.append(Segment(text=text))
    return segments


def _html_title(soup: BeautifulSoup) -> str:
    for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            return str(meta["content"]).strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    heading = soup.find("h1")
    return heading.get_text(" ", strip=True) if heading else ""


def _html(data: bytes, fallback_title: str) -> ExtractedDocument:
    soup = BeautifulSoup(decode_text(data), "html.parser")
    title = _html_title(soup)
    return ExtractedDocument(
        title=title[:300] or fallback_title, file_type="html", segments=_html_segments(soup)
    )


def _epub(data: bytes, fallback_title: str) -> ExtractedDocument:
    import ebooklib
    from ebooklib import epub

    try:
        book = epub.read_epub(io.BytesIO(data), options={"ignore_ncx": True})
    except Exception as exc:  # ebooklib raises a variety of exceptions for bad files
        raise InvalidInputError(
            "The EPUB file could not be read. It may be corrupted or DRM-protected."
        ) from exc

    titles = book.get_metadata("DC", "title")
    title = titles[0][0].strip() if titles and titles[0] and titles[0][0] else ""
    segments: list[Segment] = []
    chapter_number = 0
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        chapter_segments = _html_segments(soup)
        if not chapter_segments:
            continue
        chapter_number += 1
        heading = soup.find(["h1", "h2", "h3"])
        chapter = heading.get_text(" ", strip=True)[:300] if heading else f"Chapter {chapter_number}"
        for segment in chapter_segments:
            segment.section = segment.section or chapter
        segments.extend(chapter_segments)
    return ExtractedDocument(title=title[:300] or fallback_title, file_type="epub", segments=segments)


def extract_document(data: bytes, file_type: str, *, fallback_title: str) -> ExtractedDocument:
    if not data:
        raise InvalidInputError("The file is empty.")
    if file_type == "pdf":
        document = _pdf(data, fallback_title)
    elif file_type == "docx":
        document = _docx(data, fallback_title)
    elif file_type in ("txt", "md"):
        document = _plain(data, fallback_title, file_type)
    elif file_type == "epub":
        document = _epub(data, fallback_title)
    elif file_type == "html":
        document = _html(data, fallback_title)
    else:  # pragma: no cover - guarded by detect_file_type
        raise InvalidInputError("Unsupported document type.")

    if document.char_count < 50:
        if file_type == "pdf":
            raise InvalidInputError(
                "No text could be extracted. Scanned (image-only) PDFs are not supported; "
                "use a PDF with selectable text."
            )
        raise InvalidInputError("No readable text was found in this document.")
    return document
