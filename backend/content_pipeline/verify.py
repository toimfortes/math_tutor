from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

from backend.app.content.seed_loader import DEFAULT_GOLD_PATH, load_gold_problem_bank
from backend.content_pipeline.safety import check_gold_file
from backend.content_pipeline.templates.linear_functions import LINEAR_FUNCTION_TEMPLATE_CASES, solve_case


@dataclass(frozen=True)
class FrozenBankVerificationReport:
    ok: bool
    problem_count: int
    realization_count: int
    template_case_count: int
    safety_terms: list[str]
    schema_errors: list[str]
    template_errors: list[str]
    role_errors: list[str]
    public_leaks: list[str]
    graph_errors: list[str]


def verify_frozen_gold_bank(path: Path | None = None) -> FrozenBankVerificationReport:
    gold_path = path or DEFAULT_GOLD_PATH
    data = json.loads(gold_path.read_text())
    bank = load_gold_problem_bank(gold_path)
    cases_by_ref = {case.ref: case for case in LINEAR_FUNCTION_TEMPLATE_CASES}
    public_refs = set(bank.public_refs())

    schema_errors = _schema_errors(data)
    template_errors = _template_errors(cases_by_ref, public_refs, bank)
    role_errors = _role_errors(cases_by_ref, public_refs)
    public_leaks = _public_leaks(data)
    graph_errors = _graph_errors(data)
    safety_terms = check_gold_file(gold_path)
    realization_count = sum(1 + len(item.get("themed", {})) for item in data.get("problems", []))
    ok = not (schema_errors or template_errors or role_errors or public_leaks or graph_errors or safety_terms)

    return FrozenBankVerificationReport(
        ok=ok,
        problem_count=len(data.get("problems", [])),
        realization_count=realization_count,
        template_case_count=len(LINEAR_FUNCTION_TEMPLATE_CASES),
        safety_terms=safety_terms,
        schema_errors=schema_errors,
        template_errors=template_errors,
        role_errors=role_errors,
        public_leaks=public_leaks,
        graph_errors=graph_errors,
    )


def _schema_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("domain") != "linear_functions":
        errors.append("domain must be linear_functions")
    if not data.get("problems"):
        errors.append("problems must be non-empty")

    for item in data.get("problems", []):
        problem_id = item.get("id", "<missing>")
        for field in ("skill_id", "answer_type", "checker", "representations", "hint_scaffold", "neutral"):
            if field not in item:
                errors.append(f"{problem_id}: missing {field}")
        scaffold = item.get("hint_scaffold", {})
        for field in ("max_safe_hint_level", "level_0", "level_1", "level_2"):
            if field not in scaffold:
                errors.append(f"{problem_id}: missing hint_scaffold.{field}")
        if scaffold.get("max_safe_hint_level", 99) > 2:
            errors.append(f"{problem_id}: max_safe_hint_level must not exceed 2")
        for realization_key, realization in _realizations(item).items():
            for field in ("prompt", "canonical_answer", "solution_method"):
                if not realization.get(field):
                    errors.append(f"{problem_id}/{realization_key}: missing {field}")
    return errors


def _template_errors(cases_by_ref: dict[Any, Any], public_refs: set[Any], bank: Any) -> list[str]:
    errors: list[str] = []
    case_refs = set(cases_by_ref)
    if case_refs != public_refs:
        missing = sorted(f"{ref.problem_id}/{ref.realization_key}" for ref in public_refs - case_refs)
        extra = sorted(f"{ref.problem_id}/{ref.realization_key}" for ref in case_refs - public_refs)
        errors.extend(f"missing template case {ref}" for ref in missing)
        errors.extend(f"extra template case {ref}" for ref in extra)
    for ref in sorted(case_refs & public_refs, key=lambda value: (value.problem_id, value.realization_key)):
        solved = solve_case(cases_by_ref[ref])
        expected = bank.private_problem(ref).canonical_answer
        if solved != expected:
            errors.append(f"{ref.problem_id}/{ref.realization_key}: solve()={solved!r}, expected {expected!r}")
    return errors


