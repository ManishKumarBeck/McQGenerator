"""Aggregated performance statistics across submitted attempts."""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import Settings
from ..models import Attempt, AttemptAnswer
from .attempts import finalize_expired_attempts, to_summary
from .grading import DEFAULT_TOPIC


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 2) if denominator else None


def overview(db: Session, settings: Settings, *, trend_limit: int = 20) -> schemas.AnalyticsOverview:
    finalize_expired_attempts(db, settings)
    submitted = Attempt.status == "submitted"

    totals = db.execute(
        select(
            func.count(Attempt.id),
            func.count(func.distinct(Attempt.test_id)),
            func.avg(Attempt.percentage),
            func.max(Attempt.percentage),
            func.coalesce(func.sum(Attempt.correct_count), 0),
            func.coalesce(func.sum(Attempt.incorrect_count), 0),
            func.coalesce(func.sum(Attempt.unanswered_count), 0),
            func.coalesce(func.sum(Attempt.time_spent_seconds), 0),
            func.coalesce(func.sum(Attempt.question_count), 0),
        ).where(submitted)
    ).one()
    (count, tests_taken, avg_pct, best_pct, correct, incorrect, unanswered, time_total, questions) = totals
    in_progress = db.scalar(select(func.count(Attempt.id)).where(Attempt.status == "in_progress")) or 0

    summary = schemas.AnalyticsSummary(
        total_attempts=count,
        tests_taken=tests_taken,
        in_progress_attempts=in_progress,
        average_percentage=round(avg_pct, 2) if avg_pct is not None else None,
        best_percentage=best_pct,
        accuracy=_pct(correct, correct + incorrect),
        total_correct=correct,
        total_incorrect=incorrect,
        total_unanswered=unanswered,
        total_time_seconds=time_total,
        average_time_per_question_seconds=round(time_total / questions, 1) if questions else None,
    )

    topic_clean = func.coalesce(func.nullif(func.trim(AttemptAnswer.topic), ""), DEFAULT_TOPIC)
    topic_key = func.lower(topic_clean)
    topic_rows = db.execute(
        select(
            func.min(topic_clean).label("topic"),
            func.count(AttemptAnswer.id),
            func.sum(case((AttemptAnswer.is_correct.is_(True), 1), else_=0)),
            func.sum(case((AttemptAnswer.is_correct.is_(False), 1), else_=0)),
            func.sum(case((AttemptAnswer.is_correct.is_(None), 1), else_=0)),
        )
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .where(submitted)
        .group_by(topic_key)
    ).all()
    topics = sorted(
        (
            schemas.TopicStat(
                topic=topic,
                total=total,
                correct=c,
                incorrect=i,
                unanswered=u,
                accuracy=_pct(c, c + i),
            )
            for topic, total, c, i, u in topic_rows
        ),
        key=lambda t: (-t.total, t.topic.casefold()),
    )

    subject_label = func.coalesce(func.nullif(func.trim(Attempt.subject), ""), "Unspecified")
    subjects = [
        schemas.SubjectStat(
            subject=subject,
            attempts=n,
            average_percentage=round(avg, 2) if avg is not None else None,
        )
        for subject, n, avg in db.execute(
            select(subject_label, func.count(Attempt.id), func.avg(Attempt.percentage))
            .where(submitted)
            .group_by(subject_label)
            .order_by(func.count(Attempt.id).desc())
        ).all()
    ]

    recent = list(
        db.scalars(select(Attempt).where(submitted).order_by(Attempt.submitted_at.desc()).limit(trend_limit))
    )
    trend = [
        schemas.TrendPoint(
            attempt_id=a.id,
            test_title=a.test_title,
            submitted_at=a.submitted_at,
            percentage=a.percentage or 0.0,
        )
        for a in reversed(recent)
    ]

    return schemas.AnalyticsOverview(
        summary=summary,
        topics=topics,
        subjects=subjects,
        trend=trend,
        recent_attempts=[to_summary(a) for a in recent[:5]],
    )
