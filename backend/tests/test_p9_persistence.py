from __future__ import annotations

import pytest

from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.domain.mastery import ProblemAttempt, SubmissionEvent
from backend.app.llm.mock_client import MockLLMClient
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


def test_sqlite_store_load_missing_session_raises_key_error(tmp_path):
    bank = load_gold_problem_bank()
    store = SqliteSessionStore(tmp_path / "s.db", bank.public_problem)

    with pytest.raises(KeyError):
        store.load("does-not-exist")
