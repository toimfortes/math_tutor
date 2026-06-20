"""Heuristic (a-priori) item difficulty from generation parameters.

Difficulty is on a logit scale (higher = harder), hard-clamped to [-3, 3] so it
can seed the empirical-Bayes calibrator without saturating the sigmoid. The
generation parameters are exactly the item covariates explanatory IRT (LLTM)
uses; this is a feature-based prior, refined later by `calibration.calibrate`.
"""

from __future__ import annotations

from typing import Any

from backend.content_pipeline.templates.linear_functions import LinearTemplateCase, solve_case

DIFFICULTY_MIN = -3.0
DIFFICULTY_MAX = 3.0

# Foundational/prerequisite skills are easier; equation-writing is multi-step/harder.
_SKILL_BASE: dict[str, float] = {
    "coord_plane_basics": -1.5,
    "lin_y_intercept": -1.0,
    "lin_rate_of_change": -0.5,
    "lin_evaluate": -0.5,
    "lin_interpret_meaning": -0.5,
    "lin_slope_two_points": 0.0,
    "lin_slope_from_graph": 0.0,
    "lin_equation_slope_intercept": 1.0,
}

_MULTI_STEP_KINDS = {"slope_intercept_equation", "equation_two_points", "equation_point_slope", "solve_for_x"}

# Evenly spaced band centres so gold (1-5) and generated items share one scale
# without compressing into the sigmoid tails.
_BAND_CENTRES = {1: -2.4, 2: -1.2, 3: 0.0, 4: 1.2, 5: 2.4}


def _clamp(value: float) -> float:
    return max(DIFFICULTY_MIN, min(DIFFICULTY_MAX, value))


def heuristic_difficulty(skill_id: str, kind: str, params: dict[str, Any]) -> float:
    score = _SKILL_BASE.get(skill_id, 0.0)

    numbers = [value for value in params.values() if isinstance(value, (int, float))]
    if numbers:
        score += min(max(abs(value) for value in numbers) / 20.0, 0.8)  # bigger numbers slightly harder
    if any(isinstance(value, (int, float)) and value < 0 for value in numbers):
        score += 0.5  # negative values

    # Fractional canonical answers are harder; derive deterministically from the solver.
    answer = solve_case(
        LinearTemplateCase(problem_id="_difficulty", realization_key="neutral", kind=kind, answer_type="", params=params, roles={})
    )
    if "/" in answer:
        score += 0.6

    if kind in _MULTI_STEP_KINDS:
        score += 0.6

    return _clamp(score)


def difficulty_band(score: float) -> int:
    """Map a logit difficulty to an integer 1-5 band (display only)."""
    clamped = _clamp(score)
    # boundaries midway between band centres
    for band in (1, 2, 3, 4):
        if clamped < (_BAND_CENTRES[band] + _BAND_CENTRES[band + 1]) / 2:
            return band
    return 5


def band_to_logit(band: int) -> float:
    """Inverse of difficulty_band: an authored 1-5 band -> a logit prior."""
    return _BAND_CENTRES[max(1, min(5, band))]
