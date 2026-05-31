from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "Math Tutor"
    database_url: str = "sqlite+pysqlite:///:memory:"
