from __future__ import annotations

import json

from backend.app.content.seed_loader import (
    DEFAULT_GOLD_PATH,
    RealizedProblemRef,
    load_gold_problem_bank,
)
from backend.content_pipeline.templates.linear_functions import (
    LINEAR_FUNCTION_TEMPLATE_CASES,
    known_wrong_answers,
    solve_case,
)
from backend.content_pipeline.verify import verify_frozen_gold_bank


def test_templates_reproduce_every_gold_realization_answer():
    bank = load_gold_problem_bank()
    cases_by_ref = {case.ref: case for case in LINEAR_FUNCTION_TEMPLATE_CASES}

    assert set(cases_by_ref) == set(bank.public_refs())
    for ref, case in cases_by_ref.items():
        assert solve_case(case) == bank.private_problem(ref).canonical_answer


def test_templates_carry_role_metadata_and_diagnostic_distractors():
    slope_case = next(
        case
        for case in LINEAR_FUNCTION_TEMPLATE_CASES
        if case.problem_id == "lf_p04" and case.realization_key == "neutral"
    )

    assert slope_case.roles["x1"] == "first input"
    assert slope_case.roles["y2"] == "second output"
    assert known_wrong_answers(slope_case)["inverted_slope"] == "1/3"
    assert known_wrong_answers(slope_case)["sign_error"] == "-3"


def test_frozen_gold_bank_verifier_runs_deterministic_ci_checks():
    report = verify_frozen_gold_bank()

    assert report.ok
    assert report.problem_count == 16
    assert report.realization_count == 48
    assert report.template_case_count == 48
    assert report.safety_terms == []
    assert report.public_leaks == []
    assert report.graph_errors == []
    assert report.table_errors == []
    assert report.grid_errors == []


def test_graph_problems_expose_public_safe_graph_payload():
    bank = load_gold_problem_bank()

    for problem_id in ("lf_p07", "lf_p08", "lf_p10"):
        public = bank.public_problem(RealizedProblemRef(problem_id, "neutral"))
        assert "graph" in public.representations
        assert public.graph is not None
        assert public.graph.kind == "line"
        assert len(public.graph.points) >= 2
        assert public.graph.x_min < public.graph.x_max
        assert public.graph.y_min < public.graph.y_max

    # graph geometry is theme-independent, so themed realizations share it.
    themed = bank.public_problem(RealizedProblemRef("lf_p07", "drone_physics"))
    assert themed.graph == bank.public_problem(RealizedProblemRef("lf_p07", "neutral")).graph

    # text-only problems carry no graph payload.
    assert bank.public_problem(RealizedProblemRef("lf_p09", "neutral")).graph is None


def test_verifier_flags_graph_representation_without_payload(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p07":
            del item["graph"]
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p07" in error for error in report.graph_errors)


def test_verifier_flags_graph_payload_with_answer_metadata(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p07":
            item["graph"]["canonical_answer"] = "2"
    broken = tmp_path / "leaky.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p07" in error for error in report.graph_errors)


def test_grid_problem_exposes_a_pointless_grid_payload():
    bank = load_gold_problem_bank()

    p01 = bank.public_problem(RealizedProblemRef("lf_p01", "neutral"))
    assert "grid" in p01.representations
    assert p01.grid is not None
    assert p01.grid.x_min < p01.grid.x_max
    assert p01.grid.y_min < p01.grid.y_max
    # the plot-a-point answer must NOT be embedded: a grid payload carries no points.
    assert not hasattr(p01.grid, "points")

    # non-grid problems carry no grid payload.
    assert bank.public_problem(RealizedProblemRef("lf_p09", "neutral")).grid is None


def test_verifier_flags_grid_representation_without_payload(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p01":
            del item["grid"]
    broken = tmp_path / "broken_grid.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p01" in error for error in report.grid_errors)


def test_verifier_flags_grid_payload_carrying_points(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p01":
            item["grid"]["points"] = [[4, 3]]
    broken = tmp_path / "leaky_grid.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p01" in error for error in report.grid_errors)


def test_table_problems_expose_public_safe_table_payload():
    bank = load_gold_problem_bank()

    p02 = bank.public_problem(RealizedProblemRef("lf_p02", "neutral"))
    assert "table" in p02.representations
    assert p02.table is not None
    assert p02.table.input_label
    assert p02.table.output_label
    assert p02.table.rows[0] == (0, 50)
    assert len(p02.table.rows) == 4

    # table data is per-realization: the drone variant of lf_p03 differs.
    neutral = bank.public_problem(RealizedProblemRef("lf_p03", "neutral"))
    drone = bank.public_problem(RealizedProblemRef("lf_p03", "drone_physics"))
    assert neutral.table is not None and drone.table is not None
    assert drone.table.rows != neutral.table.rows

    # text-only problems carry no table payload.
    assert bank.public_problem(RealizedProblemRef("lf_p09", "neutral")).table is None


def test_two_point_problems_expose_graph_payload_without_a_graph_tag():
    bank = load_gold_problem_bank()

    p04 = bank.public_problem(RealizedProblemRef("lf_p04", "neutral"))
    assert p04.graph is not None
    assert p04.graph.points == ((1, 4), (5, 16))
    # the payload visualizes the two given points; the representation stays
    # "points"/"equation" (it is not a read-from-graph problem).
    assert "graph" not in p04.representations

    # all four two-point problems carry a payload.
    for problem_id in ("lf_p04", "lf_p05", "lf_p06", "lf_p12"):
        assert bank.public_problem(RealizedProblemRef(problem_id, "neutral")).graph is not None


def test_verifier_flags_table_representation_without_payload(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p02":
            del item["neutral"]["table"]
    broken = tmp_path / "broken_table.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p02" in error for error in report.table_errors)


def test_verifier_flags_table_payload_with_answer_metadata(tmp_path):
    data = json.loads(DEFAULT_GOLD_PATH.read_text())
    for item in data["problems"]:
        if item["id"] == "lf_p02":
            item["neutral"]["table"]["canonical_answer"] = "30"
    broken = tmp_path / "leaky_table.json"
    broken.write_text(json.dumps(data))

    report = verify_frozen_gold_bank(broken)

    assert not report.ok
    assert any("lf_p02" in error for error in report.table_errors)
