from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.domain.practice_selection import REVIEW_QUOTA, order_for_student
from backend.app.main import create_app, get_clock

DAY = 86400.0


def _p(pid, skill, diff):
    return {"id": pid, "skill_id": skill, "difficulty": diff}


# --------------------------------------------------------------------------- #
# order_for_student review tier — capped, interleaved promotion                #
# --------------------------------------------------------------------------- #


def test_no_due_skills_is_band_targeted_base_unchanged():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("a3", "A", 3)]
    # backward compatible: 2-arg and explicit-empty due match the band-targeted base.
    assert order_for_student(problems, {"A": 3}) == order_for_student(problems, {"A": 3}, due_skills=())


def test_one_due_skill_promotes_quota_then_base():
    # A is due; it has 4 problems. Only REVIEW_QUOTA lead, rest follow in base order.
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("a3", "A", 3), _p("a4", "A", 4), _p("b1", "B", 1)]
    ordered = order_for_student(problems, {}, due_skills=["A"])
    ids = [p["id"] for p in ordered]
    assert ids[:REVIEW_QUOTA] == ["a1", "a2"]  # base order within A (easiest-first, untargeted)
    assert set(ids[REVIEW_QUOTA:]) == {"a3", "a4", "b1"}
    assert ids[REVIEW_QUOTA:] == ["a3", "a4", "b1"]  # remainder keeps base order


def test_multiple_due_skills_round_robin_interleaved_most_overdue_first():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("b1", "B", 1), _p("b2", "B", 2)]
    # due_skills already most-overdue-first: A then B -> round-robin a1,b1,a2,b2
    ordered = order_for_student(problems, {}, due_skills=["A", "B"])
    assert [p["id"] for p in ordered] == ["a1", "b1", "a2", "b2"]


def test_cap_respected_when_skill_has_more_than_quota():
    problems = [_p(f"a{i}", "A", i) for i in range(1, 6)]  # 5 problems, all skill A
    ordered = order_for_student(problems, {}, due_skills=["A"])
    promoted = [p["id"] for p in ordered][:REVIEW_QUOTA]
    assert len(promoted) == REVIEW_QUOTA
    assert [p["id"] for p in ordered] == ["a1", "a2", "a3", "a4", "a5"]  # quota then base remainder


def test_due_skill_not_in_bank_is_noop():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2)]
    assert order_for_student(problems, {}, due_skills=["Z"]) == order_for_student(problems, {})


def test_targets_and_due_compose():
    # Due skill A is also band-targeted (3): its base order is band-targeted (a3,a2,a1);
    # promote quota=2 -> a3,a2 lead; remainder is a1 then non-due targeted skill B.
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("a3", "A", 3), _p("b1", "B", 1), _p("b2", "B", 2)]
    ordered = order_for_student(problems, {"A": 3, "B": 1}, due_skills=["A"])
    assert [p["id"] for p in ordered] == ["a3", "a2", "a1", "b1", "b2"]


def test_order_for_student_does_not_mutate_input():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("b1", "B", 1)]
    snapshot = [dict(p) for p in problems]
    order_for_student(problems, {"A": 2}, due_skills=["A"])
    assert problems == snapshot  # input list and dicts are not mutated


def test_review_promotion_is_deterministic():
    problems = [_p("a1", "A", 1), _p("a2", "A", 2), _p("b1", "B", 1)]
    a = order_for_student(list(problems), {"A": 2}, due_skills=["A", "B"])
    b = order_for_student(list(problems), {"A": 2}, due_skills=["A", "B"])
    assert a == b


# --------------------------------------------------------------------------- #
# attempt_log.mastery_by_skill — cross-session, distinct correct count         #
# --------------------------------------------------------------------------- #


def _attempt_log(tmp_path):
    from backend.app.services.attempt_log import SqliteAttemptLog

    log = SqliteAttemptLog(tmp_path / "session.db")
    return log


def _record(log, *, session_id, student_id, skill_id, problem_id, result, ts):
    log._conn.execute(
        "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
        "VALUES (?,?,?,?,?,?,?)",
        (ts, session_id, student_id, skill_id, problem_id, result, 0),
    )
    log._conn.commit()


def test_mastery_counts_assessment_and_practice(tmp_path):
    log = _attempt_log(tmp_path)
    _record(log, session_id="uuid-assess", student_id="stu", skill_id="s_assess", problem_id="p1", result="correct", ts=10.0)
    _record(log, session_id="practice:stu", student_id="stu", skill_id="s_practice", problem_id="p2", result="correct", ts=20.0)
    # cross-session; (skill, last_ts, distinct_count); ordered by skill_id
    assert log.mastery_by_skill("stu") == [("s_assess", 10.0, 1), ("s_practice", 20.0, 1)]


def test_mastery_takes_latest_correct_and_counts_distinct(tmp_path):
    log = _attempt_log(tmp_path)
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p1", result="correct", ts=10.0)
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p1", result="incorrect", ts=50.0)  # ignored
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p2", result="correct", ts=30.0)
    assert log.mastery_by_skill("stu") == [("s1", 30.0, 2)]  # latest correct ts, 2 distinct problems


def test_mastery_same_problem_twice_counts_once(tmp_path):
    log = _attempt_log(tmp_path)
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p1", result="correct", ts=10.0)
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p1", result="correct", ts=20.0)  # same problem
    assert log.mastery_by_skill("stu") == [("s1", 20.0, 1)]  # distinct count stays 1


def test_mastery_excludes_never_correct_skill(tmp_path):
    log = _attempt_log(tmp_path)
    _record(log, session_id="uuid", student_id="stu", skill_id="s1", problem_id="p1", result="incorrect", ts=10.0)
    assert log.mastery_by_skill("stu") == []


