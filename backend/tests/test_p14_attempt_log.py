from __future__ import annotations

from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.attempt_log import SqliteAttemptLog
from backend.app.services.turn import InMemoryTurnStore, TurnService


def test_sqlite_attempt_log_appends_entries(tmp_path):
    log = SqliteAttemptLog(tmp_path / "a.db", clock=lambda: 100.0)

    log.record(session_id="s1", student_id="stu", skill_id="sk", problem_id="lf_p01", check_result="correct", xp_awarded=10)
    log.record(session_id="s1", student_id="stu", skill_id="sk", problem_id="lf_p02", check_result="incorrect", xp_awarded=0)

    entries = log.entries("s1")
    assert len(entries) == 2
    assert entries[0]["check_result"] == "correct"
    assert entries[0]["ts"] == 100.0
    assert entries[1]["problem_id"] == "lf_p02"
    assert entries[1]["xp_awarded"] == 0


def test_attempt_log_is_durable_across_reopen(tmp_path):
    db = tmp_path / "a.db"
    SqliteAttemptLog(db, clock=lambda: 1.0).record(
        session_id="s1", student_id="stu", skill_id="sk", problem_id="p", check_result="correct", xp_awarded=5
    )

    assert len(SqliteAttemptLog(db).entries("s1")) == 1


def test_turn_service_logs_each_submitted_turn_once(tmp_path):
    log = SqliteAttemptLog(tmp_path / "a.db", clock=lambda: 7.0)
    service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
        attempt_log=log,
    )
    start = service.start_session(student_id="stu", theme="space_logistics")

    service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")
    service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")  # idempotent retry

    entries = log.entries(start.session_id)
    assert len(entries) == 1  # the retry is not double-logged
    assert entries[0]["check_result"] == "correct"
    assert entries[0]["student_id"] == "stu"
