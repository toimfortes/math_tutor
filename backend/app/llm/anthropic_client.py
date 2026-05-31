from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.app.domain.diagnostic_checker import DiagnosticResult
from backend.app.llm.types import LLMResponse


DEFAULT_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
ROOT = Path(__file__).resolve().parents[3]
LLM_CONTRACT_PATH = ROOT / "docs/llm-contract.md"


class JSONTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        ...


class UrllibJSONTransport:
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"JSON API request failed: HTTP {exc.code}: {detail}") from exc


@dataclass(frozen=True)
class AnthropicLLMClient:
    api_key: str
    model: str
    routine_model: str | None = None
    hard_model: str | None = None
    top_model: str | None = None
    routing_mode: str = "strong_only"
    transport: JSONTransport | None = None
    api_url: str = DEFAULT_ANTHROPIC_API_URL
    anthropic_version: str = DEFAULT_ANTHROPIC_VERSION
    max_tokens: int = 512
    timeout_seconds: int = 15

    def generate(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        tier: str = "hard",
    ) -> LLMResponse:
        response = (self.transport or UrllibJSONTransport()).post_json(
            url=self.api_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
                "content-type": "application/json",
            },
            payload=self._payload(
                check_result=check_result,
                diagnostic=diagnostic,
                presenting_next=presenting_next,
                allowed_help_level=allowed_help_level,
                tier=tier,
            ),
            timeout_seconds=self.timeout_seconds,
        )
        return _parse_tool_response(response)

    def _payload(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        tier: str,
    ) -> dict[str, Any]:
        return {
            "model": self._model_for_tier(tier),
            "max_tokens": self.max_tokens,
            "system": _load_llm_contract(),
            "messages": [
                {
                    "role": "user",
                    "content": _turn_context_text(
                        check_result=check_result,
                        diagnostic=diagnostic,
                        presenting_next=presenting_next,
                        allowed_help_level=allowed_help_level,
                    ),
                }
            ],
            "tools": [EMIT_TUTOR_TURN_TOOL],
            "tool_choice": {"type": "tool", "name": "emit_tutor_turn"},
        }

    def _model_for_tier(self, tier: str) -> str:
        if self.routing_mode != "tiered":
            return self.hard_model or self.model
        if tier == "routine":
            return self.routine_model or self.hard_model or self.model
        if tier == "top":
            return self.top_model or self.hard_model or self.model
        return self.hard_model or self.model


EMIT_TUTOR_TURN_TOOL: dict[str, Any] = {
    "name": "emit_tutor_turn",
    "description": (
        "Emit exactly one math-tutor turn. Use only the server-provided check result, "
        "diagnostic tag, and authored scaffold constraints. Never include final answers, "
        "provider reasoning, or private solution data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "teacher_check": {
                "type": "object",
                "properties": {
                    "student_error_tag": {"type": "string"},
                    "next_scaffold_id": {"type": "string"},
                    "leak_risk": {"type": "string", "enum": ["none", "possible", "blocked"]},
                    "uses_only_authored_scaffold": {"type": "boolean"},
                    "chosen_pedagogical_move": {"type": "string"},
                },
                "required": [
                    "student_error_tag",
                    "next_scaffold_id",
                    "leak_risk",
                    "uses_only_authored_scaffold",
                    "chosen_pedagogical_move",
                ],
            },
            "dialogue": {"type": "string"},
            "pedagogical_move": {
                "type": "string",
                "enum": [
                    "review_concept",
                    "offer_heuristic_hint",
                    "rectify_error",
                    "request_clarification",
                    "reflect",
                    "summarize_mastery",
                    "present_next_problem",
                ],
            },
            "ui_mode": {"type": "string", "enum": ["chat", "equation", "table", "graph", "reflection"]},
            "proposed_hint_level": {"type": "integer", "minimum": 0, "maximum": 3},
        },
        "required": [
            "teacher_check",
            "dialogue",
            "pedagogical_move",
            "ui_mode",
            "proposed_hint_level",
        ],
    },
}


def _load_llm_contract() -> str:
    return LLM_CONTRACT_PATH.read_text()


def _turn_context_text(
    *,
    check_result: str | None,
    diagnostic: DiagnosticResult | None,
    presenting_next: bool,
    allowed_help_level: int,
) -> str:
    diagnostic_payload = None
    if diagnostic is not None:
        diagnostic_payload = {
            "student_error_tag": diagnostic.student_error_tag,
            "confidence": diagnostic.confidence,
            "matched_pattern": diagnostic.matched_pattern,
            "safe_hint_level_cap": diagnostic.safe_hint_level_cap,
        }
    return json.dumps(
        {
            "check_result": check_result,
            "diagnostic": diagnostic_payload,
            "presenting_next": presenting_next,
            "allowed_help_level": allowed_help_level,
            "instruction": "Call emit_tutor_turn with the next public tutoring response.",
        },
        sort_keys=True,
    )


def _parse_tool_response(response: dict[str, Any]) -> LLMResponse:
    for block in response.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "emit_tutor_turn":
            tool_input = block.get("input") or {}
            return LLMResponse(
                dialogue=str(tool_input["dialogue"]),
                pedagogical_move=str(tool_input["pedagogical_move"]),
                ui_mode=str(tool_input["ui_mode"]),
                proposed_hint_level=int(tool_input["proposed_hint_level"]),
                teacher_check=dict(tool_input.get("teacher_check") or {}),
                usage_metadata=dict(response.get("usage") or {}),
            )
    raise ValueError("Anthropic response did not include emit_tutor_turn tool_use")
