from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.token_store import InMemoryTokenStore, SqliteTokenStore


def _client():
    return TestClient(create_app(Settings.from_env({})))


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- token store ---------------------------------------------------------

def test_token_store_roundtrip():
    store = InMemoryTokenStore()
    token = store.issue(session_id="s1", student_id="stu")

    record = store.resolve(token)
    assert record is not None
    assert record.session_id == "s1"
    assert record.student_id == "stu"
    assert store.resolve("garbage") is None


def test_tokens_are_unique():
    store = InMemoryTokenStore()
    assert store.issue(session_id="s1", student_id="a") != store.issue(session_id="s2", student_id="b")


def test_sqlite_token_store_is_durable(tmp_path):
    db = tmp_path / "tokens.db"
    token = SqliteTokenStore(db).issue(session_id="s1", student_id="stu")

    record = SqliteTokenStore(db).resolve(token)
    assert record is not None and record.session_id == "s1"


# --- API contract --------------------------------------------------------

def test_start_session_returns_a_token():
    body = _client().post("/session/start", json={"student_id": "stu", "theme": "neutral"}).json()
    assert body["token"]


def test_turn_requires_a_bearer_token():
    client = _client()
    start = client.post("/session/start", json={"student_id": "stu", "theme": "space_logistics"}).json()
    payload = {"session_id": start["session_id"], "idempotency_key": "t1", "answer": "(4, 3)"}

    assert client.post("/turn", json=payload).status_code == 401
    assert client.post("/turn", json=payload, headers=_bearer(start["token"])).status_code == 200


def test_forged_token_is_rejected():
    client = _client()
    start = client.post("/session/start", json={"student_id": "stu", "theme": "neutral"}).json()
    payload = {"session_id": start["session_id"], "idempotency_key": "t1", "answer": "1"}

    assert client.post("/turn", json=payload, headers=_bearer("not-a-real-token")).status_code == 401


def test_token_cannot_drive_another_students_session():
    client = _client()
    alice = client.post("/session/start", json={"student_id": "alice", "theme": "neutral"}).json()
    bob = client.post("/session/start", json={"student_id": "bob", "theme": "neutral"}).json()

    # alice's token used against bob's session
    response = client.post(
        "/turn",
        json={"session_id": bob["session_id"], "idempotency_key": "t1", "answer": "1"},
        headers=_bearer(alice["token"]),
    )
    assert response.status_code == 403


def test_student_state_requires_token_and_matching_owner():
    client = _client()
    start = client.post("/session/start", json={"student_id": "alice", "theme": "neutral"}).json()
    sid, skill, token = start["session_id"], start["public_problem"]["skill_id"], start["token"]
    params = {"session_id": sid, "skill_id": skill}

    assert client.get("/student/alice/state", params=params).status_code == 401
    assert client.get("/student/alice/state", params=params, headers=_bearer(token)).status_code == 200
    # a token whose student does not match the path is forbidden
    assert client.get("/student/bob/state", params=params, headers=_bearer(token)).status_code == 403
