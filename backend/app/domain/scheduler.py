from __future__ import annotations

from backend.app.content.seed_loader import ProblemBank, RealizedProblemRef


class RoundRobinScheduler:
    def __init__(self, problem_bank: ProblemBank):
        self.problem_bank = problem_bank
        self.refs = sorted(problem_bank.public_refs(), key=lambda ref: (ref.problem_id, ref.realization_key))

    def first_ref(self, *, theme: str) -> RealizedProblemRef:
        return self._first_matching_theme(theme) or self.refs[0]

    def next_ref(self, current: RealizedProblemRef, *, theme: str) -> RealizedProblemRef:
        themed_refs = [ref for ref in self.refs if ref.realization_key == theme]
        if current in themed_refs:
            index = themed_refs.index(current)
            return themed_refs[(index + 1) % len(themed_refs)]
        return self._first_matching_theme(theme) or self.refs[0]

    def _first_matching_theme(self, theme: str) -> RealizedProblemRef | None:
        return next((ref for ref in self.refs if ref.realization_key == theme), None)
