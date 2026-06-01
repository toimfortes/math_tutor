"""Empirical-Bayes difficulty calibration.

Refines each item's heuristic prior with observed first-attempt outcomes via Beta
shrinkage: the prior dominates when responses are few and washes out continuously
as they accrue (the research-endorsed continuous blend — no hard heuristic->IRT
switch). It is a count aggregate, so it is fully order-independent (true
determinism, no Elo path artifact) and carries no student model (so no
decaying-K freeze, cold-start-ability noise, or scale-drift problems).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

PRIOR_STRENGTH = 12.0
_DIFF_MIN = -3.0
_DIFF_MAX = 3.0


@dataclass(frozen=True)
class Calibrated:
    difficulty: float
    responses: int
    prior: float
    calibrated: bool
    undecidable: int


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return 0.0  # a malformed/non-finite prior is treated as neutral, not max-hard
    return max(_DIFF_MIN, min(_DIFF_MAX, value))


def calibrate(
    first_attempts: Iterable[tuple[str, str]],
    priors: dict[str, float],
    *,
    prior_strength: float = PRIOR_STRENGTH,
) -> dict[str, Calibrated]:
    """Calibrate item difficulty from first-attempt outcomes.

    `first_attempts`: (item_id, outcome) pairs, ALREADY deduped to one strict
    first attempt per (student, item) by the caller; outcome in
    {"correct","incorrect","undecidable"}. `priors`: item_id -> prior logit.
    """
    if not math.isfinite(prior_strength) or prior_strength <= 0:
        raise ValueError("prior_strength must be a finite value > 0")

    corrects: dict[str, int] = defaultdict(int)
    decidable: dict[str, int] = defaultdict(int)
    undecided: dict[str, int] = defaultdict(int)
    for item_id, outcome in first_attempts:
        # Only correct/incorrect count toward the pass-rate; anything else
        # (undecidable, None, unknown) is treated as a skipped/undecidable data
        # point rather than silently counted as incorrect.
        if outcome == "correct":
            decidable[item_id] += 1
            corrects[item_id] += 1
        elif outcome == "incorrect":
            decidable[item_id] += 1
        else:
            undecided[item_id] += 1

    result: dict[str, Calibrated] = {}
    for item_id in set(priors) | set(decidable) | set(undecided):
        prior_logit = _clamp(priors.get(item_id, 0.0))
        n = decidable[item_id]
        if n == 0:
            result[item_id] = Calibrated(
                difficulty=prior_logit, responses=0, prior=prior_logit, calibrated=False, undecidable=undecided[item_id]
            )
            continue
        p0 = _sigmoid(-prior_logit)
        p_hat = (corrects[item_id] + prior_strength * p0) / (n + prior_strength)
        result[item_id] = Calibrated(
            difficulty=_clamp(-_logit(p_hat)),
            responses=n,
            prior=prior_logit,
            calibrated=True,
            undecidable=undecided[item_id],
        )
    return result
