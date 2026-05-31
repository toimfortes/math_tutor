from backend.app.evals.deterministic_guardrails import run


def test_deterministic_guardrail_eval_harness_passes():
    assert run() == []
