from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.auth import (
    AuthService,
    DuplicateAccountError,
    InMemoryAuthStore,
    InvalidCredentialsError,
    SqliteAuthStore,
    hash_password,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies():
    encoded = hash_password("hunter2")
    assert "hunter2" not in encoded
    assert verify_password("hunter2", encoded)
    assert not verify_password("wrong", encoded)


def test_register_then_login_issues_a_resolvable_token():
    service = AuthService(InMemoryAuthStore())
    service.register(student_id="alice", password="pw")

    token = service.login(student_id="alice", password="pw")
    assert service.resolve(token) == "alice"
    assert service.resolve("garbage") is None


def test_duplicate_registration_is_rejected():
    service = AuthService(InMemoryAuthStore())
    service.register(student_id="alice", password="pw")

    with pytest.raises(DuplicateAccountError):
        service.register(student_id="alice", password="other")


def test_bad_credentials_are_rejected():
    service = AuthService(InMemoryAuthStore())
    service.register(student_id="alice", password="pw")

    with pytest.raises(InvalidCredentialsError):
        service.login(student_id="alice", password="nope")
    with pytest.raises(InvalidCredentialsError):
        service.login(student_id="ghost", password="pw")


def test_sqlite_auth_store_is_durable(tmp_path):
    db = tmp_path / "auth.db"
    first = AuthService(SqliteAuthStore(db))
    first.register(student_id="alice", password="pw")
    token = first.login(student_id="alice", password="pw")

    second = AuthService(SqliteAuthStore(db))
    assert second.resolve(token) == "alice"  # token persisted
    assert second.login(student_id="alice", password="pw")  # account persisted


def test_register_and_login_endpoints():
    client = TestClient(create_app(Settings.from_env({})))

    created = client.post("/auth/register", json={"student_id": "alice", "password": "pw"})
    assert created.status_code == 201

    duplicate = client.post("/auth/register", json={"student_id": "alice", "password": "pw"})
    assert duplicate.status_code == 409

    login = client.post("/auth/login", json={"student_id": "alice", "password": "pw"})
    assert login.status_code == 200
    assert login.json()["auth_token"]

    bad = client.post("/auth/login", json={"student_id": "alice", "password": "nope"})
    assert bad.status_code == 401


def test_start_session_requires_authentication(login):
    client = TestClient(create_app(Settings.from_env({})))

    # without an auth token the session cannot be created
    assert client.post("/session/start", json={"theme": "neutral"}).status_code == 401

    # with a valid auth token the session is created and the student is derived from it
    started = client.post("/session/start", json={"theme": "neutral"}, headers=login(client, "alice"))
    assert started.status_code == 200
    assert started.json()["token"]

