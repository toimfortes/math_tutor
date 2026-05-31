from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.evals.live_turn_smoke import run_turn_smoke
from backend.app.llm.mock_client import MockLLMClient


def test_run_turn_smoke_exercises_session_and_wrong_answer_path():
    report = run_turn_smoke(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
    )

    assert report["provider_path"] == "turn_service"
    assert report["start_problem_id"] == "lf_p01"
    assert report["turn_check_result"] in {"incorrect", "undecidable"}
    assert report["hidden_teacher_checks"] >= 1
    assert report["guardrail_fires"] == []
