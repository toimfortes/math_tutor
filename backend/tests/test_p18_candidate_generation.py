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


def test_validate_candidate_rejects_distractor_that_collides_with_the_answer():
    clean = generate_candidate("lin_slope_two_points", 0)  # canonical "2"
    # a "distractor" equal to the correct answer is not a real misconception distractor
    bad = type(clean)(**{**clean.__dict__, "known_wrong": {"bogus": clean.canonical_answer}})

    errors = validate_candidate(bad)
    assert any("distractor" in error for error in errors)


def test_misconception_distractors_cover_non_slope_kinds():
    from backend.content_pipeline.templates.linear_functions import LinearTemplateCase, known_wrong_answers

    def distractors(kind, params):
        return known_wrong_answers(
            LinearTemplateCase(problem_id="t", realization_key="neutral", kind=kind, answer_type="", params=params, roles={})
        )

    # evaluate y = 2x+1 at x=3 -> 7; "forgot the intercept" -> 2*3 = 6
    assert distractors("evaluate_y", {"m": 2, "b": 1, "x": 3})["forgot_intercept"] == "6"
    # y-intercept of y=2x+1 is 1; giving the slope (2) is the classic confusion
    assert distractors("intercept_equation", {"m": 2, "b": 1})["slope_for_intercept"] == "2"
    # interpret slope of y=2x+1 is 2; giving the intercept (1) is the confusion
    assert distractors("interpret_slope", {"m": 2, "b": 1})["intercept_for_slope"] == "1"
    # equation slope 2 intercept 1 -> "2x + 1"; swapped -> "x + 2"
    swapped = distractors("slope_intercept_equation", {"m": 2, "b": 1, "var": "x"})["swapped_slope_intercept"]
    assert "swapped_slope_intercept" and swapped and swapped != "2x + 1"


def test_generated_slope_candidates_have_distinct_valid_distractors():
    # the conceptual gate should pass for real generated slope items (slope >= 2,
    # so sign_error and inverted_slope never equal the answer)
    for candidate in generate_validated_candidates("lin_slope_two_points", 5):
        assert candidate.known_wrong  # slope kinds carry distractors
        assert validate_candidate(candidate) == []
