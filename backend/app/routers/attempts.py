"""Exam attempt endpoints: take, autosave, submit, results and history."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from .. import schemas
from ..database import utcnow
from ..dependencies import AppSettings, DbSession
from ..services import attempts as service

router = APIRouter(prefix="/api/attempts", tags=["attempts"])

AttemptId = Annotated[str, Path(min_length=1, max_length=36)]


@router.get("", response_model=list[schemas.AttemptSummary])
def list_attempts(
    db: DbSession,
    settings: AppSettings,
    test_id: int | None = None,
    status_filter: Annotated[schemas.AttemptStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    attempts = service.list_attempts(
        db, settings, test_id=test_id, status=status_filter, limit=limit, offset=offset
    )
    return [service.to_summary(a) for a in attempts]


@router.get("/{attempt_id}", response_model=schemas.AttemptSession)
def get_attempt(attempt_id: AttemptId, db: DbSession, settings: AppSettings):
    """Current exam state for the test-taking screen (no correct answers included)."""
    return service.to_session(db, service.get_attempt(db, attempt_id), settings)


@router.put("/{attempt_id}/answers/{position}", response_model=schemas.AnswerSaved)
def save_answer(
    attempt_id: AttemptId,
    position: Annotated[int, Path(ge=0)],
    payload: schemas.AnswerUpdate,
    db: DbSession,
    settings: AppSettings,
):
    answer = service.save_answer(db, attempt_id, position, payload, settings)
    return schemas.AnswerSaved(
        position=answer.position,
        selected_option=answer.selected_option,
        marked_for_review=answer.marked_for_review,
        time_spent_seconds=answer.time_spent_seconds,
        server_time=utcnow(),
    )


@router.post("/{attempt_id}/submit", response_model=schemas.AttemptResult)
def submit_attempt(
    attempt_id: AttemptId,
    payload: schemas.SubmitRequest,
    db: DbSession,
    settings: AppSettings,
):
    """Submit and grade. Safe to call more than once; later calls return the same result."""
    attempt, already = service.submit_attempt(db, attempt_id, payload, settings)
    return service.to_result(db, attempt, settings, already_submitted=already)


@router.get("/{attempt_id}/result", response_model=schemas.AttemptResult)
def get_result(attempt_id: AttemptId, db: DbSession, settings: AppSettings):
    return service.to_result(db, service.get_attempt(db, attempt_id), settings)


@router.delete("/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attempt(attempt_id: AttemptId, db: DbSession):
    service.delete_attempt(db, attempt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
