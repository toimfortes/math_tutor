from __future__ import annotations

from backend.app.content.seed_loader import ProblemBank, load_gold_problem_bank
from backend.app.evals.live_prompt_eval import build_gemini_client
from backend.app.evals.live_llm_smoke import build_gemini_settings
from backend.app.llm.types import LLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnService


def run_turn_smoke(*, problem_bank: ProblemBank, llm_client: LLMClient) -> dict[str, object]:
    service = TurnService(
        problem_bank=problem_bank,
        llm_client=llm_client,
        store=InMemoryTurnStore(),
    )
    start = service.start_session(student_id="live-smoke", theme="space_logistics")
    turn = service.submit_turn(
        start.session_id,
        idempotency_key="live-smoke-turn-1",
        answer="not parseable",
    )
    state = service.store.sessions[start.session_id]
    return {
        "provider_path": "turn_service",
        "session_id_present": bool(start.session_id),
        "start_problem_id": start.public_problem.ref.problem_id,
        "turn_problem_id": turn.public_problem.ref.problem_id,
        "turn_check_result": turn.check_result,
        "pedagogical_move": turn.pedagogical_move,
        "proposed_hint_level": turn.proposed_hint_level,
        "guardrail_fires": list(turn.guardrail_fires),
        "hidden_teacher_checks": len(state.hidden_teacher_checks),
    }


def main() -> None:
    settings = build_gemini_settings()
    client = build_gemini_client(settings)
    report = run_turn_smoke(problem_bank=load_gold_problem_bank(), llm_client=client)
    if report["guardrail_fires"]:
        raise SystemExit(f"live turn smoke guardrail fires: {report['guardrail_fires']}")
    print(
        "live turn smoke passed: "
        f"start={report['start_problem_id']} "
        f"check={report['turn_check_result']} "
        f"move={report['pedagogical_move']} "
        f"hint={report['proposed_hint_level']} "
        f"teacher_checks={report['hidden_teacher_checks']}"
    )


if __name__ == "__main__":
    main()
