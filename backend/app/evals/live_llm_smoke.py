from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from backend.app.config import Settings
from backend.app.llm.gemini_client import GeminiLLMClient


DEFAULT_UKFL_ENV = Path("/home/antoniofortes/Projects/uk-family-law-ai/.env")
KEY_NAMES = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL")


def load_key_env_file(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in KEY_NAMES:
            continue
        loaded[key] = _strip_env_value(value)
    return loaded


def build_gemini_settings(
    *,
    env_file: Path = DEFAULT_UKFL_ENV,
    process_env: Mapping[str, str] | None = None,
) -> Settings:
    source = dict(load_key_env_file(env_file))
    source.update(process_env or os.environ)
    source["LLM_PROVIDER"] = "gemini"
    source.setdefault("GEMINI_MODEL", "gemini-3.5-flash")
    source.setdefault("LLM_MAX_TOKENS", "256")
    return Settings.from_env(source)


def run_gemini_smoke(settings: Settings) -> dict[str, object]:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for live Gemini smoke")
    client = GeminiLLMClient(
        api_key=settings.google_api_key,
        model=settings.gemini_model,
        routine_model=settings.gemini_routine_model,
        hard_model=settings.gemini_hard_model,
        top_model=settings.gemini_top_model,
        routing_mode=settings.llm_routing_mode,
        api_url=settings.gemini_api_url,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    response = client.generate(
        check_result="incorrect",
        diagnostic=None,
        presenting_next=False,
        allowed_help_level=1,
        tier="routine",
    )
    return {
        "provider": "gemini",
        "model": settings.gemini_model,
        "pedagogical_move": response.pedagogical_move,
        "ui_mode": response.ui_mode,
        "proposed_hint_level": response.proposed_hint_level,
        "teacher_check_leak_risk": response.teacher_check.get("leak_risk"),
        "usage_metadata": response.usage_metadata,
    }


def _strip_env_value(value: str) -> str:
    stripped = value.strip()
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def main() -> None:
    settings = build_gemini_settings()
    result = run_gemini_smoke(settings)
    print(
        "live Gemini smoke passed: "
        f"provider={result['provider']} "
        f"model={result['model']} "
        f"move={result['pedagogical_move']} "
        f"hint={result['proposed_hint_level']} "
        f"leak_risk={result['teacher_check_leak_risk']} "
        f"tokens={_total_tokens(result['usage_metadata'])}"
    )


def _total_tokens(usage_metadata: object) -> object:
    if isinstance(usage_metadata, dict):
        return usage_metadata.get("totalTokenCount", "unknown")
    return "unknown"


if __name__ == "__main__":
    main()
