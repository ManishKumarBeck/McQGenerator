import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import attempts as attempt_service


def start(client, test_id):
    response = client.post(f"/api/tests/{test_id}/attempts")
    assert response.status_code in (200, 201), response.text
    return response


def answer(client, attempt_id, position, selected, marked=False, time_spent=0):
    return client.put(
        f"/api/attempts/{attempt_id}/answers/{position}",
        json={"selected_option": selected, "marked_for_review": marked, "time_spent_seconds": time_spent},
    )


def correct_map(client, attempt_id):
    """Look up correct answers via the snapshot (tests only; the API never exposes them early)."""
    db = client.app.state.session_factory()
    try:
        attempt = attempt_service.get_attempt(db, attempt_id)
        return {a.position: a.correct_option for a in attempt.answers}
    finally:
        db.close()


# --------------------------------------------------------------------------- start / resume


def test_start_returns_session_without_answers(client, make_test, clock):
    test = make_test()
    response = start(client, test["id"])
    assert response.status_code == 201
    session = response.json()
    assert session["status"] == "in_progress"
    assert session["question_count"] == 4
    assert session["duration_seconds"] == 600
    assert session["max_score"] == 16
    assert len(session["questions"]) == 4
    assert all("correct_option" not in q and "explanation" not in q for q in session["questions"])
    assert "correct_option" not in client.get(f"/api/attempts/{session['id']}").text


def test_start_resumes_existing_attempt(client, make_test):
    test = make_test()
    first = start(client, test["id"]).json()
    second = start(client, test["id"])
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    summary = client.get(f"/api/tests/{test['id']}").json()
    assert summary["in_progress_attempt_id"] == first["id"]


def test_cannot_start_draft_or_missing_test(client, make_test):
    draft = make_test(status="draft")
    response = client.post(f"/api/tests/{draft['id']}/attempts")
    assert response.status_code == 409
    assert response.json()["code"] == "test_not_published"
    assert client.post("/api/tests/999/attempts").status_code == 404


def test_shuffled_options_keep_correct_answer(client, make_test):
    test = make_test(shuffle_questions=True, shuffle_options=True)
    session = start(client, test["id"]).json()
    originals = {q["text"]: q for q in test["questions"]}
    correct = correct_map(client, session["id"])
    for q in session["questions"]:
        original = originals[q["text"]]
        assert sorted(q["options"]) == sorted(original["options"])
        assert q["options"][correct[q["position"]]] == original["options"][original["correct_option"]]


# --------------------------------------------------------------------------- answering


