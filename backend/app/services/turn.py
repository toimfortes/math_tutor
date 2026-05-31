from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from backend.app.content.seed_loader import ProblemBank, PublicProblem, RealizedProblemRef
from backend.app.domain.checker import check_answer
from backend.app.domain.diagnostic_checker import DiagnosticResult, diagnose_answer
from backend.app.domain.help_ceiling import compute_allowed_help_level
from backend.app.domain.mastery import ProblemAttempt, SubmissionEvent
from backend.app.domain.mastery import SkillState
from backend.app.domain.scheduler import RoundRobinScheduler
from backend.app.domain.xp import compute_xp_award
from backend.app.llm.guardrails import GuardrailInput, apply_guardrails
from backend.app.llm.types import LLMClient, LLMResponse


@dataclass
class SessionState:
    session_id: str
    student_id: str
    theme: str
    active_ref: RealizedProblemRef
    attempts: list[ProblemAttempt] = field(default_factory=list)
    idempotency: dict[str, "TurnResponse"] = field(default_factory=dict)
    hidden_teacher_checks: list[dict[str, object]] = field(default_factory=list)
    abandoned_refs: list[RealizedProblemRef] = field(default_factory=list)
    skip_events: list[dict[str, object]] = field(default_factory=list)
    contexts_seen: set[str] = field(default_factory=set)
    transfer_passed_by_skill: set[str] = field(default_factory=set)
    retention_passed_by_skill: set[str] = field(default_factory=set)


@dataclass
class InMemoryTurnStore:
    sessions: dict[str, SessionState] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnResponse:
    session_id: str
    public_problem: PublicProblem
    dialogue: str
    pedagogical_move: str
    check_result: str | None
    xp_awarded: int
    diagnostic: DiagnosticResult | None = None
    proposed_hint_level: int = 0
    guardrail_fires: tuple[str, ...] = ()


