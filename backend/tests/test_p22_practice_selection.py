from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.domain.practice_selection import (
    LOWER_THRESHOLD,
    RAISE_THRESHOLD,
    SEED_BAND,
    WINDOW,
    order_for_student,
    target_band,
)
from backend.app.main import create_app

T, F = True, False


# --------------------------------------------------------------------------- #
# target_band — the read-only staircase                                       #
# --------------------------------------------------------------------------- #


def test_no_history_returns_seed_band():
    assert target_band([]) == SEED_BAND


def test_below_window_holds_at_median_anchor_with_no_move():
    # 2 of 2 correct but window not full -> hold at median, no +1 move.
    assert target_band([(3, T), (3, T)]) == 3


def test_even_count_short_history_uses_lower_median():
    # Bands {3,4}, lower median = 3, and < WINDOW so no move.
    assert target_band([(3, T), (4, T)]) == 3


def test_full_window_high_accuracy_steps_up():
    # 5/5 = 1.0 >= RAISE -> anchor(2) + 1 = 3.
    assert target_band([(2, T), (2, T), (2, T), (2, T), (2, T)]) == 3


def test_four_of_five_reaches_raise_threshold_and_steps_up():
    # 4/5 = 0.8 == RAISE_THRESHOLD -> step up (the 0.85 bug would have held here).
    assert RAISE_THRESHOLD <= 0.8
    assert target_band([(2, T), (2, T), (2, T), (2, T), (2, F)]) == 3


def test_full_window_low_accuracy_steps_down():
    # 2/5 = 0.4 <= LOWER -> anchor(3) - 1 = 2.
    assert LOWER_THRESHOLD >= 0.4
    assert target_band([(3, T), (3, T), (3, F), (3, F), (3, F)]) == 2


def test_full_window_mid_accuracy_holds():
    # 3/5 = 0.6 -> hold at anchor(3).
    assert target_band([(3, T), (3, T), (3, T), (3, F), (3, F)]) == 3


def test_median_anchor_smooths_single_outlier_band():
    # One out-of-order band-5 click does not leap the anchor (median = 2).
    assert target_band([(2, T), (2, T), (5, T), (2, T), (2, T)]) == 3  # median 2, 5/5 -> +1


def test_clamps_at_max_band():
    assert target_band([(5, T), (5, T), (5, T), (5, T), (5, T)]) == 5


def test_clamps_at_min_band():
    assert target_band([(1, F), (1, F), (1, F), (1, F), (1, F)]) == 1


def test_only_last_window_attempts_count():
    # Leading band-5 correct answers fall outside the window; window is band-1, all wrong.
    recent = [(5, T)] * 10 + [(1, F)] * WINDOW
    assert target_band(recent) == 1  # median of window = 1, 0/5 -> -1 -> clamp 1


def test_target_band_is_deterministic_for_identical_chronological_input():
    recent = [(2, T), (3, T), (2, F), (3, T), (2, T)]
    assert target_band(list(recent)) == target_band(list(recent))


# --------------------------------------------------------------------------- #
# order_for_student — within-skill targeting, cross-skill layout preserved     #
# --------------------------------------------------------------------------- #


def _p(pid, skill, diff):
    return {"id": pid, "skill_id": skill, "difficulty": diff}


def test_within_skill_orders_nearest_target_first():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("a3", "A", 3)]
    ordered = order_for_student(problems, {"A": 3})
    assert [p["id"] for p in ordered] == ["a3", "a2", "a1"]  # distance 0,1,2


def test_equal_distance_breaks_to_easier_band_then_id():
    problems = [_p("a4", "A", 4), _p("a2", "A", 2)]  # both distance 1 from target 3
    ordered = order_for_student(problems, {"A": 3})
    assert [p["id"] for p in ordered] == ["a2", "a4"]  # easier band first


