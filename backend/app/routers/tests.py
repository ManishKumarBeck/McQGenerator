"""Test (exam) management endpoints, including AI generation."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from .. import schemas
from ..dependencies import AppSettings, DbSession, Generator
from ..errors import InvalidInputError
from ..services import attempts as attempt_service
from ..services import catalog
from ..services.documents import extract_text_from_upload, prepare_source_text
from ..services.generation import GenerationParams

router = APIRouter(prefix="/api/tests", tags=["tests"])


@router.get("", response_model=list[schemas.TestSummary])
def list_tests(
    db: DbSession,
    settings: AppSettings,
    search: Annotated[str, Query(max_length=100)] = "",
    status_filter: Annotated[schemas.TestStatus | None, Query(alias="status")] = None,
    subject: Annotated[str | None, Query(max_length=100)] = None,
):
    attempt_service.finalize_expired_attempts(db, settings)
    return catalog.list_tests(db, search=search, status=status_filter, subject=subject)


@router.post("", response_model=schemas.TestDetail, status_code=status.HTTP_201_CREATED)
def create_test(payload: schemas.TestWrite, db: DbSession):
    test = catalog.create_test(db, payload)
    return catalog.build_test_detail(db, test)


@router.post("/generate", response_model=schemas.GenerateTestResponse, status_code=status.HTTP_201_CREATED)
def generate_test(
    form: Annotated[schemas.GenerateTestForm, Form()],
    db: DbSession,
    settings: AppSettings,
    generator: Generator,
    file: Annotated[UploadFile | None, File()] = None,
):
    """Generate MCQs with AI and save them as a draft test ready for review."""
    if form.question_count > settings.max_questions_per_generation:
        raise InvalidInputError(
            f"You can generate at most {settings.max_questions_per_generation} questions at a time."
        )

    source = form.source_text
    if file is not None and file.filename:
        data = file.file.read(settings.max_upload_bytes + 1)
        file_text = extract_text_from_upload(file.filename, data, max_bytes=settings.max_upload_bytes)
        source = f"{source}\n\n{file_text}".strip() if source else file_text

    if not source and not (form.subject or form.topic):
        raise InvalidInputError("Provide a subject or topic, or some source material to generate from.")

    warnings: list[str] = []
    if source:
        prepared = prepare_source_text(source, max_chars=settings.max_source_chars)
        source, warnings = prepared.text, prepared.warnings

    params = GenerationParams(
        subject=form.subject,
        topic=form.topic,
        category=form.category,
        difficulty=form.difficulty,
        count=form.question_count,
        source_text=source or None,
        instructions=form.instructions,
        quality_review=form.quality_review,
    )
    # Sync endpoint: FastAPI runs it in a worker thread, so the blocking LLM call is fine.
    result = generator.generate(params)

    title = form.title or " - ".join(p for p in (form.subject, form.topic) if p) or "AI generated test"
    test_settings = schemas.TestSettings(
        title=title[:200],
        subject=form.subject,
        topic=form.topic,
        category=form.category,
        difficulty=form.difficulty,
        duration_minutes=form.duration_minutes or max(5, len(result.questions)),
        marks_per_question=form.marks_per_question,
        negative_marks=form.negative_marks,
    )
    test = catalog.create_generated_test(db, test_settings, result.questions, notes=result.notes)
    return schemas.GenerateTestResponse(
        test=catalog.build_test_detail(db, test), warnings=warnings + result.warnings
    )


@router.get("/{test_id}", response_model=schemas.TestDetail)
def get_test(test_id: int, db: DbSession):
    return catalog.build_test_detail(db, catalog.get_test(db, test_id))


@router.put("/{test_id}", response_model=schemas.TestDetail)
def update_test(test_id: int, payload: schemas.TestWrite, db: DbSession):
    test = catalog.update_test(db, test_id, payload)
    return catalog.build_test_detail(db, test)


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(test_id: int, db: DbSession):
    catalog.delete_test(db, test_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{test_id}/duplicate", response_model=schemas.TestDetail, status_code=status.HTTP_201_CREATED)
def duplicate_test(test_id: int, db: DbSession):
    return catalog.build_test_detail(db, catalog.duplicate_test(db, test_id))


@router.post("/{test_id}/attempts", response_model=schemas.AttemptSession)
def start_attempt(test_id: int, db: DbSession, settings: AppSettings, response: Response):
    """Start a new attempt, or resume the one already in progress for this test."""
    attempt, resumed = attempt_service.start_attempt(db, test_id, settings)
    response.status_code = status.HTTP_200_OK if resumed else status.HTTP_201_CREATED
    return attempt_service.to_session(db, attempt, settings)
