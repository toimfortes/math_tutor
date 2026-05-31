from __future__ import annotations

from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.rate_limiter import FixedWindowRateLimiter
from backend.app.services.turn import InMemoryTurnStore, TurnService


def _service(budget: FixedWindowRateLimiter | None) -> TurnService:
    return TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
        llm_budget=budget,
    )


def test_llm_budget_degrades_to_fallback_without_breaking_grading():
    service = _service(FixedWindowRateLimiter(limit=2, window_seconds=86400))

    start = service.start_session(student_id="stu", theme="space_logistics")  # consumes 1
    t1 = service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")  # consumes 2
    t2 = service.submit_turn(start.session_id, idempotency_key="t2", answer="999")  # over budget

    assert "llm_budget_exhausted" not in start.guardrail_fires
    assert "llm_budget_exhausted" not in t1.guardrail_fires
    assert "llm_budget_exhausted" in t2.guardrail_fires
    # a budget degrade is not an error, and code-owned grading still runs.
    assert "llm_error" not in t2.guardrail_fires
    assert t2.check_result is not None


def test_llm_budget_is_per_student():
    service = _service(FixedWindowRateLimiter(limit=1, window_seconds=86400))

    alice = service.start_session(student_id="alice", theme="space_logistics")  # alice consumes 1
    alice_turn = service.submit_turn(alice.session_id, idempotency_key="t1", answer="999")  # alice over budget
    bob = service.start_session(student_id="bob", theme="space_logistics")  # bob still has budget

    assert "llm_budget_exhausted" in alice_turn.guardrail_fires
    assert "llm_budget_exhausted" not in bob.guardrail_fires


def test_no_budget_means_no_degradation():
    service = _service(None)
    start = service.start_session(student_id="stu", theme="space_logistics")

    for index in range(5):
        response = service.submit_turn(start.session_id, idempotency_key=f"t{index}", answer="999")
        assert "llm_budget_exhausted" not in response.guardrail_fires
