from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.domain.diagnostic_checker import DiagnosticResult
from backend.app.llm.anthropic_client import JSONTransport, UrllibJSONTransport
from backend.app.llm.types import LLMResponse


DEFAULT_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
ROOT = Path(__file__).resolve().parents[3]
LLM_CONTRACT_PATH = ROOT / "docs/llm-contract.md"


@dataclass(frozen=True)
class GeminiLLMClient:
    api_key: str
    model: str
    routine_model: str | None = None
    hard_model: str | None = None
    top_model: str | None = None
    routing_mode: str = "strong_only"
    transport: JSONTransport | None = None
    api_url: str = DEFAULT_GEMINI_API_URL
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
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        model = self._model_for_tier(tier)
        response = (self.transport or UrllibJSONTransport()).post_json(
            url=f"{self.api_url}/{model}:generateContent",
            headers={
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
            },
            payload=self._payload(
                check_result=check_result,
                diagnostic=diagnostic,
                presenting_next=presenting_next,
                allowed_help_level=allowed_help_level,
                context=context,
            ),
            timeout_seconds=self.timeout_seconds,
        )
        return _parse_generate_content_response(response)

    def _payload(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "systemInstruction": {
                "parts": [{"text": _load_llm_contract()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _turn_context_text(
                                check_result=check_result,
                                diagnostic=diagnostic,
                                presenting_next=presenting_next,
                                allowed_help_level=allowed_help_level,
                                context=context,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
                "responseFormat": {
                    "text": {
                        "mimeType": "APPLICATION_JSON",
                        "schema": TUTOR_TURN_SCHEMA,
                    }
                },
            },
            "safetySettings": _default_safety_settings(),
        }

    def _model_for_tier(self, tier: str) -> str:
        if self.routing_mode != "tiered":
            return self.hard_model or self.model
        if tier == "routine":
            return self.routine_model or self.hard_model or self.model
        if tier == "top":
            return self.top_model or self.hard_model or self.model
        return self.hard_model or self.model


TUTOR_TURN_SCHEMA: dict[str, Any] = {
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
        "proposed_hint_level": {"type": "integer"},
    },
    "required": [
        "teacher_check",
        "dialogue",
        "pedagogical_move",
        "ui_mode",
        "proposed_hint_level",
    ],
}


def _load_llm_contract() -> str:
    return LLM_CONTRACT_PATH.read_text()


def _turn_context_text(
    *,
    check_result: str | None,
    diagnostic: DiagnosticResult | None,
    presenting_next: bool,
    allowed_help_level: int,
    context: dict[str, Any] | None = None,
) -> str:
    diagnostic_payload = None
    if diagnostic is not None:
        diagnostic_payload = {
            "student_error_tag": diagnostic.student_error_tag,
            "confidence": diagnostic.confidence,
            "matched_pattern": diagnostic.matched_pattern,
            "safe_hint_level_cap": diagnostic.safe_hint_level_cap,
        }
    payload: dict[str, Any] = {
            "check_result": check_result,
            "diagnostic": diagnostic_payload,
            "presenting_next": presenting_next,
            "allowed_help_level": allowed_help_level,
            "instruction": "Return one JSON tutor turn matching the configured response schema.",
    }
    if context:
        payload["context"] = context
    return json.dumps(payload, sort_keys=True)


def _parse_generate_content_response(response: dict[str, Any]) -> LLMResponse:
    text = _first_text_part(response)
    tool_input = _loads_first_json_object(text)
    return LLMResponse(
        dialogue=str(tool_input["dialogue"]),
        pedagogical_move=str(tool_input["pedagogical_move"]),
        ui_mode=str(tool_input["ui_mode"]),
        proposed_hint_level=int(tool_input["proposed_hint_level"]),
        teacher_check=dict(tool_input.get("teacher_check") or {}),
        usage_metadata=dict(response.get("usageMetadata") or {}),
    )


def _first_text_part(response: dict[str, Any]) -> str:
    for candidate in response.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text = part.get("text")
            if text:
                return str(text)
    raise ValueError("Gemini response did not include a text part")


def _loads_first_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        if start == -1:
            raise
        parsed, _end = json.JSONDecoder().raw_decode(stripped[start:])
        if not isinstance(parsed, dict):
            raise ValueError("Gemini structured output was not a JSON object")
        return parsed


def _default_safety_settings() -> list[dict[str, str]]:
    return [
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
