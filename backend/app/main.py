from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.llm.anthropic_client import AnthropicLLMClient
from backend.app.llm.gemini_client import GeminiLLMClient
from backend.app.llm.mock_client import MockLLMClient
from backend.app.llm.types import LLMClient
from backend.app.services.turn import InMemoryTurnStore, TurnResponse, TurnService


class StartSessionRequest(BaseModel):
    student_id: str
    theme: str = "neutral"


class TurnRequest(BaseModel):
    session_id: str
    idempotency_key: str
    answer: str


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    app = FastAPI(title=active_settings.app_name)
    turn_service = TurnService(
        problem_bank=load_gold_problem_bank(),
        llm_client=_build_llm_client(active_settings),
        store=InMemoryTurnStore(),
    )
    app.state.turn_service = turn_service

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


def _build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "mock":
        return MockLLMClient()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            routine_model=settings.anthropic_routine_model,
            hard_model=settings.anthropic_hard_model,
            top_model=settings.anthropic_top_model,
            routing_mode=settings.llm_routing_mode,
            api_url=settings.anthropic_api_url,
            anthropic_version=settings.anthropic_version,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if settings.llm_provider == "gemini":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")
        return GeminiLLMClient(
            api_key=settings.google_api_key,
            model=settings.gemini_model,
            routine_model=settings.gemini_routine_model,
            hard_model=settings.gemini_hard_model,
            top_model=settings.gemini_top_model,
            routing_mode=settings.llm_routing_mode,
            api_url=settings.gemini_api_url,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")


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
