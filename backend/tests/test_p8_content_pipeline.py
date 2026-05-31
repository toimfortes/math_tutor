from __future__ import annotations

from backend.app.content.seed_loader import load_gold_problem_bank
from backend.content_pipeline.templates.linear_functions import (
    LINEAR_FUNCTION_TEMPLATE_CASES,
    known_wrong_answers,
    solve_case,
)
from backend.content_pipeline.verify import verify_frozen_gold_bank


def test_templates_reproduce_every_gold_realization_answer():
    bank = load_gold_problem_bank()
    cases_by_ref = {case.ref: case for case in LINEAR_FUNCTION_TEMPLATE_CASES}

    assert set(cases_by_ref) == set(bank.public_refs())
    for ref, case in cases_by_ref.items():
        assert solve_case(case) == bank.private_problem(ref).canonical_answer


def test_templates_carry_role_metadata_and_diagnostic_distractors():
    slope_case = next(
        case
        for case in LINEAR_FUNCTION_TEMPLATE_CASES
        if case.problem_id == "lf_p04" and case.realization_key == "neutral"
    )

    assert slope_case.roles["x1"] == "first input"
    assert slope_case.roles["y2"] == "second output"
    assert known_wrong_answers(slope_case)["inverted_slope"] == "1/3"
    assert known_wrong_answers(slope_case)["sign_error"] == "-3"


def test_frozen_gold_bank_verifier_runs_deterministic_ci_checks():
    report = verify_frozen_gold_bank()

    assert report.ok
    assert report.problem_count == 16
    assert report.realization_count == 48
    assert report.template_case_count == 48
    assert report.safety_terms == []
    assert report.public_leaks == []