def _role_errors(cases_by_ref: dict[Any, Any], public_refs: set[Any]) -> list[str]:
    errors: list[str] = []
    for ref in sorted(public_refs, key=lambda value: (value.problem_id, value.realization_key)):
        template_case = cases_by_ref.get(ref)
        if not template_case:
            continue
        if not template_case.roles:
            errors.append(f"{ref.problem_id}/{ref.realization_key}: missing role metadata")
        for param in template_case.params:
            if param not in template_case.roles and param not in {"var"}:
                errors.append(f"{ref.problem_id}/{ref.realization_key}: missing role for {param}")
    return errors


GRAPH_ALLOWED_KEYS = {"kind", "x_min", "x_max", "y_min", "y_max", "points", "show_grid"}


def _graph_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for item in data.get("problems", []):
        problem_id = item.get("id", "<missing>")
        has_graph_rep = "graph" in item.get("representations", [])
        graph = item.get("graph")
        if has_graph_rep and graph is None:
            errors.append(f"{problem_id}: graph representation requires a graph payload")
            continue
        if graph is None:
            continue
        if not has_graph_rep:
            errors.append(f"{problem_id}: graph payload requires a graph representation")
        extra_keys = set(graph) - GRAPH_ALLOWED_KEYS
        if extra_keys:
            errors.append(f"{problem_id}: graph payload has disallowed keys {sorted(extra_keys)}")
        missing_keys = GRAPH_ALLOWED_KEYS - set(graph)
        if missing_keys:
            errors.append(f"{problem_id}: graph payload missing keys {sorted(missing_keys)}")
            continue
        if graph["kind"] != "line":
            errors.append(f"{problem_id}: graph kind must be 'line'")
        points = graph["points"]
        if not isinstance(points, list) or len(points) < 2:
            errors.append(f"{problem_id}: graph payload needs at least two points")
        elif not all(isinstance(point, list) and len(point) == 2 for point in points):
            errors.append(f"{problem_id}: graph points must be [x, y] pairs")
        if graph["x_min"] >= graph["x_max"] or graph["y_min"] >= graph["y_max"]:
            errors.append(f"{problem_id}: graph bounds must be ordered (min < max)")
    return errors


def _public_leaks(data: dict[str, Any]) -> list[str]:
    leaks: list[str] = []
    for item in data.get("problems", []):
        problem_id = item.get("id", "<missing>")
        public_text = json.dumps(
            {
                "hint_scaffold": item.get("hint_scaffold", {}),
                "prompts": {key: value.get("prompt", "") for key, value in _realizations(item).items()},
            },
            ensure_ascii=False,
        )
        for realization_key, realization in _realizations(item).items():
            answer = str(realization.get("canonical_answer", "")).strip()
            if not answer:
                continue
            if _has_answer_shaped_leak(public_text, answer):
                leaks.append(f"{problem_id}/{realization_key}: answer-shaped public leak")
            solution_method = str(realization.get("solution_method", "")).strip()
            if solution_method and solution_method in public_text:
                leaks.append(f"{problem_id}/{realization_key}: private solution_method appears in public text")
    return leaks


def _has_answer_shaped_leak(text: str, answer: str) -> bool:
    escaped = re.escape(answer)
    patterns = [
        rf"\bthe answer is\s+{escaped}\b",
        rf"\bfinal answer\s*(is|=)\s*{escaped}\b",
        rf"\bsolution\s*(is|=)\s*{escaped}\b",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _realizations(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {"neutral": item.get("neutral", {}), **item.get("themed", {})}


def main() -> None:
    report = verify_frozen_gold_bank()
    if not report.ok:
        errors = (
            report.schema_errors
            + report.template_errors
            + report.role_errors
            + report.public_leaks
            + report.graph_errors
        )
        if report.safety_terms:
            errors.append(f"unsafe terms: {', '.join(report.safety_terms)}")
        raise SystemExit("\n".join(errors))
    print(
        "frozen gold bank verified: "
        f"{report.problem_count} problems, "
        f"{report.realization_count} realizations, "
        f"{report.template_case_count} template cases"
    )


if __name__ == "__main__":
    main()
