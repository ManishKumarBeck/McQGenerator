import pytest

from app.services.grading import AnswerKey, grade_answer, grade_attempt, topic_breakdown


def keys(*pairs):
    return [AnswerKey(selected, correct) for selected, correct in pairs]


def test_all_correct():
    summary = grade_attempt(keys((0, 0), (1, 1), (2, 2)), marks_per_question=2, negative_marks=0.5)
    assert summary.score == 6
    assert summary.max_score == 6
    assert summary.percentage == 100
    assert (summary.correct, summary.incorrect, summary.unanswered) == (3, 0, 0)
    assert summary.accuracy == 100


def test_negative_marking_applies_only_to_wrong_answers():
    # 2 correct (+4 each), 1 wrong (-1), 1 unanswered (0)
    summary = grade_attempt(keys((1, 1), (0, 0), (3, 2), (None, 1)), 4, 1)
    assert summary.score == 7
    assert summary.max_score == 16
    assert summary.percentage == 43.75
    assert summary.negative_marks_total == 1
    assert [g.marks_awarded for g in summary.grades] == [4, 4, -1, 0]
    assert [g.is_correct for g in summary.grades] == [True, True, False, None]
    assert summary.accuracy == pytest.approx(66.67)


def test_score_can_be_negative():
    summary = grade_attempt(keys((1, 0), (1, 0)), 1, 1)
    assert summary.score == -2
    assert summary.percentage == -100


def test_fractional_marks_do_not_accumulate_float_error():
    summary = grade_attempt(keys(*[(0, 0)] * 3, *[(1, 0)] * 3), 1, 0.1)
    assert summary.score == 2.7
    summary = grade_attempt(keys(*[(1, 0)] * 3), 1, 1 / 3)
    assert summary.score == -1.0


def test_all_unanswered():
    summary = grade_attempt(keys((None, 0), (None, 1)), 1, 0.25)
    assert summary.score == 0
    assert summary.unanswered == 2
    assert summary.accuracy is None


def test_empty_attempt():
    summary = grade_attempt([], 1, 0)
    assert summary.max_score == 0
    assert summary.percentage == 0


@pytest.mark.parametrize("marks,negative", [(0, 0), (-1, 0), (1, -0.5)])
def test_invalid_marking_scheme(marks, negative):
    with pytest.raises(ValueError):
        grade_attempt([], marks, negative)


def test_grade_answer_without_negative_marking():
    assert grade_answer(AnswerKey(2, 1), 1, 0).marks_awarded == 0


def test_topic_breakdown_groups_case_insensitively_and_defaults():
    tallies = topic_breakdown([("Algebra", True), ("algebra ", False), ("", None), ("Algebra", True)])
    assert list(tallies) == ["Algebra", "General"]
    assert (tallies["Algebra"].total, tallies["Algebra"].correct, tallies["Algebra"].incorrect) == (3, 2, 1)
    assert tallies["Algebra"].accuracy == pytest.approx(66.67)
    assert tallies["General"].unanswered == 1
    assert tallies["General"].accuracy is None
