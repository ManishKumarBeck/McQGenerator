"""FastAPI application factory.

Run in development with:  uvicorn app.main:app --reload   (from the backend/ folder)
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT_DIR, Settings, get_settings
from .database import Base, create_db_engine, create_session_factory
from .errors import register_error_handlers
from .migrations import upgrade
from .routers import attempts, meta, sources, tests
from .services.attempts import finalize_expired_attempts
from .services.generation import OpenAIQuestionGenerator, QuestionGenerator
from .services.sources.embeddings import default_embedder_factory
from .services.sources.library import EmbedderFactory, mark_interrupted

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def create_app(
    settings: Settings | None = None,
    *,
    generator: QuestionGenerator | None = None,
    embedder_factory: EmbedderFactory | None = None,
    frontend_dist: Path | None = FRONTEND_DIST,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(engine)
        upgrade(engine)
        with session_factory() as db:
            mark_interrupted(db)
            closed = finalize_expired_attempts(db, settings)
            if closed:
                logging.getLogger(__name__).info("Auto-submitted %d expired attempt(s)", closed)
        yield
        engine.dispose()

    app = FastAPI(
        title="MCQ Exam Platform API",
        version="1.0.0",
        description="Generate MCQ tests with AI, take timed exams and track performance.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.generator = generator or OpenAIQuestionGenerator(settings)
    app.state.embedder_factory = embedder_factory or default_embedder_factory(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(meta.router)
    app.include_router(tests.router)
    app.include_router(attempts.router)
    app.include_router(sources.router)

    if settings.serve_frontend and frontend_dist and (frontend_dist / "index.html").is_file():
        _mount_frontend(app, frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app, falling back to index.html for client-side routes."""
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    index = dist / "index.html"
    dist_root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist_root):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
