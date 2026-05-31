from backend.app.evals import deterministic_guardrails
from backend.content_pipeline.verify import FrozenBankVerificationReport


def test_deterministic_guardrail_eval_harness_passes():
    assert deterministic_guardrails.run() == []


def test_deterministic_eval_harness_includes_content_pipeline_gate(monkeypatch):
    monkeypatch.setattr(
        deterministic_guardrails,
        "verify_frozen_gold_bank",
        lambda: FrozenBankVerificationReport(
            ok=False,
            problem_count=16,
            realization_count=48,
            template_case_count=48,
            safety_terms=[],
            schema_errors=[],
            template_errors=["lf_p01/neutral mismatch"],
            role_errors=[],
            public_leaks=[],
        ),
        raising=False,
    )

    assert deterministic_guardrails.run() == ["content_pipeline"]
