import pytest

from backend.app.content.seed_loader import (
    RealizedProblemRef,
    load_gold_problem_bank,
)
from backend.app.domain.answer_normalizer import normalize_answer
from backend.app.domain.checker import check_answer
from backend.app.domain.diagnostic_checker import diagnose_answer


def test_normalizer_handles_student_notation():
    assert normalize_answer("the answer is −3 litres", answer_type="numeric").normalized == "-3"
    assert normalize_answer("I think ¾", answer_type="numeric").normalized == "3/4"
    assert normalize_answer("y = 5d + 20", answer_type="expression").normalized == "5d + 20"
    assert normalize_answer(" ( 4 , 3 ) ", answer_type="ordered_pair").normalized == "(4, 3)"


def test_checker_accepts_equivalent_answers_and_rejects_bad_input():
    assert check_answer("0.75", "3/4", answer_type="numeric").check_result == "correct"
    assert check_answer("5d + 20", "5*d + 20", answer_type="expression", variable="d").check_result == "correct"
    assert check_answer("(4,3)", "(4, 3)", answer_type="ordered_pair").check_result == "correct"
    assert check_answer("banana", "3", answer_type="numeric").check_result == "undecidable"
    assert check_answer("1/3", "3", answer_type="numeric").check_result == "incorrect"


def test_diagnostic_checker_uses_known_wrong_answer_patterns():
    result = diagnose_answer(
        student_answer="1/3",
        canonical_answer="3",
        answer_type="numeric",
        known_wrong_answers={"inverted_slope": "1/3", "sign_error": "-3"},
    )
    assert result.student_error_tag == "inverted_slope"
    assert result.confidence == "high"

    unknown = diagnose_answer(
        student_answer="42",
        canonical_answer="3",
        answer_type="numeric",
        known_wrong_answers={"inverted_slope": "1/3"},
    )
    assert unknown.student_error_tag == "unknown"
    assert unknown.confidence == "low"


def test_gold_seed_loader_binds_public_and_private_realizations():
    bank = load_gold_problem_bank()

    ref = RealizedProblemRef(problem_id="lf_p03", realization_key="space_logistics")
    public_problem = bank.public_problem(ref)
    private_problem = bank.private_problem(ref)

    assert public_problem.ref == private_problem.ref
    assert public_problem.prompt
    assert public_problem.hint_scaffold.max_safe_hint_level <= 2
    assert not hasattr(public_problem, "canonical_answer")
    assert private_problem.canonical_answer == "-15"

    drone_ref = RealizedProblemRef(problem_id="lf_p03", realization_key="drone_physics")
    assert bank.private_problem(drone_ref).canonical_answer == "-10"

    with pytest.raises(KeyError):
        bank.private_problem(RealizedProblemRef(problem_id="lf_p03", realization_key="missing"))
