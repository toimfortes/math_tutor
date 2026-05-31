from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SubmissionEvent:
    check_result: str
    hint_level: int
    self_correction: bool = False


@dataclass(frozen=True)
class ProblemAttempt:
    problem_attempt_id: str
    skill_id: str
    submissions: list[SubmissionEvent] = field(default_factory=list)
    transfer_credit: bool = False
    retention_credit: bool = False


@dataclass(frozen=True)
class SkillState:
    skill_id: str
    attempts: list[ProblemAttempt]
    contexts_seen: set[str]
    transfer_passed: bool
    retention_passed: bool


def first_decidable_submission(attempt: ProblemAttempt) -> SubmissionEvent | None:
    for submission in attempt.submissions:
        if submission.check_result in {"correct", "incorrect"}:
            return submission
    return None


def mastery_accuracy(attempts: list[ProblemAttempt]) -> float:
    decidable = [submission for attempt in attempts if (submission := first_decidable_submission(attempt))]
    if not decidable:
        return 0.0
    correct = sum(1 for submission in decidable if submission.check_result == "correct")
    return correct / len(decidable)


def is_mastered(state: SkillState) -> bool:
    decidable_count = sum(1 for attempt in state.attempts if first_decidable_submission(attempt))
    low_hint_correct = any(
        submission.check_result == "correct" and submission.hint_level <= 1
        for attempt in state.attempts
        for submission in attempt.submissions
    )
    return (
        mastery_accuracy(state.attempts) >= 0.9
        and decidable_count >= 5
        and low_hint_correct
        and len(state.contexts_seen) >= 2
        and state.transfer_passed
        and state.retention_passed
    )


def retention_is_due(*, last_correct_at: datetime, now: datetime) -> bool:
    return now - last_correct_at >= timedelta(days=2)
