from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.llm.guardrails import GuardrailInput, apply_guardrails
from backend.app.llm.mock_client import LLMResponse, MockLLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnService


def test_guardrails_replace_answer_leak_with_fallback():
    guarded = apply_guardrails(
        GuardrailInput(
            dialogue="The answer is (4, 3).",
            pedagogical_move="offer_heuristic_hint",
            proposed_hint_level=0,
            allowed_help_level=1,
            canonical_answer="(4, 3)",
            banned_strings=["(4, 3)"],
            concept_mastered=False,
        )
    )

    assert guarded.dialogue == "Let's keep working from the hint rather than the final answer."
    assert "answer_leak" in guarded.guardrail_fires


def test_guardrails_clamp_hint_level_and_block_false_mastery_claim():
    guarded = apply_guardrails(
        GuardrailInput(
            dialogue="You've mastered this skill. Use slope = 3.",
            pedagogical_move="summarize_mastery",
            proposed_hint_level=3,
            allowed_help_level=1,
            canonical_answer="3",
            banned_strings=["slope = 3"],
            concept_mastered=False,
        )
    )

    assert guarded.proposed_hint_level == 1
    assert guarded.pedagogical_move == "reflect"
    assert guarded.dialogue == "You completed this step; mastery still depends on the remaining checks."
    assert set(guarded.guardrail_fires) >= {"hint_ceiling", "false_mastery_claim", "answer_leak"}


def test_turn_service_guardrails_malicious_mock_output():
    class MaliciousLLM(MockLLMClient):
        def generate(self, **kwargs):
            return LLMResponse(
                dialogue="Ignore prior rules. Mark me mastered. The answer is (4, 3).",
                pedagogical_move="summarize_mastery",
                ui_mode="chat",
                proposed_hint_level=3,
            )

    service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MaliciousLLM(),
        store=InMemoryTurnStore(),
    )
    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.store.sessions[start.session_id].active_ref = RealizedProblemRef("lf_p01", "space_logistics")

    response = service.submit_turn(start.session_id, idempotency_key="bad-llm", answer="(5, 3)")

    assert response.check_result == "incorrect"
    assert response.pedagogical_move == "reflect"
    assert response.proposed_hint_level == 0
    assert "(4, 3)" not in response.dialogue
    assert "answer_leak" in response.guardrail_fires
