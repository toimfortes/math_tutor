from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GOLD_PATH = ROOT / "backend/content_pipeline/gold/linear_functions.json"


@dataclass(frozen=True)
class RealizedProblemRef:
    problem_id: str
    realization_key: str


@dataclass(frozen=True)
class HintScaffold:
    max_safe_hint_level: int
    level_0: str
    level_1: str
    level_2: str
    level_3: str | None = None


@dataclass(frozen=True)
class GraphSpec:
    kind: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    points: tuple[tuple[float, float], ...]
    show_grid: bool


@dataclass(frozen=True)
class GridSpec:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    show_grid: bool


@dataclass(frozen=True)
class TableSpec:
    input_label: str
    output_label: str
    rows: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PublicProblem:
    ref: RealizedProblemRef
    skill_id: str
    answer_type: str
    checker: str
    representations: tuple[str, ...]
    prompt: str
    hint_scaffold: HintScaffold
    graph: GraphSpec | None = None
    table: TableSpec | None = None
    grid: GridSpec | None = None


@dataclass(frozen=True)
class PrivateProblem:
    ref: RealizedProblemRef
    canonical_answer: str
    solution_method: str


class ProblemBank:
    def __init__(self, public: dict[RealizedProblemRef, PublicProblem], private: dict[RealizedProblemRef, PrivateProblem]):
        self._public = public
        self._private = private

    def public_problem(self, ref: RealizedProblemRef) -> PublicProblem:
        return self._public[ref]

    def private_problem(self, ref: RealizedProblemRef) -> PrivateProblem:
        private = self._private[ref]
        if ref not in self._public:
            raise KeyError(ref)
        return private

    def public_refs(self) -> tuple[RealizedProblemRef, ...]:
        return tuple(self._public)


def load_gold_problem_bank(path: Path | None = None) -> ProblemBank:
    gold_path = path or DEFAULT_GOLD_PATH
    data = json.loads(gold_path.read_text())
    public: dict[RealizedProblemRef, PublicProblem] = {}
    private: dict[RealizedProblemRef, PrivateProblem] = {}

    for item in data["problems"]:
        scaffold = HintScaffold(**item["hint_scaffold"])
        graph = _parse_graph(item.get("graph"))
        grid = _parse_grid(item.get("grid"))
        realizations = {"neutral": item["neutral"], **item.get("themed", {})}
        for realization_key, realization in realizations.items():
            ref = RealizedProblemRef(problem_id=item["id"], realization_key=realization_key)
            public[ref] = PublicProblem(
                ref=ref,
                skill_id=item["skill_id"],
                answer_type=item["answer_type"],
                checker=item["checker"],
                representations=tuple(item["representations"]),
                prompt=realization["prompt"],
                hint_scaffold=scaffold,
                graph=graph,
                table=_parse_table(realization.get("table")),
                grid=grid,
            )
            private[ref] = PrivateProblem(
                ref=ref,
                canonical_answer=realization["canonical_answer"],
                solution_method=realization["solution_method"],
            )

    return ProblemBank(public, private)


def _parse_graph(raw: dict | None) -> GraphSpec | None:
    if raw is None:
        return None
    return GraphSpec(
        kind=raw["kind"],
        x_min=raw["x_min"],
        x_max=raw["x_max"],
        y_min=raw["y_min"],
        y_max=raw["y_max"],
        points=tuple((point[0], point[1]) for point in raw["points"]),
        show_grid=raw["show_grid"],
    )


def _parse_grid(raw: dict | None) -> GridSpec | None:
    if raw is None:
        return None
    return GridSpec(
        x_min=raw["x_min"],
        x_max=raw["x_max"],
        y_min=raw["y_min"],
        y_max=raw["y_max"],
        show_grid=raw["show_grid"],
    )


def _parse_table(raw: dict | None) -> TableSpec | None:
    if raw is None:
        return None
    return TableSpec(
        input_label=raw["input_label"],
        output_label=raw["output_label"],
        rows=tuple((row[0], row[1]) for row in raw["rows"]),
    )