class TurnService:
    def __init__(self, *, problem_bank: ProblemBank, llm_client: LLMClient, store: InMemoryTurnStore):
        self.problem_bank = problem_bank
        self.llm_client = llm_client
        self.store = store
        self.scheduler = RoundRobinScheduler(problem_bank)

    def start_session(self, *, student_id: str, theme: str) -> TurnResponse:
        session_id = str(uuid4())
        active_ref = self.scheduler.first_ref(theme=theme)
        state = SessionState(session_id=session_id, student_id=student_id, theme=theme, active_ref=active_ref)
        self.store.sessions[session_id] = state
        public = self.problem_bank.public_problem(active_ref)
        state.contexts_seen.add(_context_key(public))
        llm, llm_guardrail_fires = self._generate_llm(
            check_result=None,
            diagnostic=None,
            presenting_next=True,
            allowed_help_level=0,
            tier="routine",
            context=_llm_context(public_problem=public, check_result=None, allowed_help_level=0),
        )
        private = self.problem_bank.private_problem(active_ref)
        guarded = apply_guardrails(
            GuardrailInput(
                dialogue=llm.dialogue,
                pedagogical_move=llm.pedagogical_move,
                proposed_hint_level=llm.proposed_hint_level,
                allowed_help_level=0,
                canonical_answer=private.canonical_answer,
                banned_strings=[private.canonical_answer],
                concept_mastered=False,
                teacher_check=llm.teacher_check,
            )
        )
        _persist_teacher_check_if_accepted(state, llm.teacher_check, guarded.guardrail_fires)
        return TurnResponse(
            session_id=session_id,
            public_problem=public,
            dialogue=guarded.dialogue,
            pedagogical_move=guarded.pedagogical_move,
            check_result=None,
            xp_awarded=0,
            proposed_hint_level=guarded.proposed_hint_level,
            guardrail_fires=(*llm_guardrail_fires, *guarded.guardrail_fires),
        )

    def submit_turn(self, session_id: str, *, idempotency_key: str, answer: str) -> TurnResponse:
        state = self.store.sessions[session_id]
        if idempotency_key in state.idempotency:
            return state.idempotency[idempotency_key]

        current_ref = state.active_ref
        public = self.problem_bank.public_problem(current_ref)
        state.contexts_seen.add(_context_key(public))
        private = self.problem_bank.private_problem(current_ref)
        check = check_answer(answer, private.canonical_answer, answer_type=public.answer_type, variable=_variable_from_answer(private.canonical_answer))
        diagnostic = diagnose_answer(
            student_answer=answer,
            canonical_answer=private.canonical_answer,
            answer_type=public.answer_type,
            known_wrong_answers=_known_wrong_answers(current_ref),
            variable=_variable_from_answer(private.canonical_answer),
        )
        submission = SubmissionEvent(check_result=check.check_result, hint_level=0)
        attempt = ProblemAttempt(problem_attempt_id=idempotency_key, skill_id=public.skill_id, submissions=[submission])
        state.attempts.append(attempt)
        xp = compute_xp_award(attempt, already_awarded=False).points

        presenting_next = check.check_result == "correct"
        if presenting_next:
            state.active_ref = self.scheduler.next_ref(current_ref, theme=state.theme)

        active_public = self.problem_bank.public_problem(state.active_ref)
        allowed_help = compute_allowed_help_level(attempt.submissions, max_safe_hint_level=active_public.hint_scaffold.max_safe_hint_level)
        llm, llm_guardrail_fires = self._generate_llm(
            check_result=check.check_result,
            diagnostic=diagnostic,
            presenting_next=presenting_next,
            allowed_help_level=allowed_help,
            tier=_tier_for_turn(check.check_result, diagnostic, presenting_next),
            context=_llm_context(
                public_problem=active_public,
                check_result=check.check_result,
                allowed_help_level=allowed_help,
                diagnostic=diagnostic,
            ),
        )
        guarded = apply_guardrails(
            GuardrailInput(
                dialogue=llm.dialogue,
                pedagogical_move=llm.pedagogical_move,
                proposed_hint_level=llm.proposed_hint_level,
                allowed_help_level=allowed_help,
                canonical_answer=private.canonical_answer,
                banned_strings=[private.canonical_answer],
                concept_mastered=False,
                teacher_check=llm.teacher_check,
            )
        )
        _persist_teacher_check_if_accepted(state, llm.teacher_check, guarded.guardrail_fires)
        response = TurnResponse(
            session_id=session_id,
            public_problem=active_public,
            dialogue=guarded.dialogue,
            pedagogical_move=guarded.pedagogical_move,
            check_result=check.check_result,
            xp_awarded=xp,
            diagnostic=diagnostic,
            proposed_hint_level=guarded.proposed_hint_level,
            guardrail_fires=(*llm_guardrail_fires, *guarded.guardrail_fires),
        )
        state.idempotency[idempotency_key] = response
        return response

    def skip_problem(self, session_id: str, *, reason: str) -> TurnResponse:
        state = self.store.sessions[session_id]
        skipped_ref = state.active_ref
        state.abandoned_refs.append(skipped_ref)
        state.skip_events.append({"ref": skipped_ref, "reason": reason})
        state.active_ref = self.scheduler.next_ref(skipped_ref, theme=state.theme)
        public = self.problem_bank.public_problem(state.active_ref)
        state.contexts_seen.add(_context_key(public))
        llm, llm_guardrail_fires = self._generate_llm(
            check_result=None,
            diagnostic=None,
            presenting_next=True,
            allowed_help_level=0,
            tier="routine",
            context=_llm_context(public_problem=public, check_result=None, allowed_help_level=0),
        )
        private = self.problem_bank.private_problem(state.active_ref)
        guarded = apply_guardrails(
            GuardrailInput(
                dialogue=llm.dialogue,
                pedagogical_move=llm.pedagogical_move,
                proposed_hint_level=llm.proposed_hint_level,
                allowed_help_level=0,
                canonical_answer=private.canonical_answer,
                banned_strings=[private.canonical_answer],
                concept_mastered=False,
                teacher_check=llm.teacher_check,
            )
        )
        _persist_teacher_check_if_accepted(state, llm.teacher_check, guarded.guardrail_fires)
        return TurnResponse(
            session_id=session_id,
            public_problem=public,
            dialogue=guarded.dialogue,
            pedagogical_move=guarded.pedagogical_move,
            check_result=None,
            xp_awarded=0,
            proposed_hint_level=guarded.proposed_hint_level,
            guardrail_fires=(*llm_guardrail_fires, *guarded.guardrail_fires),
        )

    def record_transfer(self, session_id: str, *, skill_id: str, context_key: str) -> SkillState:
        state = self.store.sessions[session_id]
        state.contexts_seen.add(context_key)
        state.transfer_passed_by_skill.add(skill_id)
        return self.skill_state(session_id, skill_id=skill_id)

    def record_retention(self, session_id: str, *, skill_id: str, context_key: str) -> SkillState:
        state = self.store.sessions[session_id]
        state.contexts_seen.add(context_key)
        state.retention_passed_by_skill.add(skill_id)
        return self.skill_state(session_id, skill_id=skill_id)

    def skill_state(self, session_id: str, *, skill_id: str) -> SkillState:
        state = self.store.sessions[session_id]
        attempts = [attempt for attempt in state.attempts if attempt.skill_id == skill_id]
        return SkillState(
            skill_id=skill_id,
            attempts=attempts,
            contexts_seen=set(state.contexts_seen),
            transfer_passed=skill_id in state.transfer_passed_by_skill,
            retention_passed=skill_id in state.retention_passed_by_skill,
        )

    def _generate_llm(
        self,
        *,
        check_result: str | None,
        diagnostic: DiagnosticResult | None,
        presenting_next: bool,
        allowed_help_level: int,
        tier: str,
        context: dict[str, object],
    ) -> tuple[LLMResponse, tuple[str, ...]]:
        try:
            return (
                self.llm_client.generate(
                    check_result=check_result,
                    diagnostic=diagnostic,
                    presenting_next=presenting_next,
                    allowed_help_level=allowed_help_level,
                    tier=tier,
                    context=context,
                ),
                (),
            )
        except Exception:
            return _fallback_llm_response(
                check_result=check_result,
                presenting_next=presenting_next,
                allowed_help_level=allowed_help_level,
            ), ("llm_error",)


