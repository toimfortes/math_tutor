from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.llm.mock_client import MockLLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnResponse, TurnService


class StartSessionRequest(BaseModel):
    student_id: str
    theme: str = "neutral"


class TurnRequest(BaseModel):
    session_id: str
    idempotency_key: str
    answer: str


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title=active_settings.app_name)
    turn_service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=MockLLMClient(),
        store=InMemoryTurnStore(),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": active_settings.app_name}

    @app.post("/session/start")
    def start_session(request: StartSessionRequest) -> dict:
        return _turn_response_to_dict(
            turn_service.start_session(student_id=request.student_id, theme=request.theme)
        )

    @app.post("/turn")
    def submit_turn(request: TurnRequest) -> dict:
        return _turn_response_to_dict(
            turn_service.submit_turn(
                request.session_id,
                idempotency_key=request.idempotency_key,
                answer=request.answer,
            )
        )

    return app


app = create_app()


def _turn_response_to_dict(response: TurnResponse) -> dict:
    public = response.public_problem
    diagnostic = response.diagnostic
    return {
        "session_id": response.session_id,
        "public_problem": {
            "ref": {
                "problem_id": public.ref.problem_id,
                "realization_key": public.ref.realization_key,
            },
            "skill_id": public.skill_id,
            "answer_type": public.answer_type,
            "checker": public.checker,
            "representations": list(public.representations),
            "prompt": public.prompt,
            "hint_scaffold": {
                "max_safe_hint_level": public.hint_scaffold.max_safe_hint_level,
                "level_0": public.hint_scaffold.level_0,
                "level_1": public.hint_scaffold.level_1,
                "level_2": public.hint_scaffold.level_2,
                "level_3": public.hint_scaffold.level_3,
            },
        },
        "dialogue": response.dialogue,
        "pedagogical_move": response.pedagogical_move,
        "check_result": response.check_result,
        "xp_awarded": response.xp_awarded,
        "proposed_hint_level": response.proposed_hint_level,
        "guardrail_fires": list(response.guardrail_fires),
        "diagnostic": None
        if diagnostic is None
        else {
            "student_error_tag": diagnostic.student_error_tag,
            "confidence": diagnostic.confidence,
            "matched_pattern": diagnostic.matched_pattern,
            "safe_hint_level_cap": diagnostic.safe_hint_level_cap,
        },
    }
