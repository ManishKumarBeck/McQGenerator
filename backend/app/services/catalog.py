"""Creating, editing and listing tests."""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..errors import NotFoundError
from ..models import Attempt, Question, Test
from .generation import GeneratedQuestion


def get_test(db: Session, test_id: int) -> Test:
    test = db.scalar(select(Test).where(Test.id == test_id).options(selectinload(Test.questions)))
    if test is None:
        raise NotFoundError("Test not found.")
    return test


def _apply_settings(test: Test, data: schemas.TestSettings) -> None:
    for field_name in schemas.TestSettings.model_fields:
        setattr(test, field_name, getattr(data, field_name))


def _replace_questions(test: Test, questions: list[schemas.QuestionIn]) -> None:
    existing = {q.id: q for q in test.questions}
    updated: list[Question] = []
    for position, item in enumerate(questions):
        question = existing.pop(item.id, None) if item.id is not None else None
        if question is None:
            question = Question()
        question.position = position
        question.text = item.text
        question.options = list(item.options)
        question.correct_option = item.correct_option
        question.explanation = item.explanation
        question.topic = item.topic
        question.source_ref = item.source_ref
        updated.append(question)
    # Questions left in `existing` were removed by the user; delete-orphan cleans them up.
    test.questions = updated


def create_test(db: Session, data: schemas.TestWrite, *, source: str = "manual") -> Test:
    test = Test(source=source, status=data.status)
    _apply_settings(test, data)
    _replace_questions(test, data.questions)
    db.add(test)
    db.commit()
    return get_test(db, test.id)


def create_generated_test(
    db: Session,
    settings: schemas.TestSettings,
    questions: list[GeneratedQuestion],
    *,
    notes: str = "",
) -> Test:
    test = Test(source="ai", status="draft", generation_notes=notes)
    _apply_settings(test, settings)
    test.questions = [
        Question(
            position=i,
            text=q.text,
            options=q.options,
            correct_option=q.correct_option,
            explanation=q.explanation,
            topic=q.topic,
            source_ref=q.source_ref,
        )
        for i, q in enumerate(questions)
    ]
    db.add(test)
    db.commit()
    return get_test(db, test.id)


def update_test(db: Session, test_id: int, data: schemas.TestWrite) -> Test:
    test = get_test(db, test_id)
    _apply_settings(test, data)
    test.status = data.status
    _replace_questions(test, data.questions)
    db.commit()
    return get_test(db, test.id)


def delete_test(db: Session, test_id: int) -> None:
    test = get_test(db, test_id)
    db.delete(test)
    db.commit()


def duplicate_test(db: Session, test_id: int) -> Test:
    original = get_test(db, test_id)
    copy = Test(
        source=original.source,
        status="draft",
        generation_notes=original.generation_notes,
    )
    for field_name in schemas.TestSettings.model_fields:
        setattr(copy, field_name, getattr(original, field_name))
    copy.title = f"{original.title} (copy)"[:200]
    copy.questions = [
        Question(
            position=q.position,
            text=q.text,
            options=list(q.options),
            correct_option=q.correct_option,
            explanation=q.explanation,
            topic=q.topic,
            source_ref=q.source_ref,
        )
        for q in original.questions
    ]
    db.add(copy)
    db.commit()
    return get_test(db, copy.id)


# --------------------------------------------------------------------------- read models


def _stats_query() -> Select:
    submitted = Attempt.status == "submitted"
    return select(
        Attempt.test_id,
        func.count(Attempt.id).filter(submitted).label("attempt_count"),
        func.max(Attempt.percentage).filter(submitted).label("best_percentage"),
        func.max(Attempt.submitted_at).label("last_attempt_at"),
        func.max(Attempt.id).filter(Attempt.status == "in_progress").label("in_progress_id"),
    ).group_by(Attempt.test_id)


def _attach_stats(db: Session, tests: list[Test]) -> list[dict]:
    ids = [t.id for t in tests]
    stats = {}
    counts = {}
    if ids:
        stats = {row.test_id: row for row in db.execute(_stats_query().where(Attempt.test_id.in_(ids)))}
        counts = dict(
            db.execute(
                select(Question.test_id, func.count(Question.id))
                .where(Question.test_id.in_(ids))
                .group_by(Question.test_id)
            ).all()
        )
    result = []
    for test in tests:
        row = stats.get(test.id)
        result.append(
            {
                "test": test,
                "question_count": counts.get(test.id, 0),
                "attempt_count": row.attempt_count if row else 0,
                "best_percentage": row.best_percentage if row else None,
                "last_attempt_at": row.last_attempt_at if row else None,
                "in_progress_attempt_id": row.in_progress_id if row else None,
            }
        )
    return result


def _to_summary(entry: dict, model: type[schemas.TestSummary]) -> schemas.TestSummary:
    test: Test = entry["test"]
    data = {name: getattr(test, name) for name in model.model_fields if hasattr(test, name)}
    data.update({k: v for k, v in entry.items() if k != "test"})
    if model is schemas.TestDetail:
        data["questions"] = [schemas.QuestionOut.model_validate(q) for q in test.questions]
    return model.model_validate(data)


def list_tests(
    db: Session,
    *,
    search: str = "",
    status: str | None = None,
    subject: str | None = None,
) -> list[schemas.TestSummary]:
    query = select(Test).order_by(Test.updated_at.desc(), Test.id.desc())
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Test.title.ilike(pattern),
                Test.subject.ilike(pattern),
                Test.topic.ilike(pattern),
                Test.category.ilike(pattern),
            )
        )
    if status:
        query = query.where(Test.status == status)
    if subject:
        query = query.where(Test.subject == subject)
    tests = list(db.scalars(query))
    return [_to_summary(e, schemas.TestSummary) for e in _attach_stats(db, tests)]


def build_test_detail(db: Session, test: Test) -> schemas.TestDetail:
    entry = _attach_stats(db, [test])[0]
    detail = _to_summary(entry, schemas.TestDetail)
    assert isinstance(detail, schemas.TestDetail)
    return detail
