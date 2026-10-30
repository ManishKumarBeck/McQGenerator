"""Extracting plain text from uploaded source documents."""

import io
import logging
import re
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..errors import InvalidInputError

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md")


@dataclass
class SourceText:
    text: str
    warnings: list[str] = field(default_factory=list)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pypdf raises several types here
                raise InvalidInputError("This PDF is password-protected.") from exc
        pages = [(page.extract_text() or "") for page in reader.pages]
    except InvalidInputError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        logger.info("Could not parse PDF: %s", exc)
        raise InvalidInputError("The PDF could not be read. It may be corrupted.") from exc
    return "\n\n".join(pages)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_upload(filename: str, data: bytes, *, max_bytes: int) -> str:
    name = (filename or "").lower()
    if not name.endswith(SUPPORTED_EXTENSIONS):
        raise InvalidInputError("Unsupported file type. Upload a PDF, TXT or MD file.")
    if not data:
        raise InvalidInputError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise InvalidInputError(f"The file is too large. The limit is {max_bytes / (1024 * 1024):g} MB.")

    text = _extract_pdf(data) if name.endswith(".pdf") else _decode_text(data)
    text = normalize_text(text)
    if not text:
        if name.endswith(".pdf"):
            raise InvalidInputError(
                "No text could be extracted from this PDF. Scanned/image-only PDFs are not "
                "supported; paste the text instead."
            )
        raise InvalidInputError("The uploaded file contains no text.")
    return text


def prepare_source_text(text: str, *, max_chars: int) -> SourceText:
    """Normalise source material and cap its length to control token usage."""
    text = normalize_text(text)
    warnings: list[str] = []
    if len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars)
        text = text[: cut if cut > max_chars * 0.8 else max_chars].rstrip()
        warnings.append(
            f"The source material was long, so only the first {max_chars:,} characters were used."
        )
    return SourceText(text=text, warnings=warnings)
