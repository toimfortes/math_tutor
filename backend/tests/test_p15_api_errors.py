from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.session_store import StaleSessionError


def test_unknown_session_returns_404():
    client = TestClient(create_app(Settings.from_env({})))

    response = client.post("/turn", json={"session_id": "nope", "idempotency_key": "x", "answer": "1"})

    assert response.status_code == 404


def test_unknown_session_state_returns_404():
    client = TestClient(create_app(Settings.from_env({})))

    response = client.get("/student/stu/state", params={"session_id": "nope", "skill_id": "sk"})

    assert response.status_code == 404


def test_unknown_theme_returns_400():
    client = TestClient(create_app(Settings.from_env({})))

    response = client.post("/session/start", json={"student_id": "stu", "theme": "not-a-theme"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unknown theme"


def test_stale_write_returns_409(monkeypatch):
    app = create_app(Settings.from_env({}))
    client = TestClient(app)
    start = client.post("/session/start", json={"student_id": "stu", "theme": "space_logistics"}).json()

    def boom(state):
        raise StaleSessionError(state.session_id)

    monkeypatch.setattr(app.state.turn_service.store, "save", boom)
    response = client.post(
        "/turn",
        json={"session_id": start["session_id"], "idempotency_key": "t1", "answer": "(4, 3)"},
    )

    assert response.status_code == 409
