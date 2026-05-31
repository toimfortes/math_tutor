"""Durable session persistence.

Sessions are stored as a single JSON aggregate per row in SQLite (via the
stdlib ``sqlite3`` module — no ORM, no migration tool). Each row carries a
``version`` used for optimistic locking: a save only succeeds against the
version that was loaded, so a stale write is rejected rather than silently
clobbering a newer state.

The idempotency cache holds full ``TurnResponse`` objects whose
``public_problem`` is a rich ``PublicProblem``. Rather than serialize that, we
persist only the problem ref and rebuild the ``PublicProblem`` from the gold
bank on load via the injected ``public_resolver``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable, Protocol

from backend.app.content.seed_loader import PublicProblem, RealizedProblemRef
from backend.app.domain.diagnostic_checker import DiagnosticResult
from backend.app.domain.mastery import ProblemAttempt, SubmissionEvent
from backend.app.services.turn import SessionState, TurnResponse

PublicResolver = Callable[[RealizedProblemRef], PublicProblem]


class StaleSessionError(Exception):
    """Raised when a save loses the optimistic-locking version check."""


class SessionStore(Protocol):
    def create(self, state: SessionState) -> None: ...

    def load(self, session_id: str) -> SessionState: ...

    def save(self, state: SessionState) -> None: ...


class SqliteSessionStore:
    def __init__(self, path: str | Path, public_resolver: PublicResolver):
        self._public_resolver = public_resolver
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "session_id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL)"
        )
        self._conn.commit()

    def create(self, state: SessionState) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, version, data) VALUES (?, ?, ?)",
            (state.session_id, state.version, serialize_session(state)),
        )
        self._conn.commit()

    def load(self, session_id: str) -> SessionState:
        row = self._conn.execute(
            "SELECT version, data FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        version, data = row
        state = deserialize_session(data, self._public_resolver)
        state.version = version
        return state

    def save(self, state: SessionState) -> None:
        next_version = state.version + 1
        cursor = self._conn.execute(
            "UPDATE sessions SET version = ?, data = ? WHERE session_id = ? AND version = ?",
            (next_version, serialize_session(state), state.session_id, state.version),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise StaleSessionError(state.session_id)
        state.version = next_version


def serialize_session(state: SessionState) -> str:
    return json.dumps(
        {
            "session_id": state.session_id,
            "student_id": state.student_id,
            "theme": state.theme,
            "version": state.version,
            "active_ref": _ref_to_dict(state.active_ref),
            "attempts": [_attempt_to_dict(attempt) for attempt in state.attempts],
            "idempotency": {key: _response_to_dict(value) for key, value in state.idempotency.items()},
            "hidden_teacher_checks": state.hidden_teacher_checks,
            "abandoned_refs": [_ref_to_dict(ref) for ref in state.abandoned_refs],
            "skip_events": [
                {"ref": _ref_to_dict(event["ref"]), "reason": event["reason"]} for event in state.skip_events
            ],
            "contexts_seen": sorted(state.contexts_seen),
            "transfer_passed_by_skill": sorted(state.transfer_passed_by_skill),
            "retention_passed_by_skill": sorted(state.retention_passed_by_skill),
        }
    )


def deserialize_session(data: str, public_resolver: PublicResolver) -> SessionState:
    raw = json.loads(data)
    return SessionState(
        session_id=raw["session_id"],
        student_id=raw["student_id"],
        theme=raw["theme"],
        active_ref=_ref_from_dict(raw["active_ref"]),
        attempts=[_attempt_from_dict(attempt) for attempt in raw["attempts"]],
        idempotency={
            key: _response_from_dict(value, public_resolver) for key, value in raw["idempotency"].items()
        },
        hidden_teacher_checks=list(raw["hidden_teacher_checks"]),
        abandoned_refs=[_ref_from_dict(ref) for ref in raw["abandoned_refs"]],
        skip_events=[{"ref": _ref_from_dict(event["ref"]), "reason": event["reason"]} for event in raw["skip_events"]],
        contexts_seen=set(raw["contexts_seen"]),
        transfer_passed_by_skill=set(raw["transfer_passed_by_skill"]),
        retention_passed_by_skill=set(raw["retention_passed_by_skill"]),
        version=raw["version"],
    )


def _ref_to_dict(ref: RealizedProblemRef) -> dict:
    return {"problem_id": ref.problem_id, "realization_key": ref.realization_key}


def _ref_from_dict(raw: dict) -> RealizedProblemRef:
    return RealizedProblemRef(problem_id=raw["problem_id"], realization_key=raw["realization_key"])


def _attempt_to_dict(attempt: ProblemAttempt) -> dict:
    return {
        "problem_attempt_id": attempt.problem_attempt_id,
        "skill_id": attempt.skill_id,
        "submissions": [
            {
                "check_result": submission.check_result,
                "hint_level": submission.hint_level,
                "self_correction": submission.self_correction,
            }
            for submission in attempt.submissions
        ],
        "transfer_credit": attempt.transfer_credit,
        "retention_credit": attempt.retention_credit,
    }


def _attempt_from_dict(raw: dict) -> ProblemAttempt:
    return ProblemAttempt(
        problem_attempt_id=raw["problem_attempt_id"],
        skill_id=raw["skill_id"],
        submissions=[
            SubmissionEvent(
                check_result=submission["check_result"],
                hint_level=submission["hint_level"],
                self_correction=submission["self_correction"],
            )
            for submission in raw["submissions"]
        ],
        transfer_credit=raw["transfer_credit"],
        retention_credit=raw["retention_credit"],
    )


def _response_to_dict(response: TurnResponse) -> dict:
    diagnostic = response.diagnostic
    return {
        "session_id": response.session_id,
        "ref": _ref_to_dict(response.public_problem.ref),
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


def _response_from_dict(raw: dict, public_resolver: PublicResolver) -> TurnResponse:
    diagnostic = raw["diagnostic"]
    return TurnResponse(
        session_id=raw["session_id"],
        public_problem=public_resolver(_ref_from_dict(raw["ref"])),
        dialogue=raw["dialogue"],
        pedagogical_move=raw["pedagogical_move"],
        check_result=raw["check_result"],
        xp_awarded=raw["xp_awarded"],
        diagnostic=None
        if diagnostic is None
        else DiagnosticResult(
            student_error_tag=diagnostic["student_error_tag"],
            confidence=diagnostic["confidence"],
            matched_pattern=diagnostic["matched_pattern"],
            safe_hint_level_cap=diagnostic["safe_hint_level_cap"],
        ),
        proposed_hint_level=raw["proposed_hint_level"],
        guardrail_fires=tuple(raw["guardrail_fires"]),
    )
