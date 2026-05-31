from __future__ import annotations

from dataclasses import dataclass
import re

from sympy import N, simplify
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from backend.app.domain.answer_normalizer import normalize_answer


TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)


@dataclass(frozen=True)
class CheckResult:
    check_result: str
    normalized_answer: str
    reason: str | None = None


def check_answer(student_answer: str, canonical_answer: str, *, answer_type: str, variable: str | None = None) -> CheckResult:
    normalized = normalize_answer(student_answer, answer_type=answer_type).normalized
    canonical = normalize_answer(canonical_answer, answer_type=answer_type).normalized

    try:
        if answer_type == "numeric":
            return _check_numeric(normalized, canonical)
        if answer_type == "expression":
            return _check_expression(normalized, canonical, variable=variable)
        if answer_type == "ordered_pair":
            return _check_ordered_pair(normalized, canonical)
        if answer_type == "set":
            return CheckResult("undecidable", normalized, "set_checker_not_implemented")
    except Exception as exc:
        return CheckResult("undecidable", normalized, f"parse_error:{type(exc).__name__}")

    return CheckResult("undecidable", normalized, f"unsupported_answer_type:{answer_type}")


def _check_numeric(student: str, canonical: str) -> CheckResult:
    student_expr = parse_expr(student, transformations=TRANSFORMS, evaluate=True)
    canonical_expr = parse_expr(canonical, transformations=TRANSFORMS, evaluate=True)
    if abs(float(N(student_expr - canonical_expr))) <= 1e-9:
        return CheckResult("correct", student)
    return CheckResult("incorrect", student)


def _check_expression(student: str, canonical: str, *, variable: str | None) -> CheckResult:
    symbols = {variable: parse_expr(variable)} if variable else {}
    student_expr = parse_expr(student, local_dict=symbols, transformations=TRANSFORMS, evaluate=True)
    canonical_expr = parse_expr(canonical, local_dict=symbols, transformations=TRANSFORMS, evaluate=True)
    if simplify(student_expr - canonical_expr) == 0:
        return CheckResult("correct", student)
    return CheckResult("incorrect", student)


def _check_ordered_pair(student: str, canonical: str) -> CheckResult:
    student_pair = _parse_pair(student)
    canonical_pair = _parse_pair(canonical)
    if student_pair is None or canonical_pair is None:
        return CheckResult("undecidable", student, "pair_parse_error")
    first = _check_numeric(student_pair[0], canonical_pair[0]).check_result
    second = _check_numeric(student_pair[1], canonical_pair[1]).check_result
    return CheckResult("correct" if first == second == "correct" else "incorrect", student)


def _parse_pair(value: str) -> tuple[str, str] | None:
    match = re.match(r"^\(?\s*([^,]+?)\s*,\s*([^)]+?)\s*\)?$", value)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()
