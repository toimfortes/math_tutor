"""Band-targeted within-skill practice selection (deterministic, read-only).

Turns the offline-frozen difficulty bands into a LIVE ordering of the practice
pool, targeting a desirable-difficulty success band per skill. The student's
level is estimated read-only from their attempt history via a bounded staircase;
nothing here mutates state, calls a clock, or writes item difficulty — so the
calibration feedback loop is structurally impossible (item difficulty stays
frozen and offline-calibrated). Pure functions only: no RNG, no wall-clock.

Two pieces:
- `target_band`: maps one skill's recent (deduped, decidable) attempt history to a
  target difficulty band (1-5) via a median-anchored ±1 staircase, gated on a full
  observation window.
- `order_for_student`: reorders the full practice list so that, WITHIN each skill,
  problems nearest that skill's target band come first; untouched skills keep their
  easiest-first order and their cross-skill position.
"""

from __future__ import annotations

from typing import Iterable

SEED_BAND = 2  # ~62% cold-start seed (Rasch CAT); used only when a skill has no history
RAISE_THRESHOLD = 0.80  # >= this recent accuracy steps the target up (4/5 reaches it)
LOWER_THRESHOLD = 0.50  # <= this steps the target down
WINDOW = 5  # recent decidable attempts considered; movement only when window is full
MIN_BAND = 1
MAX_BAND = 5


def _clamp_band(band: int) -> int:
    return max(MIN_BAND, min(MAX_BAND, band))


def _lower_median(values: list[int]) -> int:
    """Deterministic median; for even counts returns the lower of the two middles."""
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def target_band(recent: list[tuple[int, bool]], *, seed_band: int = SEED_BAND) -> int:
    """Target difficulty band for one skill from its recent decidable history.

    `recent` is the full chronological list of `(difficulty_band, was_correct)` for a
    single skill, already deduped-by-problem and filtered to decidable attempts by the
    caller. This function owns the window slice.

    - empty -> `seed_band`
    - anchor = lower-median band over the last `WINDOW` attempts (order-independent
      within the window, so a single out-of-order outlier cannot leap the target)
    - window not full -> hold at the anchor (no movement on thin evidence)
    - else step +1 if recent accuracy >= RAISE_THRESHOLD, -1 if <= LOWER_THRESHOLD,
      otherwise hold. Result is clamped to [MIN_BAND, MAX_BAND].
    """
    window = list(recent[-WINDOW:])
    if not window:
        return seed_band

    anchor = _lower_median([band for band, _ in window])
    if len(window) < WINDOW:
        return _clamp_band(anchor)

    accuracy = sum(1 for _, correct in window if correct) / len(window)
    if accuracy >= RAISE_THRESHOLD:
        return _clamp_band(anchor + 1)
    if accuracy <= LOWER_THRESHOLD:
        return _clamp_band(anchor - 1)
    return _clamp_band(anchor)


def order_for_student(problems: Iterable[dict], targets: dict[str, int]) -> list[dict]:
    """Reorder the practice list, target-first WITHIN each skill — slot-preserving.

    A skill that has a target has ITS problems reordered by distance from the target
    band (then easier band, then id), but only **within the global slots that skill
    already occupies** in the input. Skills without a target are left byte-identical
    to the input — their problems do not move at all. So the cross-skill layout is
    exactly preserved, and an untouched skill looks identical whether or not other
    skills have history (no fresh-vs-active discontinuity). Pure; the id tiebreak
    makes each per-skill reorder a total order, so output is input-order-independent.
    """
    result = list(problems)
    slots: dict[str, list[int]] = {}
    for index, problem in enumerate(result):
        slots.setdefault(problem["skill_id"], []).append(index)

    for skill_id, target in targets.items():
        indices = slots.get(skill_id)
        if not indices:
            continue
        members = [result[i] for i in indices]
        members.sort(key=lambda p: (abs(p["difficulty"] - target), p["difficulty"], p["id"]))
        for slot, member in zip(indices, members):
            result[slot] = member
    return result
