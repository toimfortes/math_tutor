from __future__ import annotations

from collections import defaultdict

from backend.app.content.seed_loader import ProblemBank, RealizedProblemRef


class RoundRobinScheduler:
    def __init__(self, problem_bank: ProblemBank):
        self.problem_bank = problem_bank
        self.refs = sorted(problem_bank.public_refs(), key=lambda ref: (ref.problem_id, ref.realization_key))
        self._interleaved_cache: dict[str, list[RealizedProblemRef]] = {}

    def first_ref(self, *, theme: str) -> RealizedProblemRef:
        return self._first_matching_theme(theme) or self.refs[0]

    def next_ref(self, current: RealizedProblemRef, *, theme: str) -> RealizedProblemRef:
        # Interleave subskills: consecutive problems should require different
        # strategies (slope vs intercept vs equation vs graph), which has strong
        # RCT evidence over blocked practice (Rohrer 2019, d=0.83).
        order = self._interleaved_order(theme)
        if current in order:
            index = order.index(current)
            return order[(index + 1) % len(order)]
        return self._first_matching_theme(theme) or self.refs[0]

    def _interleaved_order(self, theme: str) -> list[RealizedProblemRef]:
        if theme in self._interleaved_cache:
            return self._interleaved_cache[theme]
        themed = [ref for ref in self.refs if ref.realization_key == theme]
        remaining: dict[str, list[RealizedProblemRef]] = defaultdict(list)
        for ref in themed:
            remaining[self.problem_bank.public_problem(ref).skill_id].append(ref)

        order: list[RealizedProblemRef] = []
        last_skill: str | None = None
        for _ in range(len(themed)):
            available = [(skill, refs) for skill, refs in remaining.items() if refs]
            # Prefer a skill different from the previous one; among the options,
            # take the one with the most remaining (so the schedule stays feasible),
            # breaking ties deterministically by skill id.
            preferred = [pair for pair in available if pair[0] != last_skill] or available
            preferred.sort(key=lambda pair: (-len(pair[1]), pair[0]))
            chosen_skill = preferred[0][0]
            order.append(remaining[chosen_skill].pop(0))
            last_skill = chosen_skill

        self._interleaved_cache[theme] = order
        return order

    def transfer_ref(
        self,
        *,
        skill_id: str,
        contexts_seen: set[str],
        preferred_theme: str,
    ) -> RealizedProblemRef:
        candidates = [ref for ref in self.refs if self.problem_bank.public_problem(ref).skill_id == skill_id]
        themed = [ref for ref in candidates if ref.realization_key == preferred_theme]
        for ref in themed + candidates:
            public = self.problem_bank.public_problem(ref)
            if _context_key(public.ref.realization_key, public.representations) not in contexts_seen:
                return ref
        return themed[0] if themed else candidates[0]

    def retention_ref(self, *, skill_id: str, preferred_theme: str) -> RealizedProblemRef:
        candidates = [ref for ref in self.refs if self.problem_bank.public_problem(ref).skill_id == skill_id]
        themed = [ref for ref in candidates if ref.realization_key == preferred_theme]
        return themed[0] if themed else candidates[0]

    def _first_matching_theme(self, theme: str) -> RealizedProblemRef | None:
        return next((ref for ref in self.refs if ref.realization_key == theme), None)


def _context_key(realization_key: str, representations: tuple[str, ...]) -> str:
    representation = representations[0] if representations else "unknown"
    return f"{realization_key}:{representation}"