def test_untouched_skill_is_byte_identical_and_slots_preserved():
    # A is touched (target 3) and reorders only within its own slots (0, 2);
    # B is untouched and its problems do not move at all (slots 1, 3 unchanged).
    problems = [_p("a1", "A", 1), _p("b1", "B", 1), _p("a3", "A", 3), _p("b3", "B", 3)]
    ordered = order_for_student(problems, {"A": 3})
    ids = [p["id"] for p in ordered]
    assert ids == ["a3", "b1", "a1", "b3"]  # A: slot0=a3,slot2=a1; B untouched at slots 1,3


def test_empty_targets_returns_input_unchanged():
    # No history anywhere -> identical to input (no fresh-vs-active discontinuity).
    problems = [_p("a1", "A", 1), _p("b1", "B", 1), _p("a2", "A", 2)]
    assert order_for_student(problems, {}) == problems


def test_order_for_student_is_order_independent():
    problems = [_p("a1", "A", 1), _p("a3", "A", 3), _p("a2", "A", 2)]
    a = order_for_student(list(problems), {"A": 2})
    b = order_for_student(list(reversed(problems)), {"A": 2})
    assert a == b


# --------------------------------------------------------------------------- #
# Endpoint integration                                                         #
# --------------------------------------------------------------------------- #


def _bank(items):
    """items: list of (id, skill_id, difficulty, canonical). All numeric."""
    problems = []
    for pid, skill, diff, canonical in items:
        problems.append(
            {
                "id": pid,
                "skill_id": skill,
                "answer_type": "numeric",
                "checker": "numeric",
                "representations": ["symbolic"],
                "difficulty": diff,
                "params": {},
                "known_wrong_answers": {},
                "neutral": {"prompt": f"solve {pid}", "canonical_answer": canonical, "solution_method": ""},
                "hint_scaffold": {
                    "max_safe_hint_level": 0,
                    "level_0": "think",
                    "level_1": "",
                    "level_2": "",
                    "level_3": None,
                },
            }
        )
    return {"schema_version": "1.0", "domain": "linear_functions", "pool": "practice", "problems": problems}


def _client(tmp_path, items):
    bank_path = tmp_path / "practice.json"
    bank_path.write_text(json.dumps(_bank(items)))
    session_db = tmp_path / "session.db"
    settings = Settings.from_env(
        {"PRACTICE_BANK_PATH": str(bank_path), "SESSION_DB_PATH": str(session_db)}
    )
    client = TestClient(create_app(settings))
    return client, session_db


