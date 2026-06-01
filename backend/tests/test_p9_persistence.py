from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.domain.mastery import ProblemAttempt, SubmissionEvent
from backend.app.llm.mock_client import MockLLMClient
from backend.app.main import create_app
from backend.app.services.session_store import (
    SqliteSessionStore,
    StaleSessionError,
    deserialize_session,
    serialize_session,
)
from backend.app.services.turn import InMemoryTurnStore, SessionState, TurnService


def _state_with_history() -> SessionState:
    bank = load_gold_problem_bank()
    service = TurnService(problem_bank=bank, llm_client=MockLLMClient(), store=InMemoryTurnStore())
    start = service.start_session(student_id="stu", theme="space_logistics")
    service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")
    service.record_transfer(start.session_id, skill_id=start.public_problem.skill_id, context_key="drone_physics:word")
    return service.store.load(start.session_id)


def test_session_state_survives_serialization_round_trip():
    bank = load_gold_problem_bank()
    original = _state_with_history()

    restored = deserialize_session(serialize_session(original), bank.public_problem)

    assert restored.session_id == original.session_id
    assert restored.student_id == original.student_id
    assert restored.theme == original.theme
    assert restored.active_ref == original.active_ref
    assert [a.problem_attempt_id for a in restored.attempts] == [a.problem_attempt_id for a in original.attempts]
    assert restored.attempts[0].submissions[0].check_result == original.attempts[0].submissions[0].check_result
    assert restored.contexts_seen == original.contexts_seen
    assert restored.transfer_passed_by_skill == original.transfer_passed_by_skill
    assert restored.active_attempt_id == original.active_attempt_id
    assert restored.xp_awarded_by_attempt == original.xp_awarded_by_attempt
    assert set(restored.idempotency) == set(original.idempotency)
    # the cached turn response is rebuilt with a real PublicProblem from the bank.
    cached = restored.idempotency["t1"]
    assert cached.public_problem.ref == original.idempotency["t1"].public_problem.ref
    assert cached.public_problem.prompt


def test_sqlite_store_persists_session_across_store_instances(tmp_path):
    db = tmp_path / "sessions.db"
    bank = load_gold_problem_bank()
    state = _state_with_history()

    store = SqliteSessionStore(db, bank.public_problem)
    store.create(state)

    reopened = SqliteSessionStore(db, bank.public_problem)
    restored = reopened.load(state.session_id)
    assert restored.student_id == "stu"
    assert len(restored.attempts) == 1
    assert restored.active_ref == state.active_ref
    assert restored.active_attempt_id == state.active_attempt_id
    assert restored.xp_awarded_by_attempt == state.xp_awarded_by_attempt


def test_sqlite_store_optimistic_locking_rejects_stale_writes(tmp_path):
    db = tmp_path / "s.db"
    bank = load_gold_problem_bank()
    store = SqliteSessionStore(db, bank.public_problem)
    state = SessionState(
        session_id="s1",
        student_id="stu",
        theme="neutral",
        active_ref=RealizedProblemRef("lf_p01", "neutral"),
    )
    store.create(state)

    first = store.load("s1")
    second = store.load("s1")

    store.save(first)  # succeeds and bumps the version
    with pytest.raises(StaleSessionError):
        store.save(second)  # writes against the now-stale version


def test_turn_service_state_survives_a_fresh_service_on_the_same_db(tmp_path):
    db = tmp_path / "live.db"
    bank = load_gold_problem_bank()
    service = TurnService(
        problem_bank=bank, llm_client=MockLLMClient(), store=SqliteSessionStore(db, bank.public_problem)
    )
    start = service.start_session(student_id="stu", theme="space_logistics")
    skill_id = start.public_problem.skill_id
    first = service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")

    # a brand-new store + service on the same database file sees the saved work.
    fresh = TurnService(
        problem_bank=bank, llm_client=MockLLMClient(), store=SqliteSessionStore(db, bank.public_problem)
    )
    skill = fresh.skill_state(start.session_id, skill_id=skill_id)
    assert skill.attempts  # the earlier attempt survived the "restart"

    # the idempotency cache survived too: retrying the turn returns the cache.
    again = fresh.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")
    assert again.dialogue == first.dialogue
    assert again.public_problem.ref == first.public_problem.ref


def test_app_persists_sessions_to_the_configured_sqlite_file(tmp_path):
    settings = Settings.from_env({"SESSION_DB_PATH": str(tmp_path / "app.db")})

    first_app = TestClient(create_app(settings))
    start = first_app.post("/session/start", json={"student_id": "stu", "theme": "space_logistics"}).json()
    session_id = start["session_id"]
    skill_id = start["public_problem"]["skill_id"]
    first_app.post("/turn", json={"session_id": session_id, "idempotency_key": "t1", "answer": "(4, 3)"})

    # a freshly constructed app on the same db file still sees the session.
    second_app = TestClient(create_app(settings))
    state = second_app.get(f"/student/stu/state", params={"session_id": session_id, "skill_id": skill_id})

    assert state.status_code == 200
    assert state.json()["skill_id"] == skill_id
    assert state.json()["attempt_count"] >= 1


def test_app_defaults_to_in_memory_store_without_a_db_path():
    settings = Settings.from_env({})

    client = TestClient(create_app(settings))
    start = client.post("/session/start", json={"student_id": "stu", "theme": "neutral"}).json()

    assert start["session_id"]


def test_sqlite_store_load_missing_session_raises_key_error(tmp_path):
    bank = load_gold_problem_bank()
    store = SqliteSessionStore(tmp_path / "s.db", bank.public_problem)

    with pytest.raises(KeyError):
        store.load("does-not-exist")
