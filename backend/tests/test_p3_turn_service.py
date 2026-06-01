from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.llm.types import LLMResponse
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnService


def build_service() -> TurnService:
    return TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
    )


class FailingLLMClient:
    def generate(self, **kwargs):
        raise RuntimeError("provider timeout")


def test_session_start_returns_server_selected_problem():
    service = build_service()

    response = service.start_session(student_id="student-1", theme="space_logistics")

    assert response.session_id
    assert response.public_problem.ref.realization_key == "space_logistics"
    assert response.public_problem.prompt
    assert response.check_result is None
    assert response.dialogue


def test_turn_submission_uses_code_owned_correctness_and_schedules_next_problem():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    response = service.submit_turn(
        session_id=start.session_id,
        idempotency_key="turn-1",
        answer="(4, 3)",
    )

    assert response.check_result == "correct"
    assert response.xp_awarded == 8
    assert response.public_problem.ref != start.public_problem.ref
    assert response.public_problem.ref.realization_key == "space_logistics"
    assert response.pedagogical_move == "present_next_problem"


def test_turn_submission_is_idempotent_for_same_key():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    first = service.submit_turn(start.session_id, idempotency_key="same-key", answer="(4, 3)")
    replay = service.submit_turn(start.session_id, idempotency_key="same-key", answer="wrong")

    assert replay == first
    assert len(service.store.sessions[start.session_id].attempts) == 1


def test_retries_on_same_problem_are_grouped_under_one_attempt():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    wrong = service.submit_turn(start.session_id, idempotency_key="wrong-point", answer="(5, 3)")
    correct = service.submit_turn(start.session_id, idempotency_key="correct-point", answer="(4, 3)")
    state = service.store.sessions[start.session_id]

    assert wrong.check_result == "incorrect"
    assert wrong.xp_awarded == 1
    assert correct.check_result == "correct"
    assert correct.xp_awarded == 7
    assert len(state.attempts) == 1
    assert [submission.check_result for submission in state.attempts[0].submissions] == ["incorrect", "correct"]
    assert state.attempts[0].submissions[1].self_correction is True


def test_wrong_answer_uses_diagnostic_tag_and_does_not_advance_problem():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.store.sessions[start.session_id].active_ref = RealizedProblemRef("lf_p04", "neutral")

    response = service.submit_turn(
        start.session_id,
        idempotency_key="wrong-slope",
        answer="1/3",
    )

    assert response.check_result == "incorrect"
    assert response.diagnostic.student_error_tag == "inverted_slope"
    assert response.public_problem.ref == RealizedProblemRef("lf_p04", "neutral")
    assert response.pedagogical_move == "rectify_error"


def test_wrong_answer_diagnostics_are_template_backed_across_rate_problems():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    cases = [
        (RealizedProblemRef("lf_p03", "drone_physics"), "10", "sign_error"),
        (RealizedProblemRef("lf_p06", "neutral"), "10", "sign_error"),
        (RealizedProblemRef("lf_p07", "space_logistics"), "1/2", "inverted_slope"),
    ]

    for index, (ref, answer, expected_tag) in enumerate(cases):
        service.store.sessions[start.session_id].active_ref = ref
        response = service.submit_turn(
            start.session_id,
            idempotency_key=f"known-wrong-{index}",
            answer=answer,
        )

        assert response.check_result == "incorrect"
        assert response.diagnostic.student_error_tag == expected_tag
        assert response.diagnostic.confidence == "high"
        assert response.pedagogical_move == "rectify_error"
        assert response.public_problem.ref == ref


def test_unknown_wrong_answer_stays_low_confidence():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.store.sessions[start.session_id].active_ref = RealizedProblemRef("lf_p09", "neutral")

    response = service.submit_turn(start.session_id, idempotency_key="unknown-wrong", answer="8")

    assert response.check_result == "incorrect"
    assert response.diagnostic.student_error_tag == "unknown"
    assert response.diagnostic.confidence == "low"


def test_turn_service_passes_public_context_without_private_answer_to_llm():
    class RecordingLLM(MockLLMClient):
        def __init__(self):
            self.calls = []

        def generate(self, **kwargs):
            self.calls.append(kwargs)
            return LLMResponse(
                dialogue="Here is the next problem.",
                pedagogical_move="present_next_problem" if kwargs["presenting_next"] else "offer_heuristic_hint",
                ui_mode="chat",
                proposed_hint_level=0,
                teacher_check={
                    "student_error_tag": "unknown",
                    "next_scaffold_id": "level_0",
                    "leak_risk": "none",
                    "uses_only_authored_scaffold": True,
                    "chosen_pedagogical_move": "present_next_problem"
                    if kwargs["presenting_next"]
                    else "offer_heuristic_hint",
                },
            )

    llm = RecordingLLM()
    service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=llm,
        store=InMemoryTurnStore(),
    )

    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.submit_turn(start.session_id, idempotency_key="wrong", answer="not parseable")

    start_context = llm.calls[0]["context"]
    turn_context = llm.calls[1]["context"]
    assert start_context["public_problem"]["prompt"] == start.public_problem.prompt
    assert turn_context["public_problem"]["prompt"] == start.public_problem.prompt
    assert "canonical_answer" not in str(start_context)
    assert "canonical_answer" not in str(turn_context)
    assert "private_problem" not in str(turn_context)


def test_session_start_degrades_safely_when_llm_fails():
    service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=FailingLLMClient(),
        store=InMemoryTurnStore(),
    )

    response = service.start_session(student_id="student-1", theme="space_logistics")

    assert response.public_problem.prompt
    assert response.pedagogical_move == "present_next_problem"
    assert response.check_result is None
    assert response.xp_awarded == 0
    assert "llm_error" in response.guardrail_fires
    assert "answer" not in response.dialogue.lower()


def test_submit_turn_preserves_code_owned_result_when_llm_fails():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.llm_client = FailingLLMClient()

    response = service.submit_turn(start.session_id, idempotency_key="turn-llm-fail", answer="(4, 3)")

    assert response.check_result == "correct"
    assert response.xp_awarded == 8
    assert response.public_problem.ref != start.public_problem.ref
    assert response.pedagogical_move == "present_next_problem"
    assert "llm_error" in response.guardrail_fires
    assert service.submit_turn(start.session_id, idempotency_key="turn-llm-fail", answer="wrong") == response
