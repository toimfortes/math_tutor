from __future__ import annotations

from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.main import _turn_response_to_dict
from backend.app.services.turn import TurnResponse


def _turn_response_for(problem_id: str) -> TurnResponse:
    bank = load_gold_problem_bank()
    public = bank.public_problem(RealizedProblemRef(problem_id, "neutral"))
    return TurnResponse(
        session_id="s1",
        public_problem=public,
        dialogue="Here is the next problem.",
        pedagogical_move="present_next_problem",
        check_result=None,
        xp_awarded=0,
    )


def test_turn_response_serializes_graph_payload():
    data = _turn_response_to_dict(_turn_response_for("lf_p07"))

    graph = data["public_problem"]["graph"]
    assert graph["kind"] == "line"
    assert graph["points"] == [[0, 0], [1, 2]]
    assert graph["show_grid"] is True
    assert graph["x_min"] < graph["x_max"]
    assert graph["y_min"] < graph["y_max"]
    # the public graph payload must never carry answer metadata.
    assert "canonical_answer" not in graph
    assert "solution_method" not in graph


def test_turn_response_omits_graph_for_text_problems():
    data = _turn_response_to_dict(_turn_response_for("lf_p09"))

    assert data["public_problem"]["graph"] is None
