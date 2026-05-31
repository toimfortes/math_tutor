from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from backend.app.content.seed_loader import RealizedProblemRef


@dataclass(frozen=True)
class LinearTemplateCase:
    problem_id: str
    realization_key: str
    kind: str
    answer_type: str
    params: dict[str, Any]
    roles: dict[str, str]

    @property
    def ref(self) -> RealizedProblemRef:
        return RealizedProblemRef(self.problem_id, self.realization_key)


COMMON_REALIZATIONS = ("neutral", "space_logistics", "drone_physics")


def case(
    problem_id: str,
    realization_key: str,
    kind: str,
    answer_type: str,
    params: dict[str, Any],
    roles: dict[str, str],
) -> LinearTemplateCase:
    return LinearTemplateCase(
        problem_id=problem_id,
        realization_key=realization_key,
        kind=kind,
        answer_type=answer_type,
        params=params,
        roles=roles,
    )


def same_cases(problem_id: str, kind: str, answer_type: str, params: dict[str, Any], roles: dict[str, str]) -> list[LinearTemplateCase]:
    return [case(problem_id, realization, kind, answer_type, params, roles) for realization in COMMON_REALIZATIONS]


COORD_ROLES = {"x": "horizontal coordinate", "y": "vertical coordinate"}
RATE_ROLES = {"x1": "first input", "y1": "first output", "x2": "second input", "y2": "second output"}
SLOPE_ROLES = {"x1": "first input", "y1": "first output", "x2": "second input", "y2": "second output"}
RISE_RUN_ROLES = {"rise": "vertical change", "run": "horizontal change"}
INTERCEPT_ROLES = {"b": "initial value"}
LINEAR_MODEL_ROLES = {"m": "signed rate", "b": "initial value", "var": "input variable"}
TWO_POINT_LINE_ROLES = {
    "x1": "first input",
    "y1": "first output",
    "x2": "second input",
    "y2": "second output",
    "var": "input variable",
}
POINT_SLOPE_LINE_ROLES = {
    "m": "signed rate",
    "x1": "known input",
    "y1": "known output",
    "var": "input variable",
}
EVALUATE_ROLES = {"m": "signed rate", "b": "initial value", "x": "given input"}
SOLVE_X_ROLES = {"m": "signed rate", "b": "initial value", "y": "given output"}


LINEAR_FUNCTION_TEMPLATE_CASES: tuple[LinearTemplateCase, ...] = (
    *same_cases("lf_p01", "coordinate", "ordered_pair", {"x": 4, "y": 3}, COORD_ROLES),
    *same_cases("lf_p02", "rate_between_points", "numeric", {"x1": 0, "y1": 50, "x2": 1, "y2": 80}, RATE_ROLES),
    case("lf_p03", "neutral", "rate_between_points", "numeric", {"x1": 0, "y1": 200, "x2": 2, "y2": 170}, RATE_ROLES),
    case("lf_p03", "space_logistics", "rate_between_points", "numeric", {"x1": 0, "y1": 200, "x2": 2, "y2": 170}, RATE_ROLES),
    case("lf_p03", "drone_physics", "rate_between_points", "numeric", {"x1": 0, "y1": 30, "x2": 1, "y2": 20}, RATE_ROLES),
    *same_cases("lf_p04", "slope_two_points", "numeric", {"x1": 1, "y1": 4, "x2": 5, "y2": 16}, SLOPE_ROLES),
    *same_cases("lf_p05", "slope_two_points", "expression", {"x1": 2, "y1": 3, "x2": 8, "y2": 6}, SLOPE_ROLES),
    *same_cases("lf_p06", "slope_two_points", "numeric", {"x1": 0, "y1": 90, "x2": 6, "y2": 30}, SLOPE_ROLES),
    *same_cases("lf_p07", "rise_run", "numeric", {"rise": 2, "run": 1}, RISE_RUN_ROLES),
    *same_cases("lf_p08", "rise_run", "expression", {"rise": 3, "run": 4}, RISE_RUN_ROLES),
    *same_cases("lf_p09", "intercept_equation", "numeric", {"b": 7}, INTERCEPT_ROLES),
    *same_cases("lf_p10", "intercept_point", "numeric", {"y": 12}, {"y": "vertical-axis value"}),
    case("lf_p11", "neutral", "slope_intercept_equation", "expression", {"m": 5, "b": 20, "var": "x"}, LINEAR_MODEL_ROLES),
    case("lf_p11", "space_logistics", "slope_intercept_equation", "expression", {"m": 5, "b": 20, "var": "d"}, LINEAR_MODEL_ROLES),
    case("lf_p11", "drone_physics", "slope_intercept_equation", "expression", {"m": 5, "b": 20, "var": "t"}, LINEAR_MODEL_ROLES),
    case("lf_p12", "neutral", "equation_two_points", "expression", {"x1": 0, "y1": 6, "x2": 3, "y2": 18, "var": "x"}, TWO_POINT_LINE_ROLES),
    case("lf_p12", "space_logistics", "equation_two_points", "expression", {"x1": 0, "y1": 6, "x2": 3, "y2": 18, "var": "d"}, TWO_POINT_LINE_ROLES),
    case("lf_p12", "drone_physics", "equation_two_points", "expression", {"x1": 0, "y1": 6, "x2": 3, "y2": 18, "var": "t"}, TWO_POINT_LINE_ROLES),
    case("lf_p13", "neutral", "equation_point_slope", "expression", {"m": -8, "x1": 2, "y1": 50, "var": "x"}, POINT_SLOPE_LINE_ROLES),
    case("lf_p13", "space_logistics", "equation_point_slope", "expression", {"m": -8, "x1": 2, "y1": 50, "var": "k"}, POINT_SLOPE_LINE_ROLES),
    case("lf_p13", "drone_physics", "equation_point_slope", "expression", {"m": -8, "x1": 2, "y1": 50, "var": "t"}, POINT_SLOPE_LINE_ROLES),
    *same_cases("lf_p14", "evaluate_y", "numeric", {"m": 3, "b": 4, "x": 10}, EVALUATE_ROLES),
    *same_cases("lf_p15", "solve_for_x", "numeric", {"m": 6, "b": 12, "y": 60}, SOLVE_X_ROLES),
    case("lf_p16", "neutral", "interpret_slope", "numeric", {"m": -25}, {"m": "signed rate"}),
    case("lf_p16", "space_logistics", "interpret_slope", "numeric", {"m": -25}, {"m": "signed rate"}),
    case("lf_p16", "drone_physics", "interpret_slope", "numeric", {"m": -10}, {"m": "signed rate"}),
)


