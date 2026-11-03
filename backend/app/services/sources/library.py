"""Source library: create, index (extract → chunk → embed), search and retrieve passages."""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from ... import schemas
from ...config import Settings
from ...database import utcnow
from ...errors import AppError, ConflictError, InvalidInputError, NotFoundError
from ...models import Source, SourceChunk
from .chunking import chunk_segments
from .embeddings import Embedder, from_blob, to_blob
from .extract import detect_file_type, extract_document, title_from_filename
from .fetch import fetch_document, validate_url
from .retrieval import Passage, rank, select_passages

logger = logging.getLogger(__name__)

EmbedderFactory = Callable[[], Embedder | None]
EMBED_BATCH = 64


# --------------------------------------------------------------------------- CRUD


def get_source(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise NotFoundError("Source not found.")
    return source


def list_sources(db: Session) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.created_at.desc(), Source.id.desc())))


def create_file_source(
    db: Session, filename: str, data: bytes, settings: Settings, title: str = ""
) -> Source:
    file_type = detect_file_type(filename)
    if not data:
        raise InvalidInputError("The uploaded file is empty.")
    if len(data) > settings.max_library_upload_bytes:
        raise InvalidInputError(f"The file is too large. The limit is {settings.max_library_upload_mb:g} MB.")
    source = Source(
        title=(title.strip() or title_from_filename(filename))[:300],
        title_locked=bool(title.strip()),
        kind="file",
        file_type=file_type,
        origin=filename[:2000],
        status="processing",
    )
    db.add(source)
    db.commit()
    return source


def create_url_source(db: Session, url: str, title: str = "") -> Source:
    url = validate_url(url)
    source = Source(
        title=(title.strip() or url)[:300],
        title_locked=bool(title.strip()),
        kind="url",
        origin=url,
        status="processing",
    )
    db.add(source)
    db.commit()
    return source


def rename_source(db: Session, source_id: int, title: str) -> Source:
    source = get_source(db, source_id)
    source.title = title.strip()[:300]
    source.title_locked = True
    db.commit()
    return source


def delete_source(db: Session, source_id: int) -> None:
    source = get_source(db, source_id)
    db.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
    db.delete(source)
    db.commit()


def mark_interrupted(db: Session) -> int:
    """Sources still 'processing' at startup were interrupted by a restart."""
    result = db.execute(
        update(Source)
        .where(Source.status == "processing")
        .values(
            status="failed",
            error=(
                "Processing was interrupted because the server stopped. Retry a link, or upload a file again."
            ),
        )
    )
    db.commit()
    return result.rowcount or 0


