from __future__ import annotations

from backend.app.content.seed_loader import RealizedProblemRef
from backend.content_pipeline.templates.linear_functions import (
    LINEAR_FUNCTION_TEMPLATE_CASES,
    known_wrong_answers,
)


KNOWN_WRONG_ANSWERS_BY_REF: dict[RealizedProblemRef, dict[str, str]] = {
    template_case.ref: known_wrong_answers(template_case)
    for template_case in LINEAR_FUNCTION_TEMPLATE_CASES
    if known_wrong_answers(template_case)
}


def known_wrong_answers_for_ref(ref: RealizedProblemRef) -> dict[str, str]:
    return KNOWN_WRONG_ANSWERS_BY_REF.get(ref, {})
