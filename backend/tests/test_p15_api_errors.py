from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.session_store import StaleSessionError


def _client():
    return TestClient(create_app(Settings.from_env({})))


def _start(client, student="alice", theme="neutral"):
    body = client.post("/session/start", json={"student_id": student, "theme": theme}).json()
    return body, {"Authorization": f"Bearer {body['token']}"}


def test_turn_on_a_session_the_token_does_not_own_is_forbidden():
    client = _client()
    _, auth = _start(client)

    response = client.post(
        "/turn",
        json={"session_id": "not-this-token's-session", "idempotency_key": "x", "answer": "1"},
        headers=auth,
    )

    assert response.status_code == 403


def test_unknown_skill_returns_400_for_state_and_assessments():
    client = _client()
    start, auth = _start(client)

    state = client.get(
        "/student/alice/state",
        params={"session_id": start["session_id"], "skill_id": "not-a-skill"},
        headers=auth,
    )
    transfer = client.post(
        "/assessment/transfer",
        json={"session_id": start["session_id"], "skill_id": "not-a-skill", "context_key": "neutral:transfer"},
        headers=auth,
    )

    assert state.status_code == 400
    assert state.json()["detail"] == "unknown skill"
    assert transfer.status_code == 400
    assert transfer.json()["detail"] == "unknown skill"


def test_unknown_theme_returns_400():
    response = _client().post("/session/start", json={"student_id": "stu", "theme": "not-a-theme"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unknown theme"


def test_empty_request_identifiers_return_422():
    client = _client()
    start, auth = _start(client, theme="space_logistics")

    empty_student = client.post("/session/start", json={"student_id": " ", "theme": "neutral"})
    empty_theme = client.post("/session/start", json={"student_id": "stu", "theme": " "})
    empty_answer = client.post(
        "/turn",
        json={"session_id": start["session_id"], "idempotency_key": "k", "answer": " "},
        headers=auth,
    )

    assert empty_student.status_code == 422
    assert empty_theme.status_code == 422
    assert empty_answer.status_code == 422


def test_stale_write_returns_409(monkeypatch):
    app = create_app(Settings.from_env({}))
    client = TestClient(app)
    start = client.post("/session/start", json={"student_id": "stu", "theme": "space_logistics"}).json()
    auth = {"Authorization": f"Bearer {start['token']}"}

    def boom(state):
        raise StaleSessionError(state.session_id)

    monkeypatch.setattr(app.state.turn_service.store, "save", boom)
    response = client.post(
        "/turn",
        json={"session_id": start["session_id"], "idempotency_key": "t1", "answer": "(4, 3)"},
        headers=auth,
    )

    assert response.status_code == 409
