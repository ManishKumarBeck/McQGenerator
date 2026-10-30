# McqGen — AI MCQ Exam Platform

Generate multiple-choice tests with AI from a topic, your notes or a PDF, review and edit every question, then take timed exams with a real exam interface and track your performance over time.

![Dashboard](docs/screenshots/dashboard.png)

McqGen started as a small LangChain + Streamlit script that turned a document into a table of MCQs. It has grown into a full-stack exam platform: a **FastAPI** backend with **SQLite** persistence and a **React + TypeScript** frontend, covering the whole exam lifecycle: create → review → take → grade → analyse.

---

## Features

**Test creation**
- **AI generation** from a topic, pasted text, or an uploaded **PDF / TXT / MD** file (OpenAI via LangChain structured output).
- Configure question count (1–30 per run), **difficulty** (easy / medium / hard / mixed), subject, topic, audience/category and extra instructions.
- Optional **AI quality review** pass that checks accuracy and wording (the original project's "expert reviewer" chain, now structured).
- Every AI question includes an **explanation** and a **sub-topic** for analytics. Output is validated: malformed or duplicate questions are discarded and answer positions are shuffled to avoid bias.
- AI tests are saved as **drafts** you review and edit before publishing.
- **Manual editor**: write questions from scratch with 2–6 options, explanations and topics. Reorder, duplicate and delete questions. Validation runs inline, and you're warned before leaving with unsaved changes.
- Search, filter, duplicate and delete tests.

**Exam experience**
- Dedicated full-screen exam view, one question at a time, with previous/next navigation and keyboard shortcuts (`1–4`, `←/→`, `M`).
- **Question palette** showing answered, unanswered, marked-for-review, answered-and-marked and not-visited questions.
- **Server-authoritative timer**: the deadline is stored on the server and the countdown is synced to the server clock, so refreshing, closing the tab or changing the device clock can't extend the exam.
- **Automatic submission** when time runs out. Abandoned attempts are closed by the server too.
- **Autosave** every answer through a sequential queue. Offline changes are kept in a local backup and retried with backoff; the UI shows *Saving… / All answers saved / Offline*.
- Refresh-safe: answers, review marks and your current question are restored. You're asked to confirm before leaving the exam.
- Confirmation dialog before submitting, with a summary of unanswered and marked questions.

**Results & analytics**
- Automatic grading with configurable marks per question and **negative marking**.
- Score, percentage, correct / incorrect / unanswered counts, accuracy, time taken and penalty total.
- Question-by-question **answer review** with the correct answer, your answer and the explanation, filterable by outcome.
- **Topic-wise breakdown** for every attempt.
- **History** of all attempts, plus an **analytics dashboard**: average and best score, accuracy, time spent, score trend, accuracy by topic, weakest topics and per-subject averages.
- Results are **snapshots**: editing or deleting a test later never changes past results.

**UX**
- Responsive layouts for desktop, tablet and phone, with a bottom navigation bar and a palette sheet on mobile.
- Light and dark themes, plus loading skeletons, empty states, error states with retry, and toast feedback.
- Accessible components (native `<dialog>`, ARIA radio groups, focus styles, reduced-motion support).

## Screenshots

| Generate with AI | Exam |
| --- | --- |
| ![Generate](docs/screenshots/generate.png) | ![Exam](docs/screenshots/exam.png) |
| **Submit confirmation** | **Results & answer review** |
| ![Submit](docs/screenshots/submit-confirm.png) | ![Result](docs/screenshots/result.png) |
| **Test library** | **Analytics (dark mode)** |
| ![Tests](docs/screenshots/tests.png) | ![Analytics](docs/screenshots/analytics-dark.png) |

<p align="center">
  <img src="docs/screenshots/mobile-exam.png" width="260" alt="Mobile exam" />
  &nbsp;&nbsp;
  <img src="docs/screenshots/mobile-palette.png" width="260" alt="Mobile question palette" />
</p>

## Architecture

```mermaid
flowchart LR
    subgraph Browser["React SPA (Vite + TypeScript)"]
        UI[Pages & components] --> RQ[TanStack Query]
        UI --> EX[useExamSession<br/>timer · autosave queue · local backup]
    end
    RQ -- REST /api --> API
    EX -- REST /api --> API
    subgraph Server["FastAPI"]
        API[Routers] --> SVC[Services<br/>catalog · attempts · grading · analytics]
        API --> GEN[Generation service<br/>LangChain structured output]
        SVC --> DB[(SQLite via SQLAlchemy)]
    end
    GEN -- HTTPS --> OAI[OpenAI API]
```

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, React Router, TanStack Query, Recharts, Sonner, Lucide icons |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, pydantic-settings |
| AI | LangChain (`langchain-openai`) with JSON-schema structured output, OpenAI chat models |
| Storage | SQLite by default (any SQLAlchemy database such as PostgreSQL via `DATABASE_URL`) |
| Documents | `pypdf` for PDF text extraction |
| Testing | pytest, Vitest + Testing Library, Playwright (end-to-end, desktop and mobile) |
| Quality | Ruff (lint + format), ESLint, TypeScript strict mode, GitHub Actions CI |

### Key design decisions

- **The server owns time.** Each attempt stores `deadline_at`. The client computes the countdown from the server's timestamp, and the API rejects answers after the deadline (plus a small network grace period). Expired attempts are auto-submitted on the next read, list or server start, even if the browser never comes back.
- **Exactly-once submission.** Submitting uses a conditional `UPDATE … WHERE status = 'in_progress'`, so duplicate clicks, retries and concurrent requests grade an attempt exactly once. Later calls return the same result with `already_submitted: true`. A partial unique index allows only one in-progress attempt per test.
- **Snapshots for history.** When an attempt starts, the questions (in their displayed, possibly shuffled order) and the marking scheme are copied into the attempt. Results stay correct even if the test is edited or deleted.
- **Correct answers never reach the exam screen.** The exam endpoint returns questions without answers or explanations; they're only exposed in results.
- **Structured AI output.** Instead of parsing free-form JSON (the original project broke when the model wrapped JSON in Markdown fences), the model returns a JSON-schema-validated object. Every question is then sanitised and validated. Prompts are built as messages, not templates, so braces in source text can't break them, and the source text is treated as data to resist prompt injection.
- **Free and local by default.** SQLite, no auth, no external services except the OpenAI API.

## Getting started

### Prerequisites

- **Python 3.11+** (tested on 3.11, 3.13 and 3.14)
- **Node.js 22.12+** (for the frontend tooling)
- An **OpenAI API key** for AI generation. Everything else works without one.

### 1. Clone and configure

```bash
git clone https://github.com/<your-username>/McqGen.git
cd McqGen
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. See [Environment variables](#environment-variables).

### 2. Backend

```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API runs at http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs. The SQLite database is created automatically at `backend/data/mcq_exam.db`.

### 3. Frontend (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` requests to the backend on port 8000.

### Single-server mode

To run everything from one process (no Vite), build the frontend once. FastAPI then serves it automatically:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --port 8000
# open http://127.0.0.1:8000
```

### Try it without an OpenAI key

A demo server with a deterministic fake generator is included (it's the one the end-to-end tests use):

```bash
cd backend
python -m tests.e2e_server --port 8000 --db demo.db --serve-frontend
```

`samples/data_science.txt` is a small document you can upload to try file-based generation.

## Environment variables

All settings are read from `.env` in the project root (or `backend/.env`). Real environment variables take precedence.

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | OpenAI key used for generation. `OPENAI_KEY` is accepted for backwards compatibility. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model. Use `gpt-4o` for higher quality at higher cost. |
| `OPENAI_TEMPERATURE` | `0.4` | Sampling temperature. |
| `OPENAI_TIMEOUT_SECONDS` | `90` | Per-request timeout. |
| `OPENAI_MAX_RETRIES` | `2` | Automatic retries for transient OpenAI errors. |
| `DATABASE_URL` | `sqlite:///backend/data/mcq_exam.db` | Any SQLAlchemy URL. |
| `MAX_UPLOAD_MB` | `5` | Maximum upload size. |
| `MAX_SOURCE_CHARS` | `40000` | Longer source material is truncated (with a warning) to control token usage. |
| `MAX_QUESTIONS_PER_GENERATION` | `30` | Upper limit per AI generation request. |
| `SUBMISSION_GRACE_SECONDS` | `10` | Network allowance for answers that arrive right at the deadline. |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Allowed browser origins (JSON list). |
| `SERVE_FRONTEND` | `true` | Serve `frontend/dist` from FastAPI when it exists. |
| `LOG_LEVEL` | `INFO` | Python log level. The API key is never logged. |

Frontend (optional, in `frontend/.env`): `VITE_API_BASE_URL` to call an API on another origin, and `VITE_API_PROXY_TARGET` to change the dev proxy target.

## Testing

```bash
# Backend: unit + API tests (OpenAI is always mocked), lint and format check
cd backend
pip install -r requirements-dev.txt
pytest
ruff check . && ruff format --check .

# Frontend: lint, type-check, unit tests, production build
cd frontend
npm run lint && npm run typecheck && npm test && npm run build

# End-to-end: starts the backend (with a fake AI generator) and Vite automatically
npx playwright install chromium   # first time only
npm run e2e                       # set PYTHON=path/to/python if needed
```

The suites cover:

- **Grading**: negative marking, fractional marks and float rounding, negative totals, empty attempts.
- **Timer**: answers within and after the grace period, automatic submission by the client and by the server, abandoned attempts, late submissions ignoring answers.
- **Concurrency**: duplicate and concurrent submissions are graded exactly once.
- **Persistence**: answers, review marks and position survive refreshes; offline answers are queued and synced; the local backup is restored after a reload.
- **Validation and errors**: input validation, upload limits, scanned or corrupt PDFs, every OpenAI failure mode (bad key, quota, rate limit, timeout, connection, context length, malformed output).
- **UI**: the full create → publish → take → grade flow, search, filter, duplicate and delete, unsaved-change guards, and mobile layouts with no horizontal scrolling.
- **Console**: every end-to-end test fails on browser console errors.

## API overview

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health, database status and whether AI is configured |
| `GET` | `/api/tests?search=&status=` | List tests with attempt stats |
| `POST` | `/api/tests` | Create a test (with questions) |
| `POST` | `/api/tests/generate` | Generate a draft test with AI (multipart: fields + optional file) |
| `GET / PUT / DELETE` | `/api/tests/{id}` | Read, fully update or delete a test |
| `POST` | `/api/tests/{id}/duplicate` | Copy a test as a draft |
| `POST` | `/api/tests/{id}/attempts` | Start an attempt, or resume the running one |
| `GET` | `/api/attempts/{id}` | Exam state (no correct answers) and server time |
| `PUT` | `/api/attempts/{id}/answers/{position}` | Autosave one answer |
| `POST` | `/api/attempts/{id}/submit` | Submit and grade (idempotent) |
| `GET` | `/api/attempts/{id}/result` | Graded result with explanations and topic breakdown |
| `GET / DELETE` | `/api/attempts`, `/api/attempts/{id}` | History and deletion |
| `GET` | `/api/analytics` | Aggregated performance statistics |

Errors use a consistent shape: `{"detail": "Human-readable message", "code": "machine_code"}`.

## Project structure

```
McqGen/
├── backend/
│   ├── app/
│   │   ├── main.py              # app factory, CORS, SPA serving
│   │   ├── config.py            # settings from .env
│   │   ├── database.py          # engine, sessions, UTC datetime type
│   │   ├── models.py            # Test, Question, Attempt, AttemptAnswer
│   │   ├── schemas.py           # request/response models
│   │   ├── routers/             # tests, attempts, health + analytics
│   │   └── services/            # generation, documents, catalog, attempts, grading, analytics
│   ├── tests/                   # pytest suites + e2e demo server
│   └── requirements*.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Tests, Create, Edit, Detail, Exam, Result, History, Analytics
│   │   ├── components/          # ui primitives, exam, tests, charts, layout
│   │   ├── hooks/               # useExamSession, useLeaveGuard, useTheme
│   │   └── lib/                 # API client, types, exam & draft logic, formatting
│   └── e2e/                     # Playwright tests
├── experiment/                  # original prototype notebook
├── samples/                     # sample source document
└── docs/screenshots/
```

## Roadmap

- User accounts and authentication (the data model is ready for an owner column)
- Alembic migrations and a PostgreSQL deployment profile
- Question bank import/export (CSV/JSON) and "add more AI questions" to an existing test
- Practice mode with instant feedback, and "retry only wrong answers"
- Shareable test links and leaderboards
- Docker Compose setup

## License

[MIT](LICENSE)
