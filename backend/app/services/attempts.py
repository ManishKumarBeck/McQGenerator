"""Exam attempt lifecycle: start/resume, autosave answers, submit and grade.

The server is the source of truth for time. Every attempt has a fixed `deadline_at`;
answers arriving after the deadline (plus a small network grace period) are rejected,
and expired attempts are finalised automatically even if the browser never submits.
"""

import logging
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..config import Settings
from ..database import utcnow
from ..errors import ConflictError, InvalidInputError, NotFoundError
from ..models import Attempt, AttemptAnswer
from .catalog import get_test
from .grading import AnswerKey, grade_attempt, topic_breakdown

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- helpers


def _grace(settings: Settings) -> timedelta:
    return timedelta(seconds=settings.submission_grace_seconds)


def is_expired(attempt: Attempt, now: datetime, settings: Settings) -> bool:
    return now > attempt.deadline_at + _grace(settings)


def get_attempt(db: Session, attempt_id: str) -> Attempt:
    attempt = db.scalar(
        select(Attempt).where(Attempt.id == attempt_id).options(selectinload(Attempt.answers))
    )
    if attempt is None:
        raise NotFoundError("Attempt not found.")
    return attempt


def _find_in_progress(db: Session, test_id: int) -> Attempt | None:
    return db.scalar(
        select(Attempt)
        .where(Attempt.test_id == test_id, Attempt.status == "in_progress")
        .options(selectinload(Attempt.answers))
    )


# --------------------------------------------------------------------------- lifecycle


