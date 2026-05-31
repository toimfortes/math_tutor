from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnService


def build_service() -> TurnService:
    return TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
    )


def test_session_start_returns_server_selected_problem():
    service = build_service()

    response = service.start_session(student_id="student-1", theme="space_logistics")

    assert response.session_id
    assert response.public_problem.ref.realization_key == "space_logistics"
    assert response.public_problem.prompt
    assert response.check_result is None
    assert response.dialogue


def test_turn_submission_uses_code_owned_correctness_and_schedules_next_problem():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    response = service.submit_turn(
        session_id=start.session_id,
        idempotency_key="turn-1",
        answer="(4, 3)",
    )

    assert response.check_result == "correct"
    assert response.xp_awarded == 8
    assert response.public_problem.ref != start.public_problem.ref
    assert response.public_problem.ref.realization_key == "space_logistics"
    assert response.pedagogical_move == "present_next_problem"


def test_turn_submission_is_idempotent_for_same_key():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")

    first = service.submit_turn(start.session_id, idempotency_key="same-key", answer="(4, 3)")
    replay = service.submit_turn(start.session_id, idempotency_key="same-key", answer="wrong")

    assert replay == first
    assert len(service.store.sessions[start.session_id].attempts) == 1


def test_wrong_answer_uses_diagnostic_tag_and_does_not_advance_problem():
    service = build_service()
    start = service.start_session(student_id="student-1", theme="space_logistics")
    service.store.sessions[start.session_id].active_ref = RealizedProblemRef("lf_p04", "neutral")

    response = service.submit_turn(
        start.session_id,
        idempotency_key="wrong-slope",
        answer="1/3",
    )

    assert response.check_result == "incorrect"
    assert response.diagnostic.student_error_tag == "inverted_slope"
    assert response.public_problem.ref == RealizedProblemRef("lf_p04", "neutral")
    assert response.pedagogical_move == "rectify_error"