def solve_case(template_case: LinearTemplateCase) -> str:
    params = template_case.params
    match template_case.kind:
        case "coordinate":
            return f"({params['x']}, {params['y']})"
        case "rate_between_points" | "slope_two_points":
            return _format_fraction(_slope(params))
        case "rise_run":
            return _format_fraction(Fraction(params["rise"], params["run"]))
        case "intercept_equation":
            return _format_fraction(Fraction(params["b"]))
        case "intercept_point":
            return _format_fraction(Fraction(params["y"]))
        case "slope_intercept_equation":
            return _format_linear_expression(Fraction(params["m"]), Fraction(params["b"]), params["var"])
        case "equation_two_points":
            slope = _slope(params)
            intercept = Fraction(params["y1"]) - slope * Fraction(params["x1"])
            return _format_linear_expression(slope, intercept, params["var"])
        case "equation_point_slope":
            slope = Fraction(params["m"])
            intercept = Fraction(params["y1"]) - slope * Fraction(params["x1"])
            return _format_linear_expression(slope, intercept, params["var"])
        case "evaluate_y":
            return _format_fraction(Fraction(params["m"]) * Fraction(params["x"]) + Fraction(params["b"]))
        case "solve_for_x":
            return _format_fraction((Fraction(params["y"]) - Fraction(params["b"])) / Fraction(params["m"]))
        case "interpret_slope":
            return _format_fraction(Fraction(params["m"]))
    raise ValueError(f"Unknown template kind: {template_case.kind}")


def known_wrong_answers(template_case: LinearTemplateCase) -> dict[str, str]:
    if template_case.kind not in {"rate_between_points", "slope_two_points", "rise_run"}:
        return {}

    if template_case.kind == "rise_run":
        correct = Fraction(template_case.params["rise"], template_case.params["run"])
    else:
        correct = _slope(template_case.params)

    distractors = {
        "sign_error": _format_fraction(-correct),
    }
    if correct:
        distractors["inverted_slope"] = _format_fraction(1 / correct)
    return distractors


def _slope(params: dict[str, Any]) -> Fraction:
    return Fraction(params["y2"] - params["y1"], params["x2"] - params["x1"])


def _format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _format_linear_expression(slope: Fraction, intercept: Fraction, variable: str) -> str:
    if slope.denominator == 1:
        slope_text = f"{slope.numerator}*{variable}"
    else:
        slope_text = f"{slope.numerator}/{slope.denominator}*{variable}"

    if intercept == 0:
        return slope_text
    if intercept > 0:
        return f"{slope_text} + {_format_fraction(intercept)}"
    return f"{slope_text} - {_format_fraction(-intercept)}"
