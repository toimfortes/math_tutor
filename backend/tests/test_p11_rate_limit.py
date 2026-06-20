from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.rate_limiter import FixedWindowRateLimiter


def test_allows_up_to_limit_then_blocks():
    now = [1000.0]
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False


def test_window_resets_after_elapsed_time():
    now = [1000.0]
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    now[0] += 61
    assert limiter.allow("a") is True


def test_keys_are_independent():
    now = [1000.0]
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("b") is True


def test_session_start_is_rate_limited_per_student(login):
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))
    stu = login(client, "stu")
    other = login(client, "other")

    first = client.post("/session/start", json={"theme": "neutral"}, headers=stu)
    second = client.post("/session/start", json={"theme": "neutral"}, headers=stu)
    other_start = client.post("/session/start", json={"theme": "neutral"}, headers=other)

    assert first.status_code == 200
    assert second.status_code == 429
    assert other_start.status_code == 200  # a different student has its own budget


def test_skip_is_rate_limited_per_session(login):
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))
    start = client.post("/session/start", json={"theme": "neutral"}, headers=login(client, "stu")).json()
    auth = {"Authorization": f"Bearer {start['token']}"}

    first = client.post("/session/skip", json={"session_id": start["session_id"], "reason": "stuck"}, headers=auth)
    second = client.post("/session/skip", json={"session_id": start["session_id"], "reason": "stuck"}, headers=auth)

    assert first.status_code == 200
    assert second.status_code == 429


def test_assessment_writes_are_rate_limited_per_session(login):
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))
    start = client.post("/session/start", json={"theme": "neutral"}, headers=login(client, "stu")).json()
    auth = {"Authorization": f"Bearer {start['token']}"}
    payload = {
        "session_id": start["session_id"],
        "skill_id": start["public_problem"]["skill_id"],
        "context_key": "neutral:transfer",
    }

    first = client.post("/assessment/transfer", json=payload, headers=auth)
    second = client.post("/assessment/transfer", json=payload, headers=auth)

    assert first.status_code == 200
    assert second.status_code == 429


def test_login_attempts_are_rate_limited_per_student():
    # Brute-forcing a student's password via /auth/login must be capped like the rest
    # of the mutable API. The limit applies BEFORE the credential check, so failed
    # guesses count.
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))
    client.post("/auth/register", json={"student_id": "victim", "password": "correct-pw"})

    first = client.post("/auth/login", json={"student_id": "victim", "password": "guess-1"})
    second = client.post("/auth/login", json={"student_id": "victim", "password": "guess-2"})
    assert first.status_code == 401  # wrong password, but the attempt was allowed
    assert second.status_code == 429  # capped before the credential check

    # a different account keeps its own budget
    client.post("/auth/register", json={"student_id": "other", "password": "x"})
    assert client.post("/auth/login", json={"student_id": "other", "password": "y"}).status_code == 401


def test_login_limit_is_per_ip_so_one_attacker_cannot_lock_out_a_victim():
    # Composite {ip}:{student_id} key: an attacker flooding the victim's id from their
    # own IP must NOT exhaust the victim's budget from a different IP.
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    app = create_app(settings)
    attacker = TestClient(app, client=("10.0.0.1", 1111))
    victim = TestClient(app, client=("10.0.0.2", 2222))
    attacker.post("/auth/register", json={"student_id": "victim", "password": "correct-pw"})

    # attacker burns the victim-id budget from 10.0.0.1
    assert attacker.post("/auth/login", json={"student_id": "victim", "password": "g1"}).status_code == 401
    assert attacker.post("/auth/login", json={"student_id": "victim", "password": "g2"}).status_code == 429
    # the real victim, from a different IP, still has its own budget and can log in
    ok = victim.post("/auth/login", json={"student_id": "victim", "password": "correct-pw"})
    assert ok.status_code == 200 and "auth_token" in ok.json()


def test_register_is_rate_limited_per_student():
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))
    first = client.post("/auth/register", json={"student_id": "stu", "password": "pw"})
    second = client.post("/auth/register", json={"student_id": "stu", "password": "pw2"})
    assert first.status_code == 201
    assert second.status_code == 429  # repeated registration attempts on one id are capped


def test_rate_limiting_is_disabled_by_default(login):
    client = TestClient(create_app(Settings.from_env({})))
    headers = login(client, "stu")

    for _ in range(5):
        response = client.post("/session/start", json={"theme": "neutral"}, headers=headers)
        assert response.status_code == 200
