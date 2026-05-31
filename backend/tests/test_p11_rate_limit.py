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


def test_session_start_is_rate_limited_per_student():
    settings = Settings.from_env({"RATE_LIMIT_PER_MINUTE": "1"})
    client = TestClient(create_app(settings))

    first = client.post("/session/start", json={"student_id": "stu", "theme": "neutral"})
    second = client.post("/session/start", json={"student_id": "stu", "theme": "neutral"})
    other = client.post("/session/start", json={"student_id": "other", "theme": "neutral"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert other.status_code == 200  # a different student has its own budget


def test_rate_limiting_is_disabled_by_default():
    client = TestClient(create_app(Settings.from_env({})))

    for _ in range(5):
        response = client.post("/session/start", json={"student_id": "stu", "theme": "neutral"})
        assert response.status_code == 200