def _auth(client, student="ada"):
    client.post("/auth/register", json={"student_id": student, "password": "pw"})
    token = client.post("/auth/login", json={"student_id": student, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_log(session_db, student, rows):
    """rows: list of (problem_id, skill_id, check_result) inserted in order."""
    conn = sqlite3.connect(str(session_db))
    for problem_id, skill_id, result in rows:
        conn.execute(
            "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (0.0, f"practice:{student}", student, skill_id, problem_id, result, 0),
        )
    conn.commit()
    conn.close()


def test_fresh_student_gets_easiest_first(tmp_path):
    items = [("a1", "A", 1, "1"), ("a3", "A", 3, "3"), ("a2", "A", 2, "2")]
    client, _ = _client(tmp_path, items)
    auth = _auth(client)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert [p["difficulty"] for p in problems] == [1, 2, 3]  # unchanged easiest-first


def test_all_undecidable_history_leaves_order_unchanged(tmp_path):
    items = [("a1", "A", 1, "1"), ("a3", "A", 3, "3"), ("a2", "A", 2, "2")]
    client, session_db = _client(tmp_path, items)
    auth = _auth(client)
    _seed_log(session_db, "ada", [("a1", "A", "undecidable"), ("a2", "A", None)])
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert [p["difficulty"] for p in problems] == [1, 2, 3]


def test_farming_one_problem_does_not_climb(tmp_path):
    # Same band-2 problem answered correctly 5x -> dedup to one -> < WINDOW -> hold at 2.
    items = [
        ("a1", "A", 1, "1"),
        ("a2", "A", 2, "2"),
        ("a3", "A", 3, "3"),
    ]
    client, session_db = _client(tmp_path, items)
    auth = _auth(client)
    _seed_log(session_db, "ada", [("a2", "A", "correct")] * 5)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    # target held at band 2 (one distinct attempt) -> a2 leads, not a3.
    assert problems[0]["id"] == "a2"


def test_re_attempt_latest_result_wins_and_moves_to_window(tmp_path):
    # Five distinct band-3 problems answered correctly would give target 4 (band-4
    # leads). Re-answering three of them INCORRECT must override (latest wins) AND
    # land in the recent window: 2/5 correct -> target 2 -> band-2 problem leads.
    # If dedup kept the FIRST result instead, all 5 would read correct -> band-4 leads.
    items = [
        ("aL", "A", 2, "0"),
        ("am1", "A", 3, "1"),
        ("am2", "A", 3, "2"),
        ("am3", "A", 3, "3"),
        ("am4", "A", 3, "4"),
        ("am5", "A", 3, "5"),
        ("aH", "A", 4, "6"),
    ]
    client, session_db = _client(tmp_path, items)
    auth = _auth(client)
    drilled = ["am1", "am2", "am3", "am4", "am5"]
    seq = [(pid, "A", "correct") for pid in drilled]
    seq += [(pid, "A", "incorrect") for pid in ("am1", "am2", "am3")]  # latest = incorrect
    _seed_log(session_db, "ada", seq)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["id"] == "aL"  # target dropped to band 2; band-4 would mean first-result-wins bug


def test_spamming_one_problem_does_not_flush_other_history(tmp_path):
    # Regression for the dedup-behind-raw-limit flush: five distinct band-3 problems
    # answered correctly, then one of them spammed incorrect MORE than the read cap.
    # SQL dedups by problem_id before the limit, so the other four survive: window is
    # 4 correct / 1 incorrect = 0.8 -> target 4 (band-4 leads). A raw row limit would
    # have flushed everything to the single spammed attempt -> target 3.
    items = [
        ("am1", "A", 3, "1"),
        ("am2", "A", 3, "2"),
        ("am3", "A", 3, "3"),
        ("am4", "A", 3, "4"),
        ("am5", "A", 3, "5"),
        ("aH", "A", 4, "6"),
    ]
    client, session_db = _client(tmp_path, items)
    auth = _auth(client)
    seq = [(pid, "A", "correct") for pid in ("am1", "am2", "am3", "am4", "am5")]
    seq += [("am1", "A", "incorrect")] * 250  # spam well beyond PRACTICE_HISTORY_READ_CAP (200)
    _seed_log(session_db, "ada", seq)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["id"] == "aH"  # band-4 leads; flush bug would leave a band-3 leading


def test_strong_band2_performance_leads_with_harder_band(tmp_path):
    # Five DISTINCT band-2 problems answered correctly -> full window, 5/5 -> target 3.
    items = [
        ("a0", "A", 1, "0"),
        ("a1", "A", 2, "1"),
        ("a2", "A", 2, "2"),
        ("a3", "A", 2, "3"),
        ("a4", "A", 2, "4"),
        ("a5", "A", 2, "5"),
        ("a6", "A", 3, "6"),
        ("b1", "B", 1, "7"),
        ("b2", "B", 2, "8"),
    ]
    client, session_db = _client(tmp_path, items)
    auth = _auth(client)
    _seed_log(
        session_db,
        "ada",
        [(pid, "A", "correct") for pid in ("a1", "a2", "a3", "a4", "a5")],
    )
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    a_ids = [p["id"] for p in problems if p["skill_id"] == "A"]
    b_ids = [p["id"] for p in problems if p["skill_id"] == "B"]
    assert a_ids[0] == "a6"  # band-3 (target) leads skill A
    assert b_ids == ["b1", "b2"]  # untouched skill B stays easiest-first
