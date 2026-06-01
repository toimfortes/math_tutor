"""Runtime loader for the separate 'extra practice' pool.

The practice bank is generated content that was approved and exported by the
content pipeline (see content_pipeline.ingest.export_practice_bank). It is kept
strictly distinct from the frozen gold assessment bank. At load time each
problem is validated against the code-owned checker (its canonical answer must
round-trip), so a malformed bank fails fast rather than serving bad content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.app.content.seed_loader import HintScaffold
from backend.app.domain.checker import check_answer


@dataclass(frozen=True)
class PracticeProblem:
    id: str
    skill_id: str
    answer_type: str
    checker: str
    representations: tuple[str, ...]
    prompt: str
    hint_scaffold: HintScaffold
    canonical_answer: str
    variable: str | None


class PracticeBank:
    def __init__(self, problems: list[PracticeProblem]):
        self._problems = problems
        self._by_id = {problem.id: problem for problem in problems}

    def public_problems(self) -> list[dict]:
        return [
            {
                "id": problem.id,
                "skill_id": problem.skill_id,
                "answer_type": problem.answer_type,
                "representations": list(problem.representations),
                "prompt": problem.prompt,
                "hint_scaffold": {
                    "max_safe_hint_level": problem.hint_scaffold.max_safe_hint_level,
                    "level_0": problem.hint_scaffold.level_0,
                    "level_1": problem.hint_scaffold.level_1,
                    "level_2": problem.hint_scaffold.level_2,
                    "level_3": problem.hint_scaffold.level_3,
                },
            }
            for problem in self._problems
        ]

    def get(self, problem_id: str) -> PracticeProblem | None:
        return self._by_id.get(problem_id)

    def grade(self, problem_id: str, answer: str) -> str | None:
        problem = self._by_id.get(problem_id)
        if problem is None:
            return None
        return check_answer(
            answer, problem.canonical_answer, answer_type=problem.answer_type, variable=problem.variable
        ).check_result


def load_practice_bank(path: Path | str) -> PracticeBank:
    data = json.loads(Path(path).read_text())
    problems: list[PracticeProblem] = []
    for raw in data.get("problems", []):
        neutral = raw["neutral"]
        canonical = neutral["canonical_answer"]
        variable = (raw.get("params") or {}).get("var")
        # Defensive runtime gate: the stored answer must grade itself as correct.
        if check_answer(canonical, canonical, answer_type=raw["answer_type"], variable=variable).check_result != "correct":
            raise ValueError(f"practice problem {raw['id']} has an answer the checker rejects")
        scaffold = raw["hint_scaffold"]
        problems.append(
            PracticeProblem(
                id=raw["id"],
                skill_id=raw["skill_id"],
                answer_type=raw["answer_type"],
                checker=raw["checker"],
                representations=tuple(raw.get("representations", [])),
                prompt=neutral["prompt"],
                hint_scaffold=HintScaffold(
                    max_safe_hint_level=scaffold["max_safe_hint_level"],
                    level_0=scaffold["level_0"],
                    level_1=scaffold["level_1"],
                    level_2=scaffold["level_2"],
                    level_3=scaffold.get("level_3"),
                ),
                canonical_answer=canonical,
                variable=variable,
            )
        )
    return PracticeBank(problems)
