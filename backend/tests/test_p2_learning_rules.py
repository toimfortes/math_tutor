from backend.app.domain.help_ceiling import compute_allowed_help_level
from backend.app.domain.mastery import (
    ProblemAttempt,
    SubmissionEvent,
    SkillState,
    is_mastered,
    mastery_accuracy,
)
from backend.app.domain.xp import compute_xp_award


def test_mastery_accuracy_uses_first_decidable_submission_per_problem_attempt():
    attempts = [
        ProblemAttempt(
            problem_attempt_id="a1",
            skill_id="lin_slope_two_points",
            submissions=[
                SubmissionEvent(check_result="incorrect", hint_level=0),
                SubmissionEvent(check_result="correct", hint_level=1, self_correction=True),
            ],
        ),
        ProblemAttempt(
            problem_attempt_id="a2",
            skill_id="lin_slope_two_points",
            submissions=[
                SubmissionEvent(check_result="undecidable", hint_level=0),
                SubmissionEvent(check_result="correct", hint_level=0),
            ],
        ),
    ]

    assert mastery_accuracy(attempts) == 0.5


def test_mastery_requires_accuracy_low_hint_context_transfer_and_retention():
    attempts = [
        ProblemAttempt(problem_attempt_id=f"a{i}", skill_id="skill", submissions=[SubmissionEvent(check_result="correct", hint_level=0)])
        for i in range(5)
    ]
    state = SkillState(
        skill_id="skill",
        attempts=attempts,
        contexts_seen={"neutral:table", "space_logistics:word"},
        transfer_passed=True,
        retention_passed=True,
    )

    assert is_mastered(state) is True

    state_without_transfer = SkillState(
        skill_id="skill",
        attempts=attempts,
        contexts_seen={"neutral:table", "space_logistics:word"},
        transfer_passed=False,
        retention_passed=True,
    )
    assert is_mastered(state_without_transfer) is False


def test_xp_is_deduped_per_problem_attempt():
    attempt = ProblemAttempt(
        problem_attempt_id="a1",
        skill_id="skill",
        submissions=[
            SubmissionEvent(check_result="correct", hint_level=0),
            SubmissionEvent(check_result="correct", hint_level=0),
        ],
        transfer_credit=True,
    )

    first_award = compute_xp_award(attempt, already_awarded=False)
    duplicate_award = compute_xp_award(attempt, already_awarded=True)

    assert first_award.points == 13
    assert duplicate_award.points == 0
    assert "deduped" in duplicate_award.reason


def test_undecidable_only_attempt_does_not_award_xp():
    attempt = ProblemAttempt(
        problem_attempt_id="a1",
        skill_id="skill",
        submissions=[SubmissionEvent(check_result="undecidable", hint_level=0)],
    )

    award = compute_xp_award(attempt, already_awarded=False)

    assert award.points == 0
    assert award.reason == "undecidable"


def test_help_ceiling_escalates_after_two_same_problem_failures():
    submissions = [
        SubmissionEvent(check_result="incorrect", hint_level=0),
        SubmissionEvent(check_result="incorrect", hint_level=0),
    ]

    assert compute_allowed_help_level(submissions, max_safe_hint_level=2) == 1

    more_submissions = submissions + [
        SubmissionEvent(check_result="incorrect", hint_level=1),
        SubmissionEvent(check_result="incorrect", hint_level=1),
    ]
    assert compute_allowed_help_level(more_submissions, max_safe_hint_level=2) == 2

    undecidable_only = [SubmissionEvent(check_result="undecidable", hint_level=0)]
    assert compute_allowed_help_level(undecidable_only, max_safe_hint_level=2) == 0
