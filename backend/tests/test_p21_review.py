from __future__ import annotations

from backend.content_pipeline.review import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MIN_CORRECTS,
    due_from_mastery,
    review_due,
)

DAY = 86400.0


# --------------------------------------------------------------------------- #
# due_from_mastery — the pure distinct-count decision core                     #
# --------------------------------------------------------------------------- #


def test_due_from_mastery_gates_on_distinct_count():
    now = 100 * DAY
    # lapsed but only 1 distinct correct -> not yet mastered -> not due
    assert due_from_mastery([("s1", now - 5 * DAY, 1)], now, interval_seconds=2 * DAY) == []
    # >= min_corrects distinct AND lapsed -> due
    due = due_from_mastery([("s1", now - 5 * DAY, 2)], now, interval_seconds=2 * DAY)
    assert [d.skill_id for d in due] == ["s1"] and due[0].seconds_since == 5 * DAY


def test_due_from_mastery_recent_is_not_due():
    now = 100 * DAY
    assert due_from_mastery([("s1", now - 0.1 * DAY, 5)], now, interval_seconds=2 * DAY) == []


def test_due_from_mastery_sorts_most_overdue_first():
    now = 100 * DAY
    mastery = [("s1", now - 3 * DAY, 2), ("s2", now - 7 * DAY, 2)]
    due = due_from_mastery(mastery, now, interval_seconds=2 * DAY)
    assert [d.skill_id for d in due] == ["s2", "s1"]


def test_default_min_corrects_is_two():
    assert DEFAULT_MIN_CORRECTS == 2


# --------------------------------------------------------------------------- #
# review_due — multi-student raw-row adapter (now counts DISTINCT problems)     #
# --------------------------------------------------------------------------- #


def test_review_due_requires_distinct_problems_not_repeats():
    now = 100 * DAY
    # same problem answered correctly twice -> distinct_count == 1 -> NOT due (default min 2)
    repeats = [
        ("stu", "s1", "p1", "correct", now - 5 * DAY),
        ("stu", "s1", "p1", "correct", now - 4 * DAY),
    ]
    assert review_due(repeats, now, interval_seconds=2 * DAY) == {}
    # two DISTINCT problems, both lapsed -> due
    distinct = [
        ("stu", "s1", "p1", "correct", now - 5 * DAY),
        ("stu", "s1", "p2", "correct", now - 4 * DAY),
    ]
    due = review_due(distinct, now, interval_seconds=2 * DAY)
    assert [d.skill_id for d in due["stu"]] == ["s1"]


def test_skill_correct_long_ago_is_due_recent_is_not():
    now = 100 * DAY
    attempts = [
        ("stu", "lin_evaluate", "p1", "correct", now - 5 * DAY),  # lapsed
        ("stu", "lin_slope_two_points", "p2", "correct", now - 0.5 * DAY),  # recent
    ]
    due = review_due(attempts, now, interval_seconds=2 * DAY, min_corrects=1)  # isolate lapse
    assert [d.skill_id for d in due["stu"]] == ["lin_evaluate"]
    assert due["stu"][0].seconds_since == 5 * DAY


def test_never_correct_skill_is_not_due():
    now = 100 * DAY
    attempts = [("stu", "lin_evaluate", "p1", "incorrect", now - 10 * DAY)]
    assert review_due(attempts, now, interval_seconds=2 * DAY) == {}


def test_recently_re_correct_resets_due_status():
    # Two DISTINCT problems (so the count gate is satisfied at min_corrects=1); the test
    # proves the RECENCY reset, not the count gate: latest correct is recent -> not due.
    now = 100 * DAY
    attempts = [
        ("stu", "lin_evaluate", "p1", "correct", now - 9 * DAY),
        ("stu", "lin_evaluate", "p2", "correct", now - 0.1 * DAY),  # re-mastered recently
    ]
    assert review_due(attempts, now, interval_seconds=2 * DAY, min_corrects=1) == {}


def test_per_student_isolation_and_overdue_ordering():
    now = 100 * DAY
    attempts = [
        ("a", "s1", "p1", "correct", now - 3 * DAY),
        ("a", "s2", "p2", "correct", now - 7 * DAY),
        ("b", "s1", "p3", "correct", now - 4 * DAY),
    ]
    due = review_due(attempts, now, interval_seconds=2 * DAY, min_corrects=1)
    assert [d.skill_id for d in due["a"]] == ["s2", "s1"]  # most overdue first
    assert [d.skill_id for d in due["b"]] == ["s1"]


def test_is_deterministic_and_ignores_undecidable():
    now = 100 * DAY
    attempts = [
        ("stu", "s1", "p1", "undecidable", now - 9 * DAY),  # must not count toward mastery
        ("stu", "s1", "p2", "correct", now - 8 * DAY),
    ]
    a = review_due(attempts, now, min_corrects=1)
    b = review_due(list(reversed(attempts)), now, min_corrects=1)
    assert a == b
    assert a["stu"][0].skill_id == "s1"


def test_default_interval_is_two_days():
    assert DEFAULT_INTERVAL_SECONDS == 2 * DAY


def test_review_queue_reads_the_attempt_log(tmp_path):
    import sqlite3

    from backend.content_pipeline.ingest import review_queue

    db = tmp_path / "session.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE attempt_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, session_id TEXT, "
        "student_id TEXT, skill_id TEXT, problem_id TEXT, check_result TEXT, xp_awarded INTEGER)"
    )
    now = 100 * DAY
    rows = [
        # lin_evaluate: 2 DISTINCT correct problems, both lapsed -> due (default min_corrects=2)
        (now - 6 * DAY, "s1", "stu", "lin_evaluate", "p1", "correct", 8),
        (now - 5 * DAY, "s1", "stu", "lin_evaluate", "p2", "correct", 8),
        # lin_slope_two_points: only 1 distinct correct -> not mastered -> not due
        (now - 0.1 * DAY, "s1", "stu", "lin_slope_two_points", "q1", "correct", 8),
    ]
    for row in rows:
        conn.execute(
            "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
            "VALUES (?,?,?,?,?,?,?)",
            row,
        )
    conn.commit()
    conn.close()

    report = review_queue(db, now, interval_seconds=2 * DAY)
    assert list(report) == ["stu"]
    assert [item["skill_id"] for item in report["stu"]] == ["lin_evaluate"]
