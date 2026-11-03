"""Source library endpoints: add books, documents and links for retrieval-augmented generation."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, Response, UploadFile, status

from .. import schemas
from ..dependencies import AppSettings, DbSession, EmbedderFactoryDep
from ..services.sources import library

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[schemas.SourceOut])
def list_sources(db: DbSession):
    return [library.to_schema(s) for s in library.list_sources(db)]


@router.post("/upload", response_model=schemas.SourceOut, status_code=status.HTTP_202_ACCEPTED)
def upload_source(
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    embedder_factory: EmbedderFactoryDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=300)] = "",
):
    """Add a PDF, Word, text, Markdown or EPUB file. Indexing continues in the background."""
    data = file.file.read(settings.max_library_upload_bytes + 1)
    source = library.create_file_source(db, file.filename or "", data, settings, title)
    background.add_task(
        library.process_source, request.app.state.session_factory, source.id, settings, embedder_factory, data
    )
    return library.to_schema(source)


@router.post("/url", response_model=schemas.SourceOut, status_code=status.HTTP_202_ACCEPTED)
def add_url_source(
    payload: schemas.SourceUrlCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    embedder_factory: EmbedderFactoryDep,
):
    """Add a web page or online document by link. It is downloaded and indexed in the background."""
    source = library.create_url_source(db, payload.url, payload.title)
    background.add_task(
        library.process_source, request.app.state.session_factory, source.id, settings, embedder_factory
    )
    return library.to_schema(source)


@router.get("/{source_id}", response_model=schemas.SourceOut)
def get_source(source_id: int, db: DbSession):
    return library.to_schema(library.get_source(db, source_id))


@router.patch("/{source_id}", response_model=schemas.SourceOut)
def rename_source(source_id: int, payload: schemas.SourceRename, db: DbSession):
    return library.to_schema(library.rename_source(db, source_id, payload.title))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: DbSession):
    library.delete_source(db, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/reindex", response_model=schemas.SourceOut, status_code=status.HTTP_202_ACCEPTED)
def reindex_source(
    source_id: int,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    embedder_factory: EmbedderFactoryDep,
):
    """Retry or refresh indexing: links are downloaded again, files are re-embedded."""
    source = library.prepare_reindex(db, source_id)
    background.add_task(
        library.reembed_source, request.app.state.session_factory, source.id, embedder_factory, settings
    )
    return library.to_schema(source)


@router.get("/{source_id}/search", response_model=list[schemas.SourceSearchHit])
def search_source(
    source_id: int,
    db: DbSession,
    embedder_factory: EmbedderFactoryDep,
    q: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
):
    """Preview which passages would be used for a topic (the retrieval step of RAG)."""
    return library.search_source(db, source_id, q, embedder_factory, limit)