# --------------------------------------------------------------------------- #
# Endpoint integration — deterministic clock override                          #
# --------------------------------------------------------------------------- #


def _bank(items):
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
                "hint_scaffold": {"max_safe_hint_level": 0, "level_0": "x", "level_1": "", "level_2": "", "level_3": None},
            }
        )
    return {"schema_version": "1.0", "domain": "linear_functions", "pool": "practice", "problems": problems}


def _client(tmp_path, items, *, now):
    bank_path = tmp_path / "practice.json"
    bank_path.write_text(json.dumps(_bank(items)))
    session_db = tmp_path / "session.db"
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(bank_path), "SESSION_DB_PATH": str(session_db)})
    app = create_app(settings)
    app.dependency_overrides[get_clock] = lambda: now  # deterministic clock
    return TestClient(app), session_db


def _auth(client, student="ada"):
    client.post("/auth/register", json={"student_id": student, "password": "pw"})
    token = client.post("/auth/login", json={"student_id": student, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(session_db, student, rows):
    conn = sqlite3.connect(str(session_db))
    for session_id, skill_id, problem_id, result, ts in rows:
        conn.execute(
            "INSERT INTO attempt_log (ts, session_id, student_id, skill_id, problem_id, check_result, xp_awarded) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, session_id, student, skill_id, problem_id, result, 0),
        )
    conn.commit()
    conn.close()


def test_lapsed_skill_is_promoted_to_front(tmp_path):
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth = _auth(client)
    # B mastered (2 DISTINCT correct problems) 5-6 days ago (lapsed); A never mastered.
    _seed(session_db, "ada", [
        ("practice:ada", "B", "b1", "correct", now - 6 * DAY),
        ("practice:ada", "B", "b2", "correct", now - 5 * DAY),
    ])
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["skill_id"] == "B"  # review-due skill promoted


def test_one_distinct_correct_is_not_promoted(tmp_path):
    # Discriminator: a single distinct correct (even lapsed) is NOT mastery -> not promoted.
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth = _auth(client)
    _seed(session_db, "ada", [("practice:ada", "B", "b1", "correct", now - 5 * DAY)])  # 1 distinct
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["id"] == "a1" and all(p["review"] is False for p in problems)


def test_same_problem_repeated_is_not_promoted(tmp_path):
    # Discriminator: replaying ONE problem correctly twice -> distinct_count 1 -> not mastery.
    # Positive control (2 DISTINCT problems DO promote) lives in
    # test_lapsed_skill_is_promoted_to_front, with the same bank/timing — this would FAIL
    # under a COUNT(*)>=2 (attempts) regression.
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth = _auth(client)
    _seed(session_db, "ada", [
        ("practice:ada", "B", "b1", "correct", now - 6 * DAY),
        ("practice:ada", "B", "b1", "correct", now - 5 * DAY),  # same problem again
    ])
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["id"] == "a1" and all(p["review"] is False for p in problems)


def test_recently_mastered_skill_is_not_promoted(tmp_path):
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth = _auth(client)
    # 2 DISTINCT corrects (passes the count gate) but RECENT -> recency keeps it not due.
    _seed(session_db, "ada", [
        ("practice:ada", "B", "b1", "correct", now - 0.2 * DAY),
        ("practice:ada", "B", "b2", "correct", now - 0.1 * DAY),
    ])
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems[0]["id"] == "a1"  # recent mastery -> not promoted -> easiest-first base


def test_review_flag_marks_due_skill_problems(tmp_path):
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth = _auth(client)
    _seed(session_db, "ada", [
        ("practice:ada", "B", "b1", "correct", now - 6 * DAY),
        ("practice:ada", "B", "b2", "correct", now - 5 * DAY),
    ])  # B mastered + lapsed
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    by_id = {p["id"]: p for p in problems}
    assert by_id["b1"]["review"] is True and by_id["b2"]["review"] is True  # due skill flagged
    assert by_id["a1"]["review"] is False  # non-due skill not flagged


def test_practice_problems_without_attempt_log_omits_review(tmp_path):
    # No SESSION_DB_PATH -> attempt_log is None -> raw public_problems(), no review key.
    # The frontend mapping defaults a missing key to false; assert the contract here.
    bank_path = tmp_path / "practice.json"
    bank_path.write_text(json.dumps(_bank([("a1", "A", 1, "1")])))
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(bank_path)})
    client = TestClient(create_app(settings))
    auth = _auth(client)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert problems and "review" not in problems[0]  # key absent; FE coerces to false


def test_review_flag_false_for_fresh_student(tmp_path):
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2")]
    client, _ = _client(tmp_path, items, now=now)
    auth = _auth(client)
    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    assert all(p["review"] is False for p in problems)  # nothing due -> key present, false


def test_per_student_isolation(tmp_path):
    now = 100 * DAY
    items = [("a1", "A", 1, "1"), ("b1", "B", 1, "2"), ("b2", "B", 2, "3")]
    client, session_db = _client(tmp_path, items, now=now)
    auth_ada = _auth(client, "ada")
    _seed(session_db, "ada", [
        ("practice:ada", "B", "b1", "correct", now - 6 * DAY),
        ("practice:ada", "B", "b2", "correct", now - 5 * DAY),
    ])  # only ada has a mastered+lapsed skill
    ada_problems = client.get("/practice/problems", headers=auth_ada).json()["problems"]
    bob_problems = client.get("/practice/problems", headers=_auth(client, "bob")).json()["problems"]
    assert ada_problems[0]["skill_id"] == "B"  # ada's due skill promoted
    assert bob_problems[0]["id"] == "a1"  # bob unaffected by ada's history
