from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_app_health_endpoint_boots():
    app = create_app(Settings(app_name="Math Tutor Test"))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Math Tutor Test"}


def test_session_and_turn_endpoints_use_mocked_loop():
    app = create_app(Settings(app_name="Math Tutor Test"))
    client = TestClient(app)

    start = client.post("/session/start", json={"student_id": "student-1", "theme": "space_logistics"})
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["public_problem"]["prompt"]

    turn = client.post(
        "/turn",
        json={
            "session_id": start_body["session_id"],
            "idempotency_key": "turn-1",
            "answer": "(4, 3)",
        },
    )

    assert turn.status_code == 200
    turn_body = turn.json()
    assert turn_body["check_result"] == "correct"
    assert turn_body["xp_awarded"] == 8
    assert turn_body["pedagogical_move"] == "present_next_problem"
