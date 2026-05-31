"""Pydantic response models for the public API.

These describe the exact snake_case JSON the endpoints already return, so the
OpenAPI schema (and any generated client) is accurate. Field names match the
hand-built dicts in main.py one-for-one.
"""

from __future__ import annotations

from pydantic import BaseModel


class ProblemRefModel(BaseModel):
    problem_id: str
    realization_key: str


class HintScaffoldModel(BaseModel):
    max_safe_hint_level: int
    level_0: str
    level_1: str
    level_2: str
    level_3: str | None = None


class GraphModel(BaseModel):
    kind: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    points: list[list[float]]
    show_grid: bool


class TableModel(BaseModel):
    input_label: str
    output_label: str
    rows: list[list[float]]


class GridModel(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    show_grid: bool


class PublicProblemModel(BaseModel):
    ref: ProblemRefModel
    skill_id: str
    answer_type: str
    checker: str
    representations: list[str]
    prompt: str
    graph: GraphModel | None = None
    table: TableModel | None = None
    grid: GridModel | None = None
    hint_scaffold: HintScaffoldModel


class DiagnosticModel(BaseModel):
    student_error_tag: str
    confidence: str
    matched_pattern: str | None = None
    safe_hint_level_cap: int


class TurnResponseModel(BaseModel):
    session_id: str
    public_problem: PublicProblemModel
    dialogue: str
    pedagogical_move: str
    check_result: str | None = None
    xp_awarded: int
    proposed_hint_level: int
    guardrail_fires: list[str]
    diagnostic: DiagnosticModel | None = None


class SkillStateModel(BaseModel):
    skill_id: str
    attempt_count: int
    contexts_seen: list[str]
    transfer_passed: bool
    retention_passed: bool
    concept_mastered: bool