def to_schema(source: Source) -> schemas.SourceOut:
    return schemas.SourceOut(
        id=source.id,
        title=source.title,
        kind=source.kind,
        file_type=source.file_type,
        origin=source.origin,
        status=source.status,
        progress=source.progress,
        error=source.error,
        notes=source.notes,
        char_count=source.char_count,
        chunk_count=source.chunk_count,
        page_count=source.page_count,
        semantic_search=source.embedding_model is not None,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


# --------------------------------------------------------------------------- indexing


def _good_title(title: str, fallback: str) -> bool:
    """Use a document's own title unless it is missing or looks auto-generated."""
    title = (title or "").strip()
    if len(title) < 3 or title == fallback:
        return False
    lowered = title.lower()
    junk = ("microsoft word", ".doc", ".pdf", "untitled", "document1")
    return not any(marker in lowered for marker in junk)


def _set(db: Session, source: Source, **values) -> None:
    for key, value in values.items():
        setattr(source, key, value)
    source.updated_at = utcnow()
    db.commit()


def _embed_chunks(db: Session, source: Source, embedder: Embedder, start_progress: int) -> None:
    chunks = list(
        db.scalars(
            select(SourceChunk).where(SourceChunk.source_id == source.id).order_by(SourceChunk.position)
        )
    )
    total = len(chunks)
    for start in range(0, total, EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        vectors = embedder.embed([c.text for c in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = to_blob(vector)
        done = min(total, start + EMBED_BATCH)
        _set(db, source, progress=start_progress + int((100 - start_progress - 1) * done / max(1, total)))
    source.embedding_model = embedder.model


def process_source(
    session_factory: sessionmaker[Session],
    source_id: int,
    settings: Settings,
    embedder_factory: EmbedderFactory,
    data: bytes | None = None,
) -> None:
    """Background job: fetch (for links), extract, chunk and embed a source."""
    with session_factory() as db:
        source = db.get(Source, source_id)
        if source is None:
            return
        try:
            _set(db, source, status="processing", progress=5, error="")
            if source.kind == "url":
                fetched = fetch_document(
                    source.origin,
                    max_bytes=settings.max_library_upload_bytes,
                    timeout=settings.url_fetch_timeout_seconds,
                    allow_private=settings.allow_private_urls,
                )
                data, file_type, fallback = fetched.data, fetched.file_type, fetched.url
            else:
                if data is None:
                    raise ConflictError(
                        "The original file is no longer available. Delete the source and upload it again."
                    )
                file_type, fallback = source.file_type, source.title
            _set(db, source, progress=15)

            document = extract_document(data, file_type, fallback_title=fallback)
            chunks = chunk_segments(document.segments)
            notes = []
            total_chars, kept = 0, []
            for chunk in chunks:
                if total_chars + len(chunk.text) > settings.max_library_chars:
                    notes.append(
                        f"Only the first {settings.max_library_chars:,} characters were indexed "
                        "(the document is very large)."
                    )
                    break
                kept.append(chunk)
                total_chars += len(chunk.text)

            db.execute(delete(SourceChunk).where(SourceChunk.source_id == source.id))
            db.add_all(
                SourceChunk(
                    source_id=source.id,
                    position=i,
                    text=c.text,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    section=c.section[:300],
                )
                for i, c in enumerate(kept)
            )
            if not source.title_locked and _good_title(document.title, fallback):
                source.title = document.title[:300]
            source.file_type = file_type
            source.char_count = total_chars
            source.chunk_count = len(kept)
            source.page_count = document.page_count
            source.embedding_model = None
            _set(db, source, progress=40)

            embedder = embedder_factory()
            if embedder is None:
                notes.append(
                    "Indexed for keyword search only (no OpenAI key). "
                    "Add a key and re-index for meaning-based search."
                )
            else:
                try:
                    _embed_chunks(db, source, embedder, start_progress=40)
                except AppError as exc:
                    db.rollback()
                    notes.append(
                        f"Semantic indexing failed ({exc.message}) — keyword search still works. "
                        "Re-index to retry."
                    )
            _set(db, source, status="ready", progress=100, notes=" ".join(notes))
            logger.info("Indexed source %s: %d chunks", source.id, len(kept))
        except AppError as exc:
            db.rollback()
            _set(db, source, status="failed", error=exc.message, progress=0)
        except Exception:
            logger.exception("Unexpected error while indexing source %s", source_id)
            db.rollback()
            _set(
                db,
                source,
                status="failed",
                error="Unexpected error while processing this source.",
                progress=0,
            )


def prepare_reindex(db: Session, source_id: int) -> Source:
    """Validate that a source can be re-processed and mark it as processing."""
    source = get_source(db, source_id)
    if source.status == "processing":
        raise ConflictError("This source is already being processed.")
    if source.kind == "file" and source.chunk_count == 0:
        raise ConflictError("The original file isn't stored. Delete this source and upload the file again.")
    _set(db, source, status="processing", progress=0, error="")
    return source


def reembed_source(
    session_factory: sessionmaker[Session],
    source_id: int,
    embedder_factory: EmbedderFactory,
    settings: Settings,
) -> None:
    """Background job: re-index. Links are fetched again; files re-use their stored text."""
    with session_factory() as db:
        source = db.get(Source, source_id)
        if source is None:
            return
        if source.kind == "url":
            db.close()
            process_source(session_factory, source_id, settings, embedder_factory)
            return
        notes = []
        embedder = embedder_factory()
        try:
            if embedder is None:
                source.embedding_model = None
                notes.append("Indexed for keyword search only (no OpenAI key).")
            else:
                _embed_chunks(db, source, embedder, start_progress=5)
            _set(db, source, status="ready", progress=100, notes=" ".join(notes))
        except AppError as exc:
            db.rollback()
            _set(db, source, status="ready", progress=100, notes=f"Semantic indexing failed ({exc.message}).")
        except Exception:
            logger.exception("Unexpected error while re-indexing source %s", source_id)
            db.rollback()
            _set(db, source, status="ready", progress=100, notes="Semantic indexing failed unexpectedly.")


# --------------------------------------------------------------------------- retrieval


def citation(source_title: str, chunk: SourceChunk) -> str:
    label = source_title.strip() or "Source"
    if chunk.page_start:
        if chunk.page_end and chunk.page_end != chunk.page_start:
            return f"{label}, pp. {chunk.page_start}–{chunk.page_end}"
        return f"{label}, p. {chunk.page_start}"
    if chunk.section and chunk.section.casefold() != label.casefold():
        return f"{label} — {chunk.section}"[:300]
    return label[:300]


def _load_passages(db: Session, source_ids: list[int]) -> tuple[list[Passage], list[Source]]:
    sources = list(db.scalars(select(Source).where(Source.id.in_(source_ids))))
    found = {s.id for s in sources}
    missing = [i for i in source_ids if i not in found]
    if missing:
        raise NotFoundError(f"Source {missing[0]} was not found.")
    not_ready = [s.title for s in sources if s.status != "ready"]
    if not_ready:
        raise ConflictError(f"“{not_ready[0]}” isn't ready yet. Wait for indexing to finish or retry it.")
    titles = {s.id: s.title for s in sources}
    semantic = all(s.embedding_model for s in sources)
    passages = []
    for chunk in db.scalars(
        select(SourceChunk)
        .where(SourceChunk.source_id.in_(source_ids))
        .order_by(SourceChunk.source_id, SourceChunk.position)
    ):
        passages.append(
            Passage(
                key=(chunk.source_id, chunk.position),
                text=chunk.text,
                citation=citation(titles[chunk.source_id], chunk),
                embedding=from_blob(chunk.embedding) if semantic and chunk.embedding is not None else None,
            )
        )
    if semantic and any(p.embedding is None for p in passages):
        for p in passages:
            p.embedding = None
    return passages, sources


def _query_embedding(passages: list[Passage], sources: list[Source], query: str, factory: EmbedderFactory):
    if not query.strip() or not passages or passages[0].embedding is None:
        return None
    models = {s.embedding_model for s in sources}
    embedder = factory()
    if embedder is None or models != {embedder.model}:
        return None  # model changed or key removed: fall back to keyword ranking
    try:
        return np.asarray(embedder.embed([query])[0], dtype=np.float32)
    except AppError as exc:
        logger.warning("Query embedding failed, using keyword search: %s", exc.message)
        return None


@dataclass
class RetrievedContext:
    text: str
    refs: dict[str, str]  # passage id ("S1") -> human-readable citation
    passage_count: int
    source_titles: list[str]


def retrieve_context(
    db: Session,
    source_ids: list[int],
    *,
    focus: str,
    budget_chars: int,
    embedder_factory: EmbedderFactory,
    rng: random.Random | None = None,
) -> RetrievedContext:
    unique_ids = list(dict.fromkeys(source_ids))
    passages, sources = _load_passages(db, unique_ids)
    query_vector = _query_embedding(passages, sources, focus, embedder_factory)
    selected = select_passages(
        passages, query=focus or None, query_embedding=query_vector, budget_chars=budget_chars, rng=rng
    )
    refs: dict[str, str] = {}
    blocks = []
    for number, passage in enumerate(selected, start=1):
        passage_id = f"S{number}"
        refs[passage_id] = passage.citation
        blocks.append(f"[{passage_id}] ({passage.citation})\n{passage.text}")
    return RetrievedContext(
        text="\n\n".join(blocks),
        refs=refs,
        passage_count=len(selected),
        source_titles=[s.title for s in sources],
    )


def search_source(
    db: Session, source_id: int, query: str, embedder_factory: EmbedderFactory, limit: int = 8
) -> list[schemas.SourceSearchHit]:
    passages, sources = _load_passages(db, [source_id])
    if not passages:
        return []
    vector = _query_embedding(passages, sources, query, embedder_factory)
    hits = rank(passages, query, vector)[:limit]
    return [
        schemas.SourceSearchHit(
            position=hit.passage.key[1],
            citation=hit.passage.citation,
            text=hit.passage.text,
            score=round(hit.score, 6),
            keyword_score=round(hit.keyword_score, 4),
            semantic_score=None if hit.semantic_score is None else round(hit.semantic_score, 4),
        )
        for hit in hits
    ]
