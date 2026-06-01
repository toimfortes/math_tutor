from __future__ import annotations

from backend.content_pipeline.review import DEFAULT_INTERVAL_SECONDS, review_due

DAY = 86400.0


def test_skill_correct_long_ago_is_due_recent_is_not():
    now = 100 * DAY
    attempts = [
        ("stu", "lin_evaluate", "correct", now - 5 * DAY),  # lapsed -> due
        ("stu", "lin_slope_two_points", "correct", now - 0.5 * DAY),  # recent -> not due
    ]
    due = review_due(attempts, now, interval_seconds=2 * DAY)
    skills = [d.skill_id for d in due["stu"]]
    assert skills == ["lin_evaluate"]
    assert due["stu"][0].seconds_since == 5 * DAY


def test_never_correct_skill_is_not_due():
    now = 100 * DAY
    attempts = [("stu", "lin_evaluate", "incorrect", now - 10 * DAY)]
    assert review_due(attempts, now, interval_seconds=2 * DAY) == {}


def test_recently_re_correct_resets_due_status():
    now = 100 * DAY
    attempts = [
        ("stu", "lin_evaluate", "correct", now - 9 * DAY),  # old correct
        ("stu", "lin_evaluate", "correct", now - 0.1 * DAY),  # re-mastered recently -> latest wins
    ]
    assert review_due(attempts, now, interval_seconds=2 * DAY) == {}


def test_per_student_isolation_and_overdue_ordering():
    now = 100 * DAY
    attempts = [
        ("a", "s1", "correct", now - 3 * DAY),
        ("a", "s2", "correct", now - 7 * DAY),
        ("b", "s1", "correct", now - 4 * DAY),
    ]
    due = review_due(attempts, now, interval_seconds=2 * DAY)
    assert [d.skill_id for d in due["a"]] == ["s2", "s1"]  # most overdue first
    assert [d.skill_id for d in due["b"]] == ["s1"]


def test_is_deterministic_and_ignores_undecidable():
    now = 100 * DAY
    attempts = [
        ("stu", "s1", "undecidable", now - 9 * DAY),
        ("stu", "s1", "correct", now - 8 * DAY),
    ]
    a = review_due(attempts, now)
    b = review_due(list(reversed(attempts)), now)
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
    conn.execute(
        "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
        "VALUES (?,?,?,?,?,?,?)",
        (now - 5 * DAY, "s1", "stu", "lin_evaluate", "p", "correct", 8),
    )
    conn.execute(
        "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
        "VALUES (?,?,?,?,?,?,?)",
        (now - 0.1 * DAY, "s1", "stu", "lin_slope_two_points", "q", "correct", 8),
    )
    conn.commit()
    conn.close()

    report = review_queue(db, now, interval_seconds=2 * DAY)
    assert list(report) == ["stu"]
    assert [item["skill_id"] for item in report["stu"]] == ["lin_evaluate"]  # lapsed only
