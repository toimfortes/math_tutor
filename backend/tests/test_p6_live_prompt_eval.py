from backend.app.evals.live_prompt_eval import LiveEvalCase, LiveEvalFailure, evaluate_response, run_live_eval_cases
from backend.app.llm.types import LLMResponse


class StaticClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_evaluate_response_fails_on_answer_leak_even_when_guardrail_catches_it():
    case = LiveEvalCase(
        name="answer_leak",
        check_result="incorrect",
        allowed_help_level=1,
        canonical_answer="7",
        banned_strings=("7",),
    )
    response = LLMResponse(
        dialogue="The answer is 7.",
        pedagogical_move="offer_heuristic_hint",
        ui_mode="chat",
        proposed_hint_level=1,
        teacher_check={
            "student_error_tag": "unknown",
            "next_scaffold_id": "level_1",
            "leak_risk": "none",
            "uses_only_authored_scaffold": True,
            "chosen_pedagogical_move": "offer_heuristic_hint",
        },
    )

    failures = evaluate_response(case, response)

    assert failures == (LiveEvalFailure(case_name="answer_leak", reason="answer_leak"),)


def test_evaluate_response_fails_on_over_help_and_bad_teacher_check():
    case = LiveEvalCase(
        name="over_help",
        check_result="incorrect",
        allowed_help_level=0,
        canonical_answer="3",
    )
    response = LLMResponse(
        dialogue="Try the next step.",
        pedagogical_move="offer_heuristic_hint",
        ui_mode="chat",
        proposed_hint_level=2,
        teacher_check={
            "student_error_tag": "unknown",
            "next_scaffold_id": "level_2",
            "leak_risk": "possible",
            "uses_only_authored_scaffold": True,
            "chosen_pedagogical_move": "offer_heuristic_hint",
        },
    )

    failures = evaluate_response(case, response)

    assert LiveEvalFailure(case_name="over_help", reason="hint_ceiling") in failures
    assert LiveEvalFailure(case_name="over_help", reason="teacher_check_leak_risk") in failures


def test_run_live_eval_cases_passes_context_and_sums_usage():
    cases = (
        LiveEvalCase(
            name="safe_hint",
            check_result="incorrect",
            allowed_help_level=1,
            canonical_answer="7",
            context={"student_message": "I think it is 2."},
        ),
    )
    client = StaticClient(
        [
            LLMResponse(
                dialogue="Look at what the rate means before choosing a value.",
                pedagogical_move="offer_heuristic_hint",
                ui_mode="chat",
                proposed_hint_level=1,
                teacher_check={
                    "student_error_tag": "unknown",
                    "next_scaffold_id": "level_1",
                    "leak_risk": "none",
                    "uses_only_authored_scaffold": True,
                    "chosen_pedagogical_move": "offer_heuristic_hint",
                },
                usage_metadata={"totalTokenCount": 42},
            )
        ]
    )

    report = run_live_eval_cases(client, cases)

    assert report.failures == ()
    assert report.total_tokens == 42
    assert client.calls[0]["context"] == {"student_message": "I think it is 2."}
