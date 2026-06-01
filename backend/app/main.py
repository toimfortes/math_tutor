from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from backend.app.api_models import SkillStateModel, TurnResponseModel
from backend.app.config import Settings
from backend.app.content.seed_loader import load_gold_problem_bank
from backend.app.services.attempt_log import SqliteAttemptLog
from backend.app.services.auth import (
    AuthService,
    DuplicateAccountError,
    InMemoryAuthStore,
    InvalidCredentialsError,
    SqliteAuthStore,
)
from backend.app.services.rate_limiter import FixedWindowRateLimiter
from backend.app.services.session_store import SqliteSessionStore, StaleSessionError
from backend.app.services.token_store import InMemoryTokenStore, SqliteTokenStore, TokenRecord
from backend.app.llm.anthropic_client import AnthropicLLMClient
from backend.app.llm.gemini_client import GeminiLLMClient
from backend.app.llm.mock_client import MockLLMClient
from backend.app.llm.types import LLMClient
from backend.app.services.turn import (
    InMemoryTurnStore,
    InvalidSkillError,
    InvalidThemeError,
    SessionNotFoundError,
    TurnResponse,
    TurnService,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StartSessionRequest(BaseModel):
    student_id: NonEmptyStr
    theme: NonEmptyStr = "neutral"


class TurnRequest(BaseModel):
    session_id: NonEmptyStr
    idempotency_key: NonEmptyStr
    answer: NonEmptyStr


class SkipRequest(BaseModel):
    session_id: NonEmptyStr
    reason: NonEmptyStr = "stuck"


class AssessmentRequest(BaseModel):
    session_id: NonEmptyStr
    skill_id: NonEmptyStr
    context_key: NonEmptyStr


class CredentialsRequest(BaseModel):
    student_id: NonEmptyStr
    password: NonEmptyStr


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    app = FastAPI(title=active_settings.app_name)

    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(request: Request, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "session not found"})

    @app.exception_handler(InvalidThemeError)
    async def _invalid_theme(request: Request, exc: InvalidThemeError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "unknown theme"})

    @app.exception_handler(InvalidSkillError)
    async def _invalid_skill(request: Request, exc: InvalidSkillError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "unknown skill"})

    @app.exception_handler(StaleSessionError)
    async def _stale_session(request: Request, exc: StaleSessionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "session was modified concurrently"})

    @app.exception_handler(DuplicateAccountError)
    async def _duplicate_account(request: Request, exc: DuplicateAccountError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "student already registered"})

    @app.exception_handler(InvalidCredentialsError)
    async def _invalid_credentials(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": "invalid credentials"})

    problem_bank = load_gold_problem_bank()
    store = (
        SqliteSessionStore(active_settings.session_db_path, problem_bank.public_problem)
        if active_settings.session_db_path
        else InMemoryTurnStore()
    )
    llm_budget = (
        FixedWindowRateLimiter(limit=active_settings.daily_llm_budget, window_seconds=86_400.0)
        if active_settings.daily_llm_budget is not None
        else None
    )
    attempt_log = SqliteAttemptLog(active_settings.session_db_path) if active_settings.session_db_path else None
    token_store = (
        SqliteTokenStore(active_settings.session_db_path)
        if active_settings.session_db_path
        else InMemoryTokenStore()
    )
    auth_service = AuthService(
        SqliteAuthStore(active_settings.session_db_path)
        if active_settings.session_db_path
        else InMemoryAuthStore()
    )
    turn_service = TurnService(
        problem_bank=problem_bank,
        llm_client=_build_llm_client(active_settings),
        store=store,
        llm_budget=llm_budget,
        attempt_log=attempt_log,
    )
    app.state.turn_service = turn_service
    limiter = (
        FixedWindowRateLimiter(limit=active_settings.rate_limit_per_minute)
        if active_settings.rate_limit_per_minute is not None
        else None
    )

    def _enforce_rate_limit(key: str) -> None:
        if limiter is not None and not limiter.allow(key):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    def require_token(authorization: str | None = Header(default=None)) -> TokenRecord:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        record = token_store.resolve(authorization.removeprefix("Bearer ").strip())
        if record is None:
            raise HTTPException(status_code=401, detail="invalid token")
        return record

    def _require_session(auth: TokenRecord, session_id: str) -> None:
        if auth.session_id != session_id:
            raise HTTPException(status_code=403, detail="token does not own this session")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": active_settings.app_name}

    @app.post("/auth/register", status_code=201)
    def register(request: CredentialsRequest) -> dict:
        auth_service.register(student_id=request.student_id, password=request.password)
        return {"student_id": request.student_id}

    @app.post("/auth/login")
    def login(request: CredentialsRequest) -> dict:
        return {"auth_token": auth_service.login(student_id=request.student_id, password=request.password)}

    @app.post("/session/start", response_model=TurnResponseModel)
    def start_session(request: StartSessionRequest) -> dict:
        _enforce_rate_limit(f"start:{request.student_id}")
        response = turn_service.start_session(student_id=request.student_id, theme=request.theme)
        payload = _turn_response_to_dict(response)
        payload["token"] = token_store.issue(session_id=response.session_id, student_id=request.student_id)
        return payload

    @app.post("/turn", response_model=TurnResponseModel)
    def submit_turn(request: TurnRequest, auth: TokenRecord = Depends(require_token)) -> dict:
        _require_session(auth, request.session_id)
        _enforce_rate_limit(f"turn:{request.session_id}")
        return _turn_response_to_dict(
            turn_service.submit_turn(
                request.session_id,
                idempotency_key=request.idempotency_key,
                answer=request.answer,
            )
        )

    @app.post("/session/skip", response_model=TurnResponseModel)
    def skip_session_problem(request: SkipRequest, auth: TokenRecord = Depends(require_token)) -> dict:
        _require_session(auth, request.session_id)
        _enforce_rate_limit(f"skip:{request.session_id}")
        return _turn_response_to_dict(turn_service.skip_problem(request.session_id, reason=request.reason))

    @app.post("/assessment/transfer", response_model=SkillStateModel)
    def record_transfer(request: AssessmentRequest, auth: TokenRecord = Depends(require_token)) -> dict:
        _require_session(auth, request.session_id)
        _enforce_rate_limit(f"assessment:{request.session_id}")
        return _skill_state_to_dict(
            turn_service.record_transfer(
                request.session_id,
                skill_id=request.skill_id,
                context_key=request.context_key,
            )
        )

    @app.post("/assessment/retention", response_model=SkillStateModel)
    def record_retention(request: AssessmentRequest, auth: TokenRecord = Depends(require_token)) -> dict:
        _require_session(auth, request.session_id)
        _enforce_rate_limit(f"assessment:{request.session_id}")
        return _skill_state_to_dict(
            turn_service.record_retention(
                request.session_id,
                skill_id=request.skill_id,
                context_key=request.context_key,
            )
        )

    @app.get("/student/{student_id}/state", response_model=SkillStateModel)
    def get_student_state(student_id: str, session_id: str, skill_id: str, auth: TokenRecord = Depends(require_token)) -> dict:
        _require_session(auth, session_id)
        if auth.student_id != student_id:
            raise HTTPException(status_code=403, detail="token does not match student")
        return _skill_state_to_dict(turn_service.skill_state(session_id, skill_id=skill_id, student_id=student_id))

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
            "graph": None
            if public.graph is None
            else {
                "kind": public.graph.kind,
                "x_min": public.graph.x_min,
                "x_max": public.graph.x_max,
                "y_min": public.graph.y_min,
                "y_max": public.graph.y_max,
                "points": [[point[0], point[1]] for point in public.graph.points],
                "show_grid": public.graph.show_grid,
            },
            "table": None
            if public.table is None
            else {
                "input_label": public.table.input_label,
                "output_label": public.table.output_label,
                "rows": [[row[0], row[1]] for row in public.table.rows],
            },
            "grid": None
            if public.grid is None
            else {
                "x_min": public.grid.x_min,
                "x_max": public.grid.x_max,
                "y_min": public.grid.y_min,
                "y_max": public.grid.y_max,
                "show_grid": public.grid.show_grid,
            },
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


def _skill_state_to_dict(state) -> dict:
    from backend.app.domain.mastery import is_mastered

    return {
        "skill_id": state.skill_id,
        "attempt_count": len(state.attempts),
        "contexts_seen": sorted(state.contexts_seen),
        "transfer_passed": state.transfer_passed,
        "retention_passed": state.retention_passed,
        "concept_mastered": is_mastered(state),
    }
