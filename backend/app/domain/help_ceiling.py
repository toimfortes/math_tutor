from __future__ import annotations

from backend.app.domain.mastery import SubmissionEvent


def compute_allowed_help_level(submissions: list[SubmissionEvent], *, max_safe_hint_level: int) -> int:
    incorrect_count = sum(1 for submission in submissions if submission.check_result == "incorrect")
    return min(max_safe_hint_level, incorrect_count // 2)
