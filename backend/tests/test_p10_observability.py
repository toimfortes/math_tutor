from __future__ import annotations

import logging

from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnService


def _service(llm_client=None) -> TurnService:
    return TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=llm_client or MockLLMClient(),
        store=InMemoryTurnStore(),
    )


def _record(caplog, message: str):
    return next(record for record in caplog.records if record.msg == message)


def test_session_start_emits_structured_log(caplog):
    service = _service()

    with caplog.at_level(logging.INFO, logger="math_tutor.turn"):
        start = service.start_session(student_id="stu", theme="space_logistics")

    record = _record(caplog, "session_started")
    assert record.session_id == start.session_id
    assert record.student_id == "stu"
    assert record.theme == "space_logistics"
    assert record.skill_id == start.public_problem.skill_id


def test_turn_submission_emits_structured_log_with_grading_outcome(caplog):
    service = _service()
    start = service.start_session(student_id="stu", theme="space_logistics")

    with caplog.at_level(logging.INFO, logger="math_tutor.turn"):
        service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")

    record = _record(caplog, "turn_submitted")
    assert record.session_id == start.session_id
    assert record.check_result == "correct"
    assert record.xp_awarded >= 0
    assert record.llm_error is False
    assert isinstance(record.guardrail_fires, list)


def test_turn_log_flags_llm_failure(caplog):
    class FailingLLM:
        def generate(self, **kwargs):
            raise RuntimeError("provider down")

    service = _service(FailingLLM())
    start = service.start_session(student_id="stu", theme="space_logistics")

    with caplog.at_level(logging.INFO, logger="math_tutor.turn"):
        service.submit_turn(start.session_id, idempotency_key="t1", answer="(4, 3)")

    record = _record(caplog, "turn_submitted")
    assert record.llm_error is True
