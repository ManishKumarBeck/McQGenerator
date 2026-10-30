import pytest

from .test_attempts_api import correct_map, start


def take(client, test_id, choose, clock, seconds=60):
    attempt = start(client, test_id).json()
    correct = correct_map(client, attempt["id"])
    answers = []
    for position, right in correct.items():
        choice = choose(position, right)
        if choice is not None:
            answers.append({"position": position, "selected_option": choice})
    clock.advance(seconds=seconds)
    return client.post(f"/api/attempts/{attempt['id']}/submit", json={"answers": answers}).json()


def test_empty_analytics(client):
    body = client.get("/api/analytics").json()
    assert body["summary"]["total_attempts"] == 0
    assert body["summary"]["average_percentage"] is None
    assert body["summary"]["accuracy"] is None
    assert body["topics"] == [] and body["trend"] == [] and body["recent_attempts"] == []


def test_analytics_aggregates_submitted_attempts(client, make_test, clock):
    math = make_test(title="Math", subject="Math")
    geo = make_test(title="Geo", subject="Geography")

    take(client, math["id"], lambda p, c: c, clock, seconds=120)  # 100%
    half = take(client, geo["id"], lambda p, c: c if p % 2 == 0 else (c + 1) % 4, clock, seconds=40)
    # 2 right (+8), 2 wrong (-2) => 6/16 = 37.5%
    assert half["percentage"] == 37.5
    start(client, math["id"])  # an in-progress attempt is excluded from stats

    body = client.get("/api/analytics").json()
    s = body["summary"]
    assert s["total_attempts"] == 2
    assert s["tests_taken"] == 2
    assert s["in_progress_attempts"] == 1
    assert s["average_percentage"] == pytest.approx(68.75)
    assert s["best_percentage"] == 100
    assert (s["total_correct"], s["total_incorrect"], s["total_unanswered"]) == (6, 2, 0)
    assert s["accuracy"] == 75
    assert s["total_time_seconds"] == 160
    assert s["average_time_per_question_seconds"] == 20

    topics = {t["topic"]: t for t in body["topics"]}
    assert set(topics) == {"Arithmetic", "Geography"}
    assert topics["Arithmetic"]["total"] == 4

    subjects = {x["subject"]: x for x in body["subjects"]}
    assert subjects["Geography"]["average_percentage"] == 37.5

    assert [p["test_title"] for p in body["trend"]] == ["Math", "Geo"]  # oldest first
    assert [a["test_title"] for a in body["recent_attempts"]] == ["Geo", "Math"]  # newest first


def test_topic_labels_merge_case_insensitively(client, make_test, clock):
    questions = [
        {"text": "Q1?", "options": ["a", "b"], "correct_option": 0, "topic": "Loops"},
        {"text": "Q2?", "options": ["a", "b"], "correct_option": 0, "topic": "loops"},
        {"text": "Q3?", "options": ["a", "b"], "correct_option": 0, "topic": ""},
    ]
    test = make_test(questions=questions, topic="")
    take(client, test["id"], lambda p, c: c, clock)
    topics = {t["topic"].casefold(): t for t in client.get("/api/analytics").json()["topics"]}
    assert topics["loops"]["total"] == 2
    assert topics["general"]["total"] == 1
