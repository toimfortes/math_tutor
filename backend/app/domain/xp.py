from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.mastery import ProblemAttempt


@dataclass(frozen=True)
class XPAward:
    points: int
    reason: str


def compute_xp_award(attempt: ProblemAttempt, *, already_awarded: bool) -> XPAward:
    if already_awarded:
        return XPAward(0, "deduped")

    points = 0
    reasons: list[str] = []

    first_correct = next((s for s in attempt.submissions if s.check_result == "correct"), None)
    if first_correct:
        points += 5
        reasons.append("correct")
        if first_correct.hint_level == 0:
            points += 3
            reasons.append("no_hint")

    if attempt.transfer_credit:
        points += 5
        reasons.append("transfer")
    if attempt.retention_credit:
        points += 5
        reasons.append("retention")

    if not reasons and attempt.submissions:
        points += 1
        reasons.append("engaged")

    return XPAward(points, ",".join(reasons))
