from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.app.domain.diagnostic_checker import DiagnosticResult


@dataclass(frozen=True)
class LLMResponse:
    dialogue: str
    pedagogical_move: str
    ui_mode: str
    proposed_hint_level: int
    teacher_check: dict[str, Any] = field(default_factory=dict)
    usage_metadata: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    def generate(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        tier: str = "hard",
    ) -> LLMResponse:
        ...