def _known_wrong_answers(ref: RealizedProblemRef) -> dict[str, str]:
    if ref.problem_id == "lf_p04":
        return {"inverted_slope": "1/3", "sign_error": "-3"}
    return {}


def _fallback_llm_response(
    *, check_result: str | None, presenting_next: bool, allowed_help_level: int
) -> LLMResponse:
    if presenting_next:
        return LLMResponse(
            dialogue="Tutor narration is temporarily unavailable. Work on the problem shown.",
            pedagogical_move="present_next_problem",
            ui_mode="chat",
            proposed_hint_level=0,
        )
    if check_result == "undecidable":
        return LLMResponse(
            dialogue="I could not parse that format. Try a clearer numeric or algebraic form.",
            pedagogical_move="request_clarification",
            ui_mode="chat",
            proposed_hint_level=0,
        )
    return LLMResponse(
        dialogue="Tutor narration is temporarily unavailable. Use the visible hint and try again.",
        pedagogical_move="offer_heuristic_hint",
        ui_mode="chat",
        proposed_hint_level=allowed_help_level,
    )


def _variable_from_answer(answer: str) -> str | None:
    for char in ("x", "d", "t", "k", "S", "A", "F", "v", "P", "H"):
        if char in answer:
            return char
    return None


def _persist_teacher_check_if_accepted(
    state: SessionState, teacher_check: dict[str, object], guardrail_fires: tuple[str, ...]
) -> None:
    if not teacher_check:
        return
    if any(fire.startswith("teacher_check_") for fire in guardrail_fires):
        return
    state.hidden_teacher_checks.append(teacher_check)


def _tier_for_turn(check_result: str, diagnostic: DiagnosticResult, presenting_next: bool) -> str:
    if presenting_next or check_result == "correct":
        return "routine"
    if check_result == "incorrect" and diagnostic.student_error_tag not in {"unknown", "none"}:
        return "hard"
    return "routine"


def _llm_context(
    *,
    public_problem: PublicProblem,
    check_result: str | None,
    allowed_help_level: int,
    diagnostic: DiagnosticResult | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "public_problem": {
            "ref": {
                "problem_id": public_problem.ref.problem_id,
                "realization_key": public_problem.ref.realization_key,
            },
            "skill_id": public_problem.skill_id,
            "answer_type": public_problem.answer_type,
            "representations": list(public_problem.representations),
            "prompt": public_problem.prompt,
            "hint_scaffold": {
                "max_safe_hint_level": public_problem.hint_scaffold.max_safe_hint_level,
                "level_0": public_problem.hint_scaffold.level_0,
                "level_1": public_problem.hint_scaffold.level_1,
                "level_2": public_problem.hint_scaffold.level_2,
                "level_3": public_problem.hint_scaffold.level_3,
            },
        },
        "check_result": check_result,
        "allowed_help_level": allowed_help_level,
        "concept_mastered": False,
    }
    if diagnostic is not None:
        context["diagnostic"] = {
            "student_error_tag": diagnostic.student_error_tag,
            "confidence": diagnostic.confidence,
            "matched_pattern": diagnostic.matched_pattern,
            "safe_hint_level_cap": diagnostic.safe_hint_level_cap,
        }
    return context


def _context_key(public_problem: PublicProblem) -> str:
    representation = public_problem.representations[0] if public_problem.representations else "unknown"
    return f"{public_problem.ref.realization_key}:{representation}"
