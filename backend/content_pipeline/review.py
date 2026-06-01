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
DEFAULT_MIN_CORRECTS = 2  # distinct correct problems required before a skill is review-eligible


@dataclass(frozen=True)
class ReviewDue:
    skill_id: str
    last_correct_ts: float
    seconds_since: float


def due_from_mastery(
    mastery: Iterable[tuple[str, float, int]],
    now: float,
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    min_corrects: int = DEFAULT_MIN_CORRECTS,
) -> list[ReviewDue]:
    """Review-due skills for ONE student from per-skill mastery signals.

    `mastery`: (skill_id, last_correct_ts, distinct_correct_count). A skill is due iff
    the student has mastered it (>= `min_corrects` DISTINCT correct problems) AND its most
    recent correct answer is older than `interval_seconds`. Pure and deterministic given
    `(mastery, now)`; most-overdue first.
    """
    items = [
        ReviewDue(skill_id=skill_id, last_correct_ts=last_ts, seconds_since=now - last_ts)
        for skill_id, last_ts, count in mastery
        if count >= min_corrects and now - last_ts >= interval_seconds
    ]
    items.sort(key=lambda d: (-d.seconds_since, d.skill_id))
    return items


def review_due(
    attempts: Iterable[tuple[str, str, str, str, float]],
    now: float,
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    min_corrects: int = DEFAULT_MIN_CORRECTS,
) -> dict[str, list[ReviewDue]]:
    """Per student, the skills mastered but lapsed past `interval_seconds`.

    `attempts`: (student_id, skill_id, problem_id, check_result, ts_epoch). Mastery
    requires >= `min_corrects` DISTINCT correct problems in the skill (so replaying one
    problem cannot qualify it); due only if the most recent correct answer is older than
    the interval (re-mastering recently resets the clock). Multi-student raw-row adapter
    over `due_from_mastery`.
    """
    last_correct: dict[str, dict[str, float]] = defaultdict(dict)
    distinct_correct: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for student_id, skill_id, problem_id, result, ts in attempts:
        if result != "correct" or ts is None:
            continue
        distinct_correct[student_id][skill_id].add(problem_id)
        previous = last_correct[student_id].get(skill_id)
        if previous is None or ts > previous:
            last_correct[student_id][skill_id] = ts

    due: dict[str, list[ReviewDue]] = {}
    for student_id, skills in last_correct.items():
        mastery = [
            (skill_id, ts, len(distinct_correct[student_id][skill_id]))
            for skill_id, ts in skills.items()
        ]
        items = due_from_mastery(mastery, now, interval_seconds=interval_seconds, min_corrects=min_corrects)
        if items:
            due[student_id] = items
    return due
