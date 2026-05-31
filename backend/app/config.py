from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    app_name: str = "Math Tutor"
    database_url: str = "sqlite+pysqlite:///:memory:"
    llm_provider: str = "mock"
    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_routine_model: str | None = None
    anthropic_hard_model: str | None = None
    anthropic_top_model: str | None = None
    anthropic_version: str = "2023-06-01"
    llm_routing_mode: str = "strong_only"
    llm_max_tokens: int = 512
    llm_timeout_seconds: int = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = environ if env is None else env
        return cls(
            app_name=source.get("APP_NAME", cls.app_name),
            database_url=source.get("DATABASE_URL", cls.database_url),
            llm_provider=source.get("LLM_PROVIDER", cls.llm_provider).lower(),
            anthropic_api_key=source.get("ANTHROPIC_API_KEY"),
            anthropic_api_url=source.get("ANTHROPIC_API_URL", cls.anthropic_api_url),
            anthropic_model=source.get("ANTHROPIC_MODEL", cls.anthropic_model),
            anthropic_routine_model=source.get("ANTHROPIC_ROUTINE_MODEL"),
            anthropic_hard_model=source.get("ANTHROPIC_HARD_MODEL"),
            anthropic_top_model=source.get("ANTHROPIC_TOP_MODEL"),
            anthropic_version=source.get("ANTHROPIC_VERSION", cls.anthropic_version),
            llm_routing_mode=source.get("LLM_ROUTING_MODE", cls.llm_routing_mode).lower(),
            llm_max_tokens=_int_from_env(source, "LLM_MAX_TOKENS", cls.llm_max_tokens),
            llm_timeout_seconds=_int_from_env(source, "LLM_TIMEOUT_SECONDS", cls.llm_timeout_seconds),
        )


def _int_from_env(source: Mapping[str, str], key: str, default: int) -> int:
    value = source.get(key)
    if value is None:
        return default
    return int(value)
