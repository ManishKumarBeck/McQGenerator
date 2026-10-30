"""Run the API with a deterministic fake question generator (no OpenAI calls).

Used by the Playwright end-to-end tests and handy for UI development without an API key:

    python -m tests.e2e_server --port 8001 --db e2e.db
"""

import argparse
import time
from pathlib import Path

import uvicorn

from app.config import Settings
from app.main import FRONTEND_DIST, create_app
from app.services.generation import GeneratedQuestion, GenerationParams, GenerationResult


class DemoGenerator:
    """Produces simple arithmetic questions so answers are predictable in tests."""

    def generate(self, params: GenerationParams) -> GenerationResult:
        time.sleep(0.4)  # make the loading state visible
        if "fail" in (params.topic or "").lower():
            from app.errors import GenerationError

            raise GenerationError("OpenAI rate limit reached. Wait a moment and try again.", status_code=429)
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
                )
            )
        return GenerationResult(questions=questions, warnings=[], notes="")


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
        cors_origins=["*"],
        serve_frontend=args.serve_frontend,
        log_level="WARNING",
    )
    app = create_app(settings, generator=DemoGenerator(), frontend_dist=FRONTEND_DIST)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
