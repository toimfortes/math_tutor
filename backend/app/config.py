from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    app_name: str = "Math Tutor"
    database_url: str = "sqlite+pysqlite:///:memory:"
    session_db_path: str | None = None
    rate_limit_per_minute: int | None = None
    daily_llm_budget: int | None = None
    practice_bank_path: str | None = None
    llm_provider: str = "mock"
    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_routine_model: str | None = None
    anthropic_hard_model: str | None = None
    anthropic_top_model: str | None = None
    anthropic_version: str = "2023-06-01"
    google_api_key: str | None = None
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/models"
    gemini_model: str = "gemini-3.5-flash"
    gemini_routine_model: str | None = None
    gemini_hard_model: str | None = None
    gemini_top_model: str | None = None
    llm_routing_mode: str = "strong_only"
    llm_max_tokens: int = 512
    llm_timeout_seconds: int = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = environ if env is None else env
        return cls(
            app_name=source.get("APP_NAME", cls.app_name),
            database_url=source.get("DATABASE_URL", cls.database_url),
            session_db_path=source.get("SESSION_DB_PATH"),
            rate_limit_per_minute=_optional_int_from_env(source, "RATE_LIMIT_PER_MINUTE"),
            daily_llm_budget=_optional_int_from_env(source, "DAILY_LLM_BUDGET"),
            practice_bank_path=source.get("PRACTICE_BANK_PATH"),
            llm_provider=source.get("LLM_PROVIDER", cls.llm_provider).lower(),
            anthropic_api_key=source.get("ANTHROPIC_API_KEY"),
            anthropic_api_url=source.get("ANTHROPIC_API_URL", cls.anthropic_api_url),
            anthropic_model=source.get("ANTHROPIC_MODEL", cls.anthropic_model),
            anthropic_routine_model=source.get("ANTHROPIC_ROUTINE_MODEL"),
            anthropic_hard_model=source.get("ANTHROPIC_HARD_MODEL"),
            anthropic_top_model=source.get("ANTHROPIC_TOP_MODEL"),
            anthropic_version=source.get("ANTHROPIC_VERSION", cls.anthropic_version),
            google_api_key=source.get("GOOGLE_API_KEY") or source.get("GEMINI_API_KEY"),
            gemini_api_url=source.get("GEMINI_API_URL", cls.gemini_api_url),
            gemini_model=source.get("GEMINI_MODEL", cls.gemini_model),
            gemini_routine_model=source.get("GEMINI_ROUTINE_MODEL"),
            gemini_hard_model=source.get("GEMINI_HARD_MODEL"),
            gemini_top_model=source.get("GEMINI_TOP_MODEL"),
            llm_routing_mode=source.get("LLM_ROUTING_MODE", cls.llm_routing_mode).lower(),
            llm_max_tokens=_int_from_env(source, "LLM_MAX_TOKENS", cls.llm_max_tokens),
            llm_timeout_seconds=_int_from_env(source, "LLM_TIMEOUT_SECONDS", cls.llm_timeout_seconds),
        )


def _int_from_env(source: Mapping[str, str], key: str, default: int) -> int:
    value = source.get(key)
    if value is None:
        return default
    return int(value)


def _optional_int_from_env(source: Mapping[str, str], key: str) -> int | None:
    value = source.get(key)
    if value is None:
        return None
    return int(value)
