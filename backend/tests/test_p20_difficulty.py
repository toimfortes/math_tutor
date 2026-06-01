from __future__ import annotations

import pytest

from backend.content_pipeline.calibration import Calibrated, calibrate
from backend.content_pipeline.difficulty import (
    DIFFICULTY_MAX,
    DIFFICULTY_MIN,
    band_to_logit,
    difficulty_band,
    heuristic_difficulty,
)


# --- heuristic prior ------------------------------------------------------

def test_heuristic_difficulty_always_in_logit_range():
    for skill, kind, params in [
        ("lin_slope_two_points", "slope_two_points", {"x1": 1, "y1": 3, "x2": 4, "y2": 9}),
        ("lin_equation_slope_intercept", "slope_intercept_equation", {"m": 9, "b": -8, "var": "x"}),
        ("coord_plane_basics", "coordinate", {"x": 4, "y": 3}),
    ]:
        score = heuristic_difficulty(skill, kind, params)
        assert DIFFICULTY_MIN <= score <= DIFFICULTY_MAX


def test_heuristic_difficulty_is_monotonic_in_features():
    # a fractional-slope, negative, large-coefficient item is harder than a small integer one
    easy = heuristic_difficulty("lin_slope_two_points", "slope_two_points", {"x1": 0, "y1": 0, "x2": 1, "y2": 2})
    hard = heuristic_difficulty("lin_slope_two_points", "slope_two_points", {"x1": 2, "y1": 3, "x2": 8, "y2": 6})
    assert hard > easy  # 3/6 = 1/2 fractional slope, bigger coords

    # multi-step equation kind is harder than single-step evaluate for similar coefficients
    evaluate = heuristic_difficulty("lin_evaluate", "evaluate_y", {"m": 2, "b": 1, "x": 3})
    equation = heuristic_difficulty("lin_equation_slope_intercept", "slope_intercept_equation", {"m": 2, "b": 1, "var": "x"})
    assert equation > evaluate


def test_heuristic_difficulty_is_deterministic():
    a = heuristic_difficulty("lin_evaluate", "evaluate_y", {"m": 3, "b": 2, "x": 4})
    b = heuristic_difficulty("lin_evaluate", "evaluate_y", {"m": 3, "b": 2, "x": 4})
    assert a == b


def test_difficulty_band_orders_and_clamps():
    assert difficulty_band(DIFFICULTY_MIN) == 1
    assert difficulty_band(DIFFICULTY_MAX) == 5
    assert difficulty_band(0.0) == 3
    assert difficulty_band(-100.0) == 1 and difficulty_band(100.0) == 5
    assert difficulty_band(-2.0) < difficulty_band(0.0) < difficulty_band(2.0)


def test_band_to_logit_round_trips_order_and_stays_in_range():
    logits = [band_to_logit(b) for b in (1, 2, 3, 4, 5)]
    assert logits == sorted(logits)  # ordered
    assert all(DIFFICULTY_MIN <= x <= DIFFICULTY_MAX for x in logits)
    assert band_to_logit(3) == 0.0


# --- empirical-Bayes calibrator ------------------------------------------

def test_zero_attempts_returns_prior_uncalibrated():
    result = calibrate([], {"item": 1.0})
    assert result["item"] == Calibrated(difficulty=1.0, responses=0, prior=1.0, calibrated=False, undecidable=0)


def test_many_wrong_raises_difficulty_many_right_lowers_it():
    attempts = [("hard", "incorrect")] * 20 + [("easy", "correct")] * 20
    result = calibrate(attempts, {"hard": 0.0, "easy": 0.0})
    assert result["hard"].difficulty > 0.0  # harder than neutral prior
    assert result["easy"].difficulty < 0.0
    assert result["hard"].responses == 20 and result["hard"].calibrated is True


def test_prior_washes_out_as_responses_grow():
    # a hard prior (2.0) but a 50% empirical pass rate over many responses -> near 0
    attempts = [("x", "correct")] * 100 + [("x", "incorrect")] * 100
    result = calibrate(attempts, {"x": 2.0})
    assert abs(result["x"].difficulty) < 0.3  # prior 2.0 washed out toward empirical ~0


def test_calibration_is_order_independent():
    import random

    attempts = [("a", "correct"), ("a", "incorrect"), ("b", "incorrect"), ("a", "correct"), ("b", "incorrect")]
    shuffled = list(attempts)
    random.Random(0).shuffle(shuffled)
    assert calibrate(attempts, {"a": 0.0, "b": 0.0}) == calibrate(shuffled, {"a": 0.0, "b": 0.0})


def test_undecidable_is_excluded_from_passrate_but_counted():
    result = calibrate([("x", "correct"), ("x", "undecidable"), ("x", "undecidable")], {"x": 0.0})
    assert result["x"].responses == 1  # only the decidable attempt
    assert result["x"].undecidable == 2


def test_prior_strength_must_be_positive_and_finite():
    with pytest.raises(ValueError):
        calibrate([("x", "correct")], {"x": 0.0}, prior_strength=0)
    with pytest.raises(ValueError):
        calibrate([("x", "correct")], {"x": 0.0}, prior_strength=float("inf"))


def test_unknown_or_none_outcomes_are_skipped_not_counted_wrong():
    result = calibrate([("x", "correct"), ("x", None), ("x", "bogus")], {"x": 0.0})
    assert result["x"].responses == 1  # only the "correct" attempt is decidable
    assert result["x"].undecidable == 2


def test_non_finite_prior_is_treated_as_neutral():
    result = calibrate([], {"x": float("nan")})
    assert result["x"].prior == 0.0 and result["x"].difficulty == 0.0