def finalize_attempt(db: Session, attempt: Attempt, reason: str, now: datetime) -> bool:
    """Grade and close an attempt exactly once.

    Returns True if this call finalised the attempt, False if it had already been
    submitted (e.g. a duplicate or concurrent submission).
    """
    submitted_at = min(now, attempt.deadline_at)
    claimed = db.execute(
        update(Attempt)
        .where(Attempt.id == attempt.id, Attempt.status == "in_progress")
        .values(status="submitted", submit_reason=reason, submitted_at=submitted_at)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()
        db.refresh(attempt)
        return False

    attempt.status = "submitted"
    attempt.submit_reason = reason
    attempt.submitted_at = submitted_at

    summary = grade_attempt(
        (AnswerKey(a.selected_option, a.correct_option, a.topic) for a in attempt.answers),
        attempt.marks_per_question,
        attempt.negative_marks,
    )
    for answer, grade in zip(attempt.answers, summary.grades, strict=True):
        answer.is_correct = grade.is_correct
        answer.marks_awarded = grade.marks_awarded

    attempt.score = summary.score
    attempt.max_score = summary.max_score
    attempt.percentage = summary.percentage
    attempt.correct_count = summary.correct
    attempt.incorrect_count = summary.incorrect
    attempt.unanswered_count = summary.unanswered
    elapsed = int((submitted_at - attempt.started_at).total_seconds())
    attempt.time_spent_seconds = max(0, min(elapsed, attempt.duration_seconds))
    db.commit()
    logger.info("Attempt %s submitted (%s): %s/%s", attempt.id, reason, summary.score, summary.max_score)
    return True


def finalize_expired_attempts(db: Session, settings: Settings, now: datetime | None = None) -> int:
    """Auto-submit every attempt whose deadline (plus grace) has passed."""
    now = now or utcnow()
    cutoff = now - _grace(settings)
    expired = list(
        db.scalars(
            select(Attempt)
            .where(Attempt.status == "in_progress", Attempt.deadline_at < cutoff)
            .options(selectinload(Attempt.answers))
        )
    )
    return sum(finalize_attempt(db, attempt, "timeout", now) for attempt in expired)


def _close_if_expired(db: Session, attempt: Attempt, settings: Settings, now: datetime) -> None:
    if attempt.status == "in_progress" and is_expired(attempt, now, settings):
        finalize_attempt(db, attempt, "timeout", now)


def start_attempt(
    db: Session,
    test_id: int,
    settings: Settings,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> tuple[Attempt, bool]:
    """Start a new attempt, or resume the running one. Returns (attempt, resumed)."""
    now = now or utcnow()
    rng = rng or random.Random()
    test = get_test(db, test_id)
    if test.status != "published":
        raise ConflictError("Publish this test before starting it.", code="test_not_published")
    if not test.questions:
        raise ConflictError("This test has no questions.", code="test_empty")

    existing = _find_in_progress(db, test_id)
    if existing is not None:
        _close_if_expired(db, existing, settings, now)
        if existing.status == "in_progress":
            return existing, True

    questions = list(test.questions)
    if test.shuffle_questions:
        rng.shuffle(questions)

    duration_seconds = test.duration_minutes * 60
    attempt = Attempt(
        id=str(uuid.uuid4()),
        test_id=test.id,
        test_title=test.title,
        subject=test.subject,
        topic=test.topic,
        category=test.category,
        difficulty=test.difficulty,
        duration_seconds=duration_seconds,
        marks_per_question=test.marks_per_question,
        negative_marks=test.negative_marks,
        status="in_progress",
        started_at=now,
        deadline_at=now + timedelta(seconds=duration_seconds),
        max_score=round(test.marks_per_question * len(questions), 4),
        question_count=len(questions),
    )
    for position, question in enumerate(questions):
        order = list(range(len(question.options)))
        if test.shuffle_options:
            rng.shuffle(order)
        attempt.answers.append(
            AttemptAnswer(
                position=position,
                question_id=question.id,
                question_text=question.text,
                options=[question.options[i] for i in order],
                correct_option=order.index(question.correct_option),
                explanation=question.explanation,
                topic=question.topic or test.topic,
                source_ref=question.source_ref,
            )
        )
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError:
        # Another request started an attempt for this test at the same moment.
        db.rollback()
        existing = _find_in_progress(db, test_id)
        if existing is None:
            raise
        return existing, True
    return get_attempt(db, attempt.id), False


def _apply_answer(answer: AttemptAnswer, data: schemas.AnswerUpdate, duration: int) -> None:
    if data.selected_option is not None and data.selected_option >= len(answer.options):
        raise InvalidInputError(f"Question {answer.position + 1} has no option {data.selected_option + 1}.")
    answer.selected_option = data.selected_option
    answer.marked_for_review = data.marked_for_review
    # Clients send a running total; never let a stale request reduce it.
    answer.time_spent_seconds = min(max(answer.time_spent_seconds, data.time_spent_seconds), duration)


def _ensure_open(db: Session, attempt: Attempt, settings: Settings, now: datetime) -> None:
    if attempt.status != "in_progress":
        raise ConflictError("This attempt has already been submitted.", code="attempt_closed")
    if is_expired(attempt, now, settings):
        finalize_attempt(db, attempt, "timeout", now)
        raise ConflictError("Time is up. The attempt was submitted automatically.", code="attempt_closed")


def save_answer(
    db: Session,
    attempt_id: str,
    position: int,
    data: schemas.AnswerUpdate,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> AttemptAnswer:
    now = now or utcnow()
    attempt = get_attempt(db, attempt_id)
    _ensure_open(db, attempt, settings, now)
    answer = next((a for a in attempt.answers if a.position == position), None)
    if answer is None:
        raise NotFoundError("Question not found in this attempt.")
    _apply_answer(answer, data, attempt.duration_seconds)
    db.commit()
    return answer


def submit_attempt(
    db: Session,
    attempt_id: str,
    request: schemas.SubmitRequest,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> tuple[Attempt, bool]:
    """Submit an attempt. Idempotent: returns (attempt, already_submitted)."""
    now = now or utcnow()
    attempt = get_attempt(db, attempt_id)
    if attempt.status == "submitted":
        return attempt, True

    if not is_expired(attempt, now, settings):
        by_position = {a.position: a for a in attempt.answers}
        for item in request.answers:
            if item.position not in by_position:
                raise InvalidInputError(f"Question {item.position + 1} does not exist in this attempt.")
            _apply_answer(by_position[item.position], item, attempt.duration_seconds)
        db.flush()
    else:
        logger.info("Ignoring %d late answers for expired attempt %s", len(request.answers), attempt.id)

    reason = "timeout" if now > attempt.deadline_at else request.reason
    finalized = finalize_attempt(db, attempt, reason, now)
    return get_attempt(db, attempt.id), not finalized


def delete_attempt(db: Session, attempt_id: str) -> None:
    attempt = get_attempt(db, attempt_id)
    db.delete(attempt)
    db.commit()


def list_attempts(
    db: Session,
    settings: Settings,
    *,
    test_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Attempt]:
    finalize_expired_attempts(db, settings)
    query = select(Attempt).order_by(Attempt.started_at.desc())
    if test_id is not None:
        query = query.where(Attempt.test_id == test_id)
    if status:
        query = query.where(Attempt.status == status)
    return list(db.scalars(query.limit(limit).offset(offset)))


# --------------------------------------------------------------------------- views


def to_summary(attempt: Attempt) -> schemas.AttemptSummary:
    return schemas.AttemptSummary.model_validate(attempt)


def to_session(
    db: Session, attempt: Attempt, settings: Settings, *, now: datetime | None = None
) -> schemas.AttemptSession:
    now = now or utcnow()
    _close_if_expired(db, attempt, settings, now)
    base = schemas.AttemptSummary.model_validate(attempt).model_dump()
    return schemas.AttemptSession(
        **base,
        server_time=now,
        questions=[
            schemas.AttemptQuestion(
                position=a.position,
                text=a.question_text,
                options=a.options,
                topic=a.topic,
                selected_option=a.selected_option,
                marked_for_review=a.marked_for_review,
                time_spent_seconds=a.time_spent_seconds,
            )
            for a in attempt.answers
        ],
    )


def to_result(
    db: Session,
    attempt: Attempt,
    settings: Settings,
    *,
    already_submitted: bool = False,
    now: datetime | None = None,
) -> schemas.AttemptResult:
    now = now or utcnow()
    _close_if_expired(db, attempt, settings, now)
    if attempt.status != "submitted":
        raise ConflictError(
            "Results are available once the attempt has been submitted.", code="attempt_in_progress"
        )
    breakdown = topic_breakdown((a.topic, a.is_correct) for a in attempt.answers)
    attempted = attempt.correct_count + attempt.incorrect_count
    base = schemas.AttemptSummary.model_validate(attempt).model_dump()
    return schemas.AttemptResult(
        **base,
        accuracy=round(attempt.correct_count / attempted * 100, 2) if attempted else None,
        negative_marks_total=round(attempt.incorrect_count * attempt.negative_marks, 4),
        already_submitted=already_submitted,
        topic_breakdown=[
            schemas.TopicStat(
                topic=topic,
                total=t.total,
                correct=t.correct,
                incorrect=t.incorrect,
                unanswered=t.unanswered,
                accuracy=t.accuracy,
            )
            for topic, t in breakdown.items()
        ],
        questions=[
            schemas.ResultQuestion(
                position=a.position,
                text=a.question_text,
                options=a.options,
                correct_option=a.correct_option,
                selected_option=a.selected_option,
                is_correct=a.is_correct,
                marks_awarded=a.marks_awarded or 0.0,
                marked_for_review=a.marked_for_review,
                explanation=a.explanation,
                topic=a.topic,
                source_ref=a.source_ref,
                time_spent_seconds=a.time_spent_seconds,
            )
            for a in attempt.answers
        ],
    )
