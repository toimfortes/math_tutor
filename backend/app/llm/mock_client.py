from __future__ import annotations

from backend.app.domain.diagnostic_checker import DiagnosticResult
from backend.app.llm.types import LLMResponse


class MockLLMClient:
    def generate(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        tier: str = "hard",
        context: dict | None = None,
    ) -> LLMResponse:
        if presenting_next:
            return LLMResponse(
                dialogue="Here is the next problem.",
                pedagogical_move="present_next_problem",
                ui_mode="chat",
                proposed_hint_level=0,
                teacher_check=_teacher_check("none", "present_next_problem", 0),
            )
        if check_result == "correct":
            return LLMResponse(
                dialogue="That matches the expected structure. Keep going.",
                pedagogical_move="summarize_mastery",
                ui_mode="chat",
                proposed_hint_level=0,
                teacher_check=_teacher_check("none", "summarize_mastery", 0),
            )
        if diagnostic and diagnostic.student_error_tag not in {"unknown", "none", "malformed_input"}:
            return LLMResponse(
                dialogue="Check which change goes on top of the rate.",
                pedagogical_move="rectify_error",
                ui_mode="chat",
                proposed_hint_level=min(allowed_help_level, diagnostic.safe_hint_level_cap),
                teacher_check=_teacher_check(
                    diagnostic.student_error_tag,
                    "rectify_error",
                    min(allowed_help_level, diagnostic.safe_hint_level_cap),
                ),
            )
        return LLMResponse(
            dialogue="Look back at the relationship in the problem and try another form.",
            pedagogical_move="offer_heuristic_hint",
            ui_mode="chat",
            proposed_hint_level=allowed_help_level,
            teacher_check=_teacher_check("unknown", "offer_heuristic_hint", allowed_help_level),
        )


def _teacher_check(student_error_tag: str, move: str, level: int) -> dict[str, object]:
    return {
        "student_error_tag": student_error_tag,
        "next_scaffold_id": f"level_{level}",
        "leak_risk": "none",
        "uses_only_authored_scaffold": True,
        "chosen_pedagogical_move": move,
    }
