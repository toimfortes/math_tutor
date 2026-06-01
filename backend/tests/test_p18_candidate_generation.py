from __future__ import annotations

from backend.content_pipeline.candidate_generation import (
    GENERATORS,
    generate_candidate,
    generate_validated_candidates,
    validate_candidate,
)


def test_slope_two_points_candidate_is_solved_deterministically():
    first = generate_candidate("lin_slope_two_points", 0)
    again = generate_candidate("lin_slope_two_points", 0)

    assert first == again  # deterministic: same index -> same candidate
    # index 0: slope target 2 through (1, 3) and (4, 9) -> 6/3 = 2
    assert first.canonical_answer == "2"
    assert first.prompt == "Find the slope of the line through (1, 3) and (4, 9)."


def test_evaluate_candidate_solves_correctly():
    candidate = generate_candidate("lin_evaluate", 0)
    # index 0: y = 2x + 1 at x = 3 -> 7
    assert candidate.canonical_answer == "7"
    assert "find y when x = 3" in candidate.prompt


def test_generated_candidates_pass_the_gates_and_vary():
    for skill_id in GENERATORS:
        candidates = generate_validated_candidates(skill_id, 5)
        assert len(candidates) == 5  # all five pass determinism + safety + leak gates
        prompts = {c.prompt for c in candidates}
        assert len(prompts) == 5  # parametrically distinct
        for candidate in candidates:
            assert validate_candidate(candidate) == []


def test_validate_candidate_rejects_unsafe_prompt():
    clean = generate_candidate("lin_evaluate", 1)
    unsafe = type(clean)(**{**clean.__dict__, "prompt": clean.prompt + " on the battle front"})

    errors = validate_candidate(unsafe)
    assert any("unsafe" in error for error in errors)


def test_validate_candidate_rejects_non_round_tripping_answer():
    clean = generate_candidate("lin_slope_two_points", 2)
    broken = type(clean)(**{**clean.__dict__, "canonical_answer": "not-a-number"})

    assert validate_candidate(broken)  # determinism gate fails
