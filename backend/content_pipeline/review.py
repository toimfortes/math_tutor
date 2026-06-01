"""Offline spaced-review recommender.

Uses the real cross-session timestamps already in the append-only attempt log to
flag skills a student mastered (answered correctly) but has since let lapse past
a spacing interval. Runs OFFLINE (no clock in the hot path, no submit_turn or
scheduler change) and is deterministic given (attempts, now). Works entirely in
epoch seconds, so it is timezone-agnostic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

DEFAULT_INTERVAL_SECONDS = 2 * 86400.0  # 2 days


@dataclass(frozen=True)
class ReviewDue:
    skill_id: str
    last_correct_ts: float
    seconds_since: float


def review_due(
    attempts: Iterable[tuple[str, str, str, float]],
    now: float,
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> dict[str, list[ReviewDue]]:
    """Per student, the skills mastered but lapsed past `interval_seconds`.

    `attempts`: (student_id, skill_id, check_result, ts_epoch). A skill is due
    only if the student's MOST RECENT correct answer on it is older than the
    interval (re-mastering it recently resets the clock). Never-correct skills
    are not due.
    """
    last_correct: dict[str, dict[str, float]] = defaultdict(dict)
    for student_id, skill_id, result, ts in attempts:
        if result != "correct" or ts is None:
            continue
        previous = last_correct[student_id].get(skill_id)
        if previous is None or ts > previous:
            last_correct[student_id][skill_id] = ts

    due: dict[str, list[ReviewDue]] = {}
    for student_id, skills in last_correct.items():
        items = [
            ReviewDue(skill_id=skill_id, last_correct_ts=ts, seconds_since=now - ts)
            for skill_id, ts in skills.items()
            if now - ts >= interval_seconds
        ]
        if items:
            items.sort(key=lambda d: (-d.seconds_since, d.skill_id))  # most overdue first, deterministic
            due[student_id] = items
    return due
