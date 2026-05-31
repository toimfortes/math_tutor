from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.diagnostic_checker import DiagnosticResult


@dataclass(frozen=True)
class LLMResponse:
    dialogue: str
    pedagogical_move: str
    ui_mode: str
    proposed_hint_level: int


class MockLLMClient:
    def generate(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
    ) -> LLMResponse:
        if presenting_next:
            return LLMResponse(
                dialogue="Here is the next problem.",
                pedagogical_move="present_next_problem",
                ui_mode="chat",
                proposed_hint_level=0,
            )
        if check_result == "correct":
            return LLMResponse(
                dialogue="That matches the expected structure. Keep going.",
                pedagogical_move="summarize_mastery",
                ui_mode="chat",
                proposed_hint_level=0,
            )
        if diagnostic and diagnostic.student_error_tag not in {"unknown", "none", "malformed_input"}:
            return LLMResponse(
                dialogue="Check which change goes on top of the rate.",
                pedagogical_move="rectify_error",
                ui_mode="chat",
                proposed_hint_level=min(allowed_help_level, diagnostic.safe_hint_level_cap),
            )
        return LLMResponse(
            dialogue="Look back at the relationship in the problem and try another form.",
            pedagogical_move="offer_heuristic_hint",
            ui_mode="chat",
            proposed_hint_level=allowed_help_level,
        )
