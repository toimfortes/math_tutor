from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.domain.mastery import (
    ProblemAttempt,
    SkillState,
    SubmissionEvent,
    is_mastered,
    retention_is_due,
)
from backend.app.llm.mock_client import MockLLMClient
from backend.app.main import create_app
from backend.app.services.turn import InMemoryTurnStore, TurnService


def build_service() -> TurnService:
    return TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
    )


def test_skip_marks_active_problem_abandoned_and_schedules_new_problem():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    response = service.skip_problem(start.session_id, reason="stuck")

    state = service.store.sessions[start.session_id]
    assert response.public_problem.ref != start.public_problem.ref
    assert response.check_result is None
    assert state.abandoned_refs == [start.public_problem.ref]
    assert state.skip_events[0]["reason"] == "stuck"


def test_transfer_and_retention_events_update_skill_state_until_mastered():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    skill_id = start.public_problem.skill_id
    attempts = [
        ProblemAttempt(
            problem_attempt_id=f"a{i}",
            skill_id=skill_id,
            submissions=[SubmissionEvent(check_result="correct", hint_level=0)],
        )
        for i in range(5)
    ]
    state = service.store.sessions[start.session_id]
    state.attempts.extend(attempts)
    state.contexts_seen.update({"space_logistics:grid", "space_logistics:word"})

    before = service.skill_state(start.session_id, skill_id=skill_id)
    assert before.transfer_passed is False
    assert before.retention_passed is False
    assert is_mastered(before) is False

    transfer = service.record_transfer(start.session_id, skill_id=skill_id, context_key="drone_physics:word")
    retention = service.record_retention(start.session_id, skill_id=skill_id, context_key="space_logistics:delayed")

    assert transfer.transfer_passed is True
    assert retention.retention_passed is True
    assert is_mastered(retention) is True


def test_retention_due_requires_two_day_delay():
    now = datetime(2026, 5, 31, tzinfo=timezone.utc)

    assert retention_is_due(last_correct_at=now - timedelta(days=2), now=now) is True
    assert retention_is_due(last_correct_at=now - timedelta(days=1, hours=23), now=now) is False


def test_p7_api_endpoints_expose_skip_transfer_retention_and_state(login):
    app = create_app()
    client = TestClient(app)

    start = client.post(
        "/session/start", json={"theme": "space_logistics"}, headers=login(client, "student-1")
    ).json()
    session_id = start["session_id"]
    skill_id = start["public_problem"]["skill_id"]
    auth = {"Authorization": f"Bearer {start['token']}"}

    skip = client.post("/session/skip", json={"session_id": session_id, "reason": "stuck"}, headers=auth)
    transfer = client.post(
        "/assessment/transfer",
        json={"session_id": session_id, "skill_id": skill_id, "context_key": "drone_physics:word"},
        headers=auth,
    )
    retention = client.post(
        "/assessment/retention",
        json={"session_id": session_id, "skill_id": skill_id, "context_key": "space_logistics:delayed"},
        headers=auth,
    )
    state = client.get(
        f"/student/student-1/state", params={"session_id": session_id, "skill_id": skill_id}, headers=auth
    )

    assert skip.status_code == 200
    assert skip.json()["public_problem"]["ref"] != start["public_problem"]["ref"]
    assert transfer.status_code == 200
    assert transfer.json()["transfer_passed"] is True
    assert retention.status_code == 200
    assert retention.json()["retention_passed"] is True
    assert state.status_code == 200
    assert state.json()["skill_id"] == skill_id
