import io
import re

import pytest
from pypdf import PdfReader

from .conftest import SAMPLE_QUESTIONS


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def page_count(content: bytes) -> int:
    return len(PdfReader(io.BytesIO(content)).pages)


def test_defaults_prefill_heading_and_instructions(client, make_test):
    test = make_test(subject="Math", topic="Mixed", category="Grade 8")
    body = client.get(f"/api/tests/{test['id']}/pdf/defaults").json()
    assert body["title"] == "Sample test"
    assert body["subtitle"] == "Math · Mixed · Grade 8"
    assert "4 multiple-choice questions" in body["instructions"]
    assert "1 mark(s) will be deducted" in body["instructions"]
    assert body["include_answer_key"] is True


def test_download_contains_heading_questions_and_key(client, make_test):
    test = make_test()
    response = client.post(
        f"/api/tests/{test['id']}/pdf",
        json={
            "institution": "Springfield High School",
            "title": "Unit 3 Quiz",
            "subtitle": "General knowledge",
            "exam_date": "12 Nov 2026",
            "instructions": "Answer all questions.\nUse a pencil.",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert re.match(
        r'attachment; filename="unit-3-quiz-\d{4}-\d{2}-\d{2}\.pdf"', response.headers["content-disposition"]
    )
    assert response.content.startswith(b"%PDF")
    text = pdf_text(response.content)
    for expected in (
        "Springfield High School",
        "Unit 3 Quiz",
        "General knowledge",
        "Date: 12 Nov 2026",
        "Maximum marks: 16",
        "−1 per wrong answer",
        "Name:",
        "Roll No.:",
        "1. Answer all questions.",
        "2. Use a pencil.",
        "2 + 2 = ?",
        "Capital of France?",
        "(B) 4",
        "Answer Key",
        "Two plus two is four.",
    ):
        assert expected in text, expected


def test_answer_key_matches_the_unshuffled_paper(client, make_test):
    test = make_test()
    text = pdf_text(client.post(f"/api/tests/{test['id']}/pdf", json={}).content)
    key = text[text.index("Answer Key") :]
    # 2+2 -> B, France -> A, 5x3 -> B, ocean -> C
    assert re.search(r"1\.\s*B\s+2\.\s*A\s+3\.\s*B\s+4\.\s*C", key), key


def test_shuffled_versions_are_deterministic_and_consistent(client, make_test):
    test = make_test()
    url = f"/api/tests/{test['id']}/pdf"
    options = {"shuffle_questions": True, "shuffle_options": True, "version_label": "Set B"}
    first = client.post(url, json=options).content
    second = client.post(url, json=options).content
    assert pdf_text(first) == pdf_text(second)
    other = pdf_text(client.post(url, json={**options, "version_label": "Set C"}).content)
    assert "Paper version: Set C" in other

    # Every key entry must point at the original correct answer.
    text = pdf_text(first)
    answers = {q["text"]: q["options"][q["correct_option"]] for q in SAMPLE_QUESTIONS}
    explanations = text[text.index("Explanations") :] if "Explanations" in text else ""
    assert "4" in answers.values()
    paper = text[: text.index("Answer Key")]
    key = dict(
        re.findall(r"(\d+)\.\s*([A-F])\b", text[text.index("Answer Key") : text.index("Explanations")])
    )
    stems = re.findall(r"\n\s*(\d+)\.\s+(.+\?)", paper)
    assert len(stems) == len(SAMPLE_QUESTIONS)
    for question_number, question_text in stems:
        block = paper[paper.index(question_text) :]
        letter = key[question_number]
        # Two-column option rows are extracted on one line: "(A)  3  (B)  4".
        option = re.search(rf"\({letter}\)\s+(.+?)(?=\s+\([A-F]\)\s|\n|$)", block).group(1).strip()
        assert option == answers[question_text], (question_text, letter, option)
    assert explanations.startswith("Explanations")


def test_optional_sections_can_be_turned_off(client, make_test):
    test = make_test()
    url = f"/api/tests/{test['id']}/pdf"
    minimal = pdf_text(
        client.post(
            url, json={"include_answer_key": False, "student_fields": False, "show_details": False}
        ).content
    )
    assert "Answer Key" not in minimal
    assert "Roll No." not in minimal
    assert "Maximum marks" not in minimal

    no_explanations = pdf_text(client.post(url, json={"include_explanations": False}).content)
    assert "Answer Key" in no_explanations
    assert "Two plus two is four." not in no_explanations


def test_answer_sheet_page(client, make_test):
    test = make_test()
    url = f"/api/tests/{test['id']}/pdf"
    without = client.post(url, json={"include_answer_key": False}).content
    with_sheet = client.post(url, json={"include_answer_key": False, "include_answer_sheet": True}).content
    assert page_count(with_sheet) == page_count(without) + 1
    assert "Answer Sheet" in pdf_text(with_sheet)


def test_long_tests_paginate(client, make_test):
    questions = [
        {
            "text": f"Long question {i}? " + "Some context. " * 30,
            "options": ["a", "b", "c", "d"],
            "correct_option": 0,
        }
        for i in range(60)
    ]
    test = make_test(questions=questions)
    content = client.post(f"/api/tests/{test['id']}/pdf", json={"include_answer_sheet": True}).content
    assert page_count(content) > 10
    assert "Long question 59?" in pdf_text(content)


def test_unicode_text_is_preserved(client, make_test):
    questions = [
        {"text": "Simplify: 6 × 3 − 4 ÷ 2 ≈ ?", "options": ["16", "π", "√2", "∞"], "correct_option": 0}
    ]
    test = make_test(questions=questions, title="Mathématiques — révision")
    response = client.post(f"/api/tests/{test['id']}/pdf", json={})
    text = pdf_text(response.content)
    assert "6 × 3 − 4 ÷ 2 ≈ ?" in text
    assert "Mathématiques — révision" in text
    assert "√2" in text
    # Non-ASCII titles still give a safe ASCII file name.
    assert 'filename="math-matiques-r-vision-' in response.headers["content-disposition"]


def test_empty_and_missing_tests(client):
    empty = client.post("/api/tests", json={"title": "Empty"}).json()
    response = client.post(f"/api/tests/{empty['id']}/pdf", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "test_empty"
    assert client.post("/api/tests/999/pdf", json={}).status_code == 404
    assert client.get("/api/tests/999/pdf/defaults").status_code == 404


@pytest.mark.parametrize(
    "field,value", [("institution", "x" * 151), ("version_label", "x" * 21), ("show_details", "maybe")]
)
def test_invalid_options(client, make_test, field, value):
    test = make_test()
    assert client.post(f"/api/tests/{test['id']}/pdf", json={field: value}).status_code == 422