def test_answers_persist_and_are_returned_on_reload(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    assert answer(client, attempt["id"], 0, 2, marked=True, time_spent=12).status_code == 200
    assert answer(client, attempt["id"], 1, None, marked=True).status_code == 200
    reloaded = client.get(f"/api/attempts/{attempt['id']}").json()["questions"]
    assert (
        reloaded[0]["selected_option"],
        reloaded[0]["marked_for_review"],
        reloaded[0]["time_spent_seconds"],
    ) == (2, True, 12)
    assert (reloaded[1]["selected_option"], reloaded[1]["marked_for_review"]) == (None, True)
    # clearing a response
    answer(client, attempt["id"], 0, None)
    assert client.get(f"/api/attempts/{attempt['id']}").json()["questions"][0]["selected_option"] is None


def test_time_spent_never_decreases(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    answer(client, attempt["id"], 0, 1, time_spent=30)
    saved = answer(client, attempt["id"], 0, 1, time_spent=5).json()
    assert saved["time_spent_seconds"] == 30


@pytest.mark.parametrize(
    "position,payload,status",
    [
        (0, {"selected_option": 4}, 422),  # only 4 options (0-3)
        (0, {"selected_option": -1}, 422),
        (0, {"selected_option": 99}, 422),
        (99, {"selected_option": 0}, 404),
        (0, {"selected_option": "a"}, 422),
    ],
)
def test_invalid_answers_rejected(client, make_test, position, payload, status):
    attempt = start(client, make_test()["id"]).json()
    response = client.put(f"/api/attempts/{attempt['id']}/answers/{position}", json=payload)
    assert response.status_code == status


def test_unknown_attempt(client):
    assert client.get("/api/attempts/nope").status_code == 404
    assert client.post("/api/attempts/nope/submit", json={}).status_code == 404


# --------------------------------------------------------------------------- submit & grading


def test_submit_grades_with_negative_marking(client, make_test, clock):
    attempt = start(client, make_test()["id"]).json()
    correct = correct_map(client, attempt["id"])
    answer(client, attempt["id"], 0, correct[0])  # +4
    answer(client, attempt["id"], 1, correct[1])  # +4
    answer(client, attempt["id"], 2, (correct[2] + 1) % 4)  # -1
    clock.advance(seconds=95)
    result = client.post(f"/api/attempts/{attempt['id']}/submit", json={"reason": "manual"}).json()
    assert result["status"] == "submitted"
    assert result["submit_reason"] == "manual"
    assert (result["correct_count"], result["incorrect_count"], result["unanswered_count"]) == (2, 1, 1)
    assert result["score"] == 7
    assert result["max_score"] == 16
    assert result["percentage"] == 43.75
    assert result["negative_marks_total"] == 1
    assert result["accuracy"] == pytest.approx(66.67)
    assert result["time_spent_seconds"] == 95
    assert result["already_submitted"] is False
    assert [q["marks_awarded"] for q in result["questions"]] == [4, 4, -1, 0]
    assert result["questions"][0]["explanation"] == "Two plus two is four."
    topics = {t["topic"]: t for t in result["topic_breakdown"]}
    assert topics["Arithmetic"]["correct"] == 1 and topics["Arithmetic"]["incorrect"] == 1
    assert topics["Geography"]["correct"] == 1 and topics["Geography"]["unanswered"] == 1


def test_submit_with_batch_answers_from_client(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    correct = correct_map(client, attempt["id"])
    batch = [{"position": p, "selected_option": c} for p, c in correct.items()]
    result = client.post(f"/api/attempts/{attempt['id']}/submit", json={"answers": batch}).json()
    assert result["score"] == 16
    assert result["percentage"] == 100


def test_submit_with_invalid_batch_does_not_finalize(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    response = client.post(
        f"/api/attempts/{attempt['id']}/submit", json={"answers": [{"position": 50, "selected_option": 0}]}
    )
    assert response.status_code == 422
    assert client.get(f"/api/attempts/{attempt['id']}").json()["status"] == "in_progress"


def test_empty_submission_scores_zero(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    result = client.post(f"/api/attempts/{attempt['id']}/submit", json={}).json()
    assert result["score"] == 0
    assert result["unanswered_count"] == 4
    assert result["accuracy"] is None


def test_duplicate_submissions_are_idempotent(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    correct = correct_map(client, attempt["id"])
    answer(client, attempt["id"], 0, correct[0])
    first = client.post(f"/api/attempts/{attempt['id']}/submit", json={}).json()
    second = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"answers": [{"position": 1, "selected_option": correct[1]}]},
    ).json()
    assert second["already_submitted"] is True
    assert second["score"] == first["score"] == 4
    assert second["submitted_at"] == first["submitted_at"]


def test_concurrent_submissions_grade_once(settings, generator, tmp_path):
    # A real file database (not the shared in-memory connection) so threads truly race.
    settings.database_url = f"sqlite:///{(tmp_path / 'race.db').as_posix()}"
    app = create_app(settings, generator=generator, frontend_dist=None)
    with TestClient(app) as file_client:
        test = file_client.post(
            "/api/tests",
            json={
                "title": "Race",
                "status": "published",
                "questions": [{"text": "Q?", "options": ["a", "b"], "correct_option": 0}],
            },
        ).json()
        attempt = start(file_client, test["id"]).json()
        results, barrier = [], threading.Barrier(5)

        def submit():
            barrier.wait()
            response = file_client.post(f"/api/attempts/{attempt['id']}/submit", json={})
            results.append(response.json() if response.status_code == 200 else response.text)

        threads = [threading.Thread(target=submit) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert all(isinstance(r, dict) for r in results), results
    assert sum(not r["already_submitted"] for r in results) == 1
    assert len({r["submitted_at"] for r in results}) == 1


def test_no_changes_after_submission(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    client.post(f"/api/attempts/{attempt['id']}/submit", json={})
    response = answer(client, attempt["id"], 0, 1)
    assert response.status_code == 409
    assert response.json()["code"] == "attempt_closed"


def test_result_not_available_before_submit(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    response = client.get(f"/api/attempts/{attempt['id']}/result")
    assert response.status_code == 409
    assert response.json()["code"] == "attempt_in_progress"


def test_new_attempt_after_submission(client, make_test):
    test = make_test()
    first = start(client, test["id"]).json()
    client.post(f"/api/attempts/{first['id']}/submit", json={})
    second = start(client, test["id"])
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


# --------------------------------------------------------------------------- timer


def test_answer_within_grace_period_is_accepted(client, make_test, clock):
    attempt = start(client, make_test(duration_minutes=1)["id"]).json()
    clock.advance(seconds=63)  # deadline 60s + 5s grace
    assert answer(client, attempt["id"], 0, 1).status_code == 200


def test_answer_after_deadline_auto_submits(client, make_test, clock):
    attempt = start(client, make_test(duration_minutes=1)["id"]).json()
    correct = correct_map(client, attempt["id"])
    answer(client, attempt["id"], 0, correct[0])
    clock.advance(seconds=70)
    response = answer(client, attempt["id"], 1, correct[1])
    assert response.status_code == 409
    assert response.json()["code"] == "attempt_closed"
    result = client.get(f"/api/attempts/{attempt['id']}/result").json()
    assert result["submit_reason"] == "timeout"
    assert result["score"] == 4  # the late answer was not counted
    assert result["time_spent_seconds"] == 60
    assert result["submitted_at"] == result["deadline_at"]


def test_timeout_submission_from_client(client, make_test, clock):
    attempt = start(client, make_test(duration_minutes=1)["id"]).json()
    correct = correct_map(client, attempt["id"])
    clock.advance(seconds=61)  # timer fired; request arrives within grace
    result = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"reason": "timeout", "answers": [{"position": 0, "selected_option": correct[0]}]},
    ).json()
    assert result["submit_reason"] == "timeout"
    assert result["score"] == 4


def test_late_submission_ignores_answers(client, make_test, clock):
    attempt = start(client, make_test(duration_minutes=1)["id"]).json()
    correct = correct_map(client, attempt["id"])
    clock.advance(minutes=10)
    result = client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"reason": "manual", "answers": [{"position": 0, "selected_option": correct[0]}]},
    ).json()
    assert result["submit_reason"] == "timeout"
    assert result["score"] == 0


def test_expired_attempt_closed_when_viewed_or_listed(client, make_test, clock):
    test = make_test(duration_minutes=1)
    first = start(client, test["id"]).json()
    clock.advance(minutes=5)
    session = client.get(f"/api/attempts/{first['id']}").json()
    assert session["status"] == "submitted"

    second = start(client, test["id"]).json()  # new attempt, old one is closed
    assert second["id"] != first["id"]
    clock.advance(minutes=5)
    listed = {a["id"]: a for a in client.get("/api/attempts").json()}
    assert listed[second["id"]]["status"] == "submitted"
    assert listed[second["id"]]["submit_reason"] == "timeout"


def test_start_after_expiry_creates_fresh_attempt(client, make_test, clock):
    test = make_test(duration_minutes=1)
    first = start(client, test["id"]).json()
    clock.advance(minutes=2)
    second = start(client, test["id"])
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_server_time_reported_for_client_sync(client, make_test, clock):
    attempt = start(client, make_test()["id"]).json()
    assert attempt["server_time"].endswith("Z") or "+00:00" in attempt["server_time"]
    assert attempt["deadline_at"] > attempt["started_at"]


# --------------------------------------------------------------------------- history


def test_results_survive_test_edits_and_deletion(client, make_test):
    test = make_test()
    attempt = start(client, test["id"]).json()
    client.post(f"/api/attempts/{attempt['id']}/submit", json={})
    before = client.get(f"/api/attempts/{attempt['id']}/result").json()

    client.put(
        f"/api/tests/{test['id']}", json={**test, "title": "Renamed", "questions": test["questions"][:1]}
    )
    client.delete(f"/api/tests/{test['id']}")
    after = client.get(f"/api/attempts/{attempt['id']}/result").json()
    assert after["test_id"] is None
    assert after["test_title"] == "Sample test"
    assert after["questions"] == before["questions"]


def test_history_listing_and_filters(client, make_test):
    a = make_test(title="A")
    b = make_test(title="B")
    first = start(client, a["id"]).json()
    client.post(f"/api/attempts/{first['id']}/submit", json={})
    start(client, b["id"])
    assert len(client.get("/api/attempts").json()) == 2
    assert [x["test_title"] for x in client.get("/api/attempts", params={"test_id": a["id"]}).json()] == ["A"]
    assert [
        x["test_title"] for x in client.get("/api/attempts", params={"status": "in_progress"}).json()
    ] == ["B"]
    assert len(client.get("/api/attempts", params={"limit": 1}).json()) == 1
    assert client.get("/api/attempts", params={"limit": 0}).status_code == 422


def test_test_summary_reflects_attempt_stats(client, make_test):
    test = make_test()
    attempt = start(client, test["id"]).json()
    correct = correct_map(client, attempt["id"])
    client.post(
        f"/api/attempts/{attempt['id']}/submit",
        json={"answers": [{"position": p, "selected_option": c} for p, c in correct.items()]},
    )
    summary = client.get(f"/api/tests/{test['id']}").json()
    assert summary["attempt_count"] == 1
    assert summary["best_percentage"] == 100
    assert summary["in_progress_attempt_id"] is None
    assert summary["last_attempt_at"] is not None


def test_delete_attempt(client, make_test):
    attempt = start(client, make_test()["id"]).json()
    assert client.delete(f"/api/attempts/{attempt['id']}").status_code == 204
    assert client.get(f"/api/attempts/{attempt['id']}").status_code == 404
