"""Pure scoring logic. Kept free of database code so it is easy to test exhaustively."""

from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_TOPIC = "General"


@dataclass(frozen=True)
class AnswerKey:
    selected_option: int | None
    correct_option: int
    topic: str = ""


@dataclass(frozen=True)
class QuestionGrade:
    is_correct: bool | None  # None = unanswered
    marks_awarded: float


@dataclass(frozen=True)
class GradeSummary:
    grades: list[QuestionGrade]
    score: float
    max_score: float
    percentage: float
    correct: int
    incorrect: int
    unanswered: int
    negative_marks_total: float

    @property
    def accuracy(self) -> float | None:
        attempted = self.correct + self.incorrect
        return round(self.correct / attempted * 100, 2) if attempted else None


def _round(value: float) -> float:
    # Rounding avoids float artefacts such as 0.1 + 0.2 = 0.30000000000000004.
    return round(value + 0.0, 4)


def grade_answer(answer: AnswerKey, marks_per_question: float, negative_marks: float) -> QuestionGrade:
    if answer.selected_option is None:
        return QuestionGrade(is_correct=None, marks_awarded=0.0)
    if answer.selected_option == answer.correct_option:
        return QuestionGrade(is_correct=True, marks_awarded=_round(marks_per_question))
    return QuestionGrade(is_correct=False, marks_awarded=_round(-negative_marks))


def grade_attempt(
    answers: Iterable[AnswerKey], marks_per_question: float, negative_marks: float
) -> GradeSummary:
    if marks_per_question <= 0:
        raise ValueError("marks_per_question must be positive")
    if negative_marks < 0:
        raise ValueError("negative_marks cannot be negative")

    grades = [grade_answer(a, marks_per_question, negative_marks) for a in answers]
    correct = sum(1 for g in grades if g.is_correct is True)
    incorrect = sum(1 for g in grades if g.is_correct is False)
    unanswered = sum(1 for g in grades if g.is_correct is None)
    max_score = _round(marks_per_question * len(grades))
    # Computed from counts (not summed per-question values) so rounding never compounds.
    score = _round(correct * marks_per_question - incorrect * negative_marks)
    percentage = round(score / max_score * 100, 2) if max_score else 0.0
    return GradeSummary(
        grades=grades,
        score=score,
        max_score=max_score,
        percentage=percentage,
        correct=correct,
        incorrect=incorrect,
        unanswered=unanswered,
        negative_marks_total=_round(incorrect * negative_marks),
    )


@dataclass
class TopicTally:
    total: int = 0
    correct: int = 0
    incorrect: int = 0
    unanswered: int = 0

    @property
    def accuracy(self) -> float | None:
        attempted = self.correct + self.incorrect
        return round(self.correct / attempted * 100, 2) if attempted else None


def topic_breakdown(items: Iterable[tuple[str, bool | None]]) -> dict[str, TopicTally]:
    """Aggregate (topic, is_correct) pairs into per-topic tallies.

    Topics are matched case-insensitively; the first spelling seen is used as the label.
    """
    tallies: dict[str, TopicTally] = {}
    labels: dict[str, str] = {}
    for topic, is_correct in items:
        label = " ".join((topic or "").split()) or DEFAULT_TOPIC
        key = label.casefold()
        labels.setdefault(key, label)
        tally = tallies.setdefault(key, TopicTally())
        tally.total += 1
        if is_correct is True:
            tally.correct += 1
        elif is_correct is False:
            tally.incorrect += 1
        else:
            tally.unanswered += 1
    return {labels[key]: tallies[key] for key in sorted(tallies)}
