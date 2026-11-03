"""Run the API with a deterministic fake question generator (no OpenAI calls).

Used by the Playwright end-to-end tests and handy for UI development without an API key:

    python -m tests.e2e_server --port 8001 --db e2e.db
"""

import argparse
import time
import zlib
from pathlib import Path

import numpy as np
import uvicorn
from fastapi.responses import HTMLResponse

from app.config import Settings
from app.main import FRONTEND_DIST, create_app
from app.services.generation import GeneratedQuestion, GenerationParams, GenerationResult
from app.services.sources.embeddings import normalise
from app.services.sources.retrieval import tokenize

DEMO_ARTICLE = """<!doctype html><html><head><title>Photosynthesis basics</title></head><body>
<nav>Home | About</nav><article><h1>Photosynthesis basics</h1>
<p>Photosynthesis is the process plants use to convert light energy into chemical energy. Chlorophyll in the
chloroplasts absorbs sunlight. Carbon dioxide and water are turned into glucose and oxygen.</p>
<h2>Light reactions</h2><p>In the light-dependent reactions water is split, oxygen is released and ATP and NADPH
are produced in the thylakoid membranes.</p>
<h2>Calvin cycle</h2><p>The Calvin cycle uses ATP and NADPH to fix carbon dioxide into sugars in the stroma.</p>
</article></body></html>"""


class DemoGenerator:
    """Produces simple arithmetic questions so answers are predictable in tests."""

    def generate(self, params: GenerationParams) -> GenerationResult:
        time.sleep(0.4)  # make the loading state visible
        if "fail" in (params.topic or "").lower():
            from app.errors import GenerationError

            raise GenerationError("OpenAI rate limit reached. Wait a moment and try again.", status_code=429)
        refs = list(params.passage_refs.values())
        questions = []
        for i in range(params.count):
            a, b = i + 2, i + 3
            correct = a + b
            options = [str(correct - 1), str(correct), str(correct + 1), str(correct + 2)]
            questions.append(
                GeneratedQuestion(
                    text=f"What is {a} + {b}?",
                    options=options,
                    correct_option=1,
                    explanation=f"{a} + {b} = {correct}.",
                    topic="Addition" if i % 2 == 0 else "Mental math",
                    source_ref=refs[i % len(refs)] if refs else "",
                )
            )
        return GenerationResult(questions=questions, warnings=[], notes="")


class DemoEmbedder:
    """Offline hashing embedder (stable across processes) so the library works without a key."""

    model = "demo-hashing"

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                matrix[row, zlib.crc32(token.encode()) % 256] += 1.0
        return normalise(matrix)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--db", default="e2e.db")
    parser.add_argument("--grace", type=int, default=2)
    parser.add_argument("--serve-frontend", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="delete the database file first")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if args.fresh:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_path.as_posix()}",
        openai_api_key="sk-e2e-fake",
        submission_grace_seconds=args.grace,
        allow_private_urls=True,  # lets e2e tests add the local demo article as a link
        cors_origins=["*"],
        serve_frontend=args.serve_frontend,
        log_level="WARNING",
    )
    app = create_app(
        settings, generator=DemoGenerator(), embedder_factory=DemoEmbedder, frontend_dist=FRONTEND_DIST
    )

    @app.get("/demo/article", include_in_schema=False)
    def demo_article() -> HTMLResponse:
        return HTMLResponse(DEMO_ARTICLE)

    # Register before the SPA catch-all route (when --serve-frontend is used).
    app.router.routes.insert(0, app.router.routes.pop())

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
