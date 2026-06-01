"""Deterministic candidate problem generation from staged source alignment.

For skills with a deterministic template, this generates parametric problem
candidates and validates each through the same gates the runtime bank must
satisfy: the answer is solved deterministically and round-trips through the
code-owned checker, the prompt passes the content safety scan, and the answer
is not leaked in the prompt. Generation is deterministic (indexed, no RNG) so
candidates are reproducible. Candidates are NOT promoted to the runtime bank;
that remains a separate, gated step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.app.domain.checker import check_answer
from backend.content_pipeline.safety import find_unsafe_terms
from backend.content_pipeline.templates.linear_functions import (
    LinearTemplateCase,
    known_wrong_answers,
    solve_case,
)


@dataclass(frozen=True)
class GeneratedCandidate:
    skill_id: str
    kind: str
    answer_type: str
    checker: str
    params: dict
    prompt: str
    canonical_answer: str
    known_wrong: dict
    hint_scaffold: dict


@dataclass(frozen=True)
class GeneratorSpec:
    skill_id: str
    kind: str
    answer_type: str
    checker: str
    make_params: Callable[[int], dict]
    make_prompt: Callable[[dict], str]
    hint_scaffold: dict


def _slope_two_points_params(index: int) -> dict:
    slope = index + 2
    x1, y1, x2 = 1, 3, 4
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y1 + slope * (x2 - x1)}


def _slope_two_points_prompt(params: dict) -> str:
    return (
        f"Find the slope of the line through "
        f"({params['x1']}, {params['y1']}) and ({params['x2']}, {params['y2']})."
    )


def _evaluate_params(index: int) -> dict:
    return {"m": index + 2, "b": index + 1, "x": index + 3}


def _evaluate_prompt(params: dict) -> str:
    return f"For y = {params['m']}x + {params['b']}, find y when x = {params['x']}."


def _y_intercept_params(index: int) -> dict:
    return {"m": index + 2, "b": index + 1}


def _y_intercept_prompt(params: dict) -> str:
    return f"What is the y-intercept of y = {params['m']}x + {params['b']}?"


def _interpret_params(index: int) -> dict:
    return {"m": index + 2, "b": index + 1}


def _interpret_prompt(params: dict) -> str:
    return (
        f"A quantity is modelled by y = {params['m']}x + {params['b']}. "
        f"By how much does y change for each unit increase in x?"
    )


def _rate_params(index: int) -> dict:
    rate = index + 3
    x1, y1, x2 = 0, 10, 2
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y1 + rate * (x2 - x1)}


def _rate_prompt(params: dict) -> str:
    return (
        f"A quantity is {params['y1']} at x = {params['x1']} and {params['y2']} at x = {params['x2']}. "
        f"What is its constant rate of change per unit x?"
    )


_SLOPE_SCAFFOLD = {
    "max_safe_hint_level": 2,
    "level_0": "Find how much each coordinate changes between the two points.",
    "level_1": "Slope is the change in y divided by the change in x.",
    "level_2": "Write the vertical change over the horizontal change and simplify.",
    "level_3": None,
}

_EVALUATE_SCAFFOLD = {
    "max_safe_hint_level": 2,
    "level_0": "Substitute the given x value into the equation.",
    "level_1": "Multiply the slope by x, then add the intercept.",
    "level_2": "Compute m times x first, then add b.",
    "level_3": None,
}

_Y_INTERCEPT_SCAFFOLD = {
    "max_safe_hint_level": 2,
    "level_0": "The y-intercept is the y-value when x = 0.",
    "level_1": "In y = mx + b, the intercept is the constant term.",
    "level_2": "Read off the value added after the x term.",
    "level_3": None,
}

_INTERPRET_SCAFFOLD = {
    "max_safe_hint_level": 2,
    "level_0": "Think about what the coefficient of x represents.",
    "level_1": "The rate of change is the slope of the line.",
    "level_2": "In y = mx + b, y changes by m for each unit of x.",
    "level_3": None,
}

_RATE_SCAFFOLD = {
    "max_safe_hint_level": 2,
    "level_0": "Compare how much the quantity changes against how much x changes.",
    "level_1": "Rate of change is change in the quantity divided by change in x.",
    "level_2": "Divide the difference in values by the difference in x.",
    "level_3": None,
}


GENERATORS: dict[str, GeneratorSpec] = {
    "lin_slope_two_points": GeneratorSpec(
        skill_id="lin_slope_two_points",
        kind="slope_two_points",
        answer_type="numeric",
        checker="numeric",
        make_params=_slope_two_points_params,
        make_prompt=_slope_two_points_prompt,
        hint_scaffold=_SLOPE_SCAFFOLD,
    ),
    "lin_evaluate": GeneratorSpec(
        skill_id="lin_evaluate",
        kind="evaluate_y",
        answer_type="numeric",
        checker="numeric",
        make_params=_evaluate_params,
        make_prompt=_evaluate_prompt,
        hint_scaffold=_EVALUATE_SCAFFOLD,
    ),
    "lin_y_intercept": GeneratorSpec(
        skill_id="lin_y_intercept",
        kind="intercept_equation",
        answer_type="numeric",
        checker="numeric",
        make_params=_y_intercept_params,
        make_prompt=_y_intercept_prompt,
        hint_scaffold=_Y_INTERCEPT_SCAFFOLD,
    ),
    "lin_interpret_meaning": GeneratorSpec(
        skill_id="lin_interpret_meaning",
        kind="interpret_slope",
        answer_type="numeric",
        checker="numeric",
        make_params=_interpret_params,
        make_prompt=_interpret_prompt,
        hint_scaffold=_INTERPRET_SCAFFOLD,
    ),
    "lin_rate_of_change": GeneratorSpec(
        skill_id="lin_rate_of_change",
        kind="rate_between_points",
        answer_type="numeric",
        checker="numeric",
        make_params=_rate_params,
        make_prompt=_rate_prompt,
        hint_scaffold=_RATE_SCAFFOLD,
    ),
}


def generate_candidate(skill_id: str, index: int) -> GeneratedCandidate:
    spec = GENERATORS[skill_id]
    params = spec.make_params(index)
    template_case = LinearTemplateCase(
        problem_id=f"cand_{skill_id}_{index}",
        realization_key="neutral",
        kind=spec.kind,
        answer_type=spec.answer_type,
        params=params,
        roles={},
    )
    return GeneratedCandidate(
        skill_id=skill_id,
        kind=spec.kind,
        answer_type=spec.answer_type,
        checker=spec.checker,
        params=params,
        prompt=spec.make_prompt(params),
        canonical_answer=solve_case(template_case),
        known_wrong=known_wrong_answers(template_case),
        hint_scaffold=spec.hint_scaffold,
    )


def validate_candidate(candidate: GeneratedCandidate) -> list[str]:
    """Run the runtime gates against a candidate; return a list of failures."""
    errors: list[str] = []

    # Determinism: the canonical answer must be exactly what the deterministic
    # solver produces for these params (rejects any hand-tampered answer), and
    # it must round-trip through the code-owned checker.
    solved = solve_case(
        LinearTemplateCase(
            problem_id="_validate",
            realization_key="neutral",
            kind=candidate.kind,
            answer_type=candidate.answer_type,
            params=candidate.params,
            roles={},
        )
    )
    round_trip = check_answer(
        candidate.canonical_answer, candidate.canonical_answer, answer_type=candidate.answer_type
    )
    if solved != candidate.canonical_answer or round_trip.check_result != "correct":
        errors.append("canonical answer is not the deterministic solver result")

    unsafe = find_unsafe_terms(candidate.prompt)
    if unsafe:
        errors.append(f"unsafe terms in prompt: {', '.join(unsafe)}")

    if f"the answer is {candidate.canonical_answer}".lower() in candidate.prompt.lower():
        errors.append("prompt leaks the canonical answer")

    return errors


def validate_stored_candidate(
    *, skill_id: str, kind: str, answer_type: str, params: dict, prompt: str, canonical_answer: str
) -> list[str]:
    """Re-run the gates against a candidate already persisted in the DB.

    Used at promotion time to re-verify a stored candidate (re-derive its answer
    from params, re-check safety and leak) before it is approved.
    """
    return validate_candidate(
        GeneratedCandidate(
            skill_id=skill_id,
            kind=kind,
            answer_type=answer_type,
            checker="",
            params=params,
            prompt=prompt,
            canonical_answer=canonical_answer,
            known_wrong={},
            hint_scaffold={},
        )
    )


def generate_validated_candidates(skill_id: str, count: int) -> list[GeneratedCandidate]:
    candidates: list[GeneratedCandidate] = []
    index = 0
    while len(candidates) < count:
        candidate = generate_candidate(skill_id, index)
        if not validate_candidate(candidate):
            candidates.append(candidate)
        index += 1
        if index > count * 100:  # safety backstop against a pathological generator
            break
    return candidates
