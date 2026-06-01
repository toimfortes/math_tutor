"""Student accounts and login.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, no third-party dep).
login() verifies a password and issues an opaque auth token that identifies the
student; start_session requires such a token, so the student identity is
verified at session creation rather than self-asserted. Accounts and tokens are
in-memory by default, SQLite-backed (durable) when a db path is configured.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path
from typing import Callable, Protocol

PBKDF2_ITERATIONS = 100_000


class DuplicateAccountError(Exception):
    """Raised when registering a student id that already exists."""


class InvalidCredentialsError(Exception):
    """Raised when a login's student id / password do not match."""


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = salt if salt is not None else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = encoded.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(derived.hex(), hash_hex)


class AuthStore(Protocol):
    def create_account(self, student_id: str, password_hash: str) -> None: ...

    def password_hash(self, student_id: str) -> str | None: ...

    def save_token(self, token: str, student_id: str) -> None: ...

    def student_for_token(self, token: str) -> str | None: ...


class InMemoryAuthStore:
    def __init__(self) -> None:
        self._accounts: dict[str, str] = {}
        self._tokens: dict[str, str] = {}

    def create_account(self, student_id: str, password_hash: str) -> None:
        self._accounts[student_id] = password_hash

    def password_hash(self, student_id: str) -> str | None:
        return self._accounts.get(student_id)

    def save_token(self, token: str, student_id: str) -> None:
        self._tokens[token] = student_id

    def student_for_token(self, token: str) -> str | None:
        return self._tokens.get(token)


class SqliteAuthStore:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS accounts (student_id TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS auth_tokens (token TEXT PRIMARY KEY, student_id TEXT NOT NULL)")
        self._conn.commit()

    def create_account(self, student_id: str, password_hash: str) -> None:
        self._conn.execute(
            "INSERT INTO accounts (student_id, password_hash) VALUES (?, ?)", (student_id, password_hash)
        )
        self._conn.commit()

    def password_hash(self, student_id: str) -> str | None:
        row = self._conn.execute("SELECT password_hash FROM accounts WHERE student_id = ?", (student_id,)).fetchone()
        return row[0] if row else None

    def save_token(self, token: str, student_id: str) -> None:
        self._conn.execute("INSERT INTO auth_tokens (token, student_id) VALUES (?, ?)", (token, student_id))
        self._conn.commit()

    def student_for_token(self, token: str) -> str | None:
        row = self._conn.execute("SELECT student_id FROM auth_tokens WHERE token = ?", (token,)).fetchone()
        return row[0] if row else None


class AuthService:
    def __init__(self, store: AuthStore, token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32)):
        self._store = store
        self._token_factory = token_factory

    def register(self, *, student_id: str, password: str) -> None:
        if self._store.password_hash(student_id) is not None:
            raise DuplicateAccountError(student_id)
        self._store.create_account(student_id, hash_password(password))

    def login(self, *, student_id: str, password: str) -> str:
        encoded = self._store.password_hash(student_id)
        if encoded is None or not verify_password(password, encoded):
            raise InvalidCredentialsError(student_id)
        token = self._token_factory()
        self._store.save_token(token, student_id)
        return token

    def resolve(self, token: str) -> str | None:
        return self._store.student_for_token(token)
