from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.checker import check_answer


@dataclass(frozen=True)
class DiagnosticResult:
    student_error_tag: str
    confidence: str
    matched_pattern: str | None = None
    safe_hint_level_cap: int = 1


def diagnose_answer(
    *,
    student_answer: str,
    canonical_answer: str,
    answer_type: str,
    known_wrong_answers: dict[str, str] | None = None,
    variable: str | None = None,
) -> DiagnosticResult:
    if check_answer(student_answer, canonical_answer, answer_type=answer_type, variable=variable).check_result == "correct":
        return DiagnosticResult("none", "high", "canonical", 0)

    for tag, wrong_answer in (known_wrong_answers or {}).items():
        result = check_answer(student_answer, wrong_answer, answer_type=answer_type, variable=variable)
        if result.check_result == "correct":
            return DiagnosticResult(tag, "high", tag, 2)

    undecidable = check_answer(student_answer, canonical_answer, answer_type=answer_type, variable=variable)
    if undecidable.check_result == "undecidable":
        return DiagnosticResult("malformed_input", "medium", undecidable.reason, 0)

    return DiagnosticResult("unknown", "low", None, 1)
