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


def test_student_state_requires_matching_session_owner():
    client = TestClient(create_app(Settings.from_env({})))
    start = client.post("/session/start", json={"student_id": "alice", "theme": "neutral"}).json()

    response = client.get(
        "/student/bob/state",
        params={"session_id": start["session_id"], "skill_id": start["public_problem"]["skill_id"]},
    )

    assert response.status_code == 404


def test_unknown_theme_returns_400():
    client = TestClient(create_app(Settings.from_env({})))

    response = client.post("/session/start", json={"student_id": "stu", "theme": "not-a-theme"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unknown theme"


def test_empty_request_identifiers_return_422():
    client = TestClient(create_app(Settings.from_env({})))

    empty_student = client.post("/session/start", json={"student_id": " ", "theme": "neutral"})
    empty_theme = client.post("/session/start", json={"student_id": "stu", "theme": " "})
    empty_turn = client.post("/turn", json={"session_id": " ", "idempotency_key": "k", "answer": "1"})
    empty_answer = client.post("/turn", json={"session_id": "s", "idempotency_key": "k", "answer": " "})

    assert empty_student.status_code == 422
    assert empty_theme.status_code == 422
    assert empty_turn.status_code == 422
    assert empty_answer.status_code == 422


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
