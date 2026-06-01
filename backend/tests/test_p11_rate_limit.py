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


def test_rate_limiting_is_disabled_by_default(login):
    client = TestClient(create_app(Settings.from_env({})))
    headers = login(client, "stu")

    for _ in range(5):
        response = client.post("/session/start", json={"theme": "neutral"}, headers=headers)
        assert response.status_code == 200
