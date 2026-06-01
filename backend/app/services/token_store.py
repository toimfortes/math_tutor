"""Session bearer tokens.

A token is an opaque, unguessable string issued when a session starts. It binds
a session to the student that owns it, so protected endpoints can derive a
verified identity from the token instead of trusting a client-supplied
student_id. In-memory by default; SQLite-backed (durable) when a db path is
configured.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


@dataclass(frozen=True)
class TokenRecord:
    session_id: str
    student_id: str


class TokenStore(Protocol):
    def issue(self, *, session_id: str, student_id: str) -> str: ...

    def resolve(self, token: str) -> TokenRecord | None: ...


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class InMemoryTokenStore:
    def __init__(self, token_factory: Callable[[], str] = _new_token):
        self._token_factory = token_factory
        self._records: dict[str, TokenRecord] = {}

    def issue(self, *, session_id: str, student_id: str) -> str:
        token = self._token_factory()
        self._records[token] = TokenRecord(session_id=session_id, student_id=student_id)
        return token

    def resolve(self, token: str) -> TokenRecord | None:
        return self._records.get(token)


class SqliteTokenStore:
    def __init__(self, path: str | Path, token_factory: Callable[[], str] = _new_token):
        self._token_factory = token_factory
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS session_tokens ("
            "token TEXT PRIMARY KEY, session_id TEXT NOT NULL, student_id TEXT NOT NULL)"
        )
        self._conn.commit()

    def issue(self, *, session_id: str, student_id: str) -> str:
        token = self._token_factory()
        self._conn.execute(
            "INSERT INTO session_tokens (token, session_id, student_id) VALUES (?, ?, ?)",
            (token, session_id, student_id),
        )
        self._conn.commit()
        return token

    def resolve(self, token: str) -> TokenRecord | None:
        row = self._conn.execute(
            "SELECT session_id, student_id FROM session_tokens WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return None
        return TokenRecord(session_id=row[0], student_id=row[1])
