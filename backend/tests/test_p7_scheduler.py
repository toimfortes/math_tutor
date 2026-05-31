from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.domain.scheduler import RoundRobinScheduler


def test_scheduler_selects_transfer_candidate_from_unseen_context():
    scheduler = RoundRobinScheduler(load_gold_problem_bank())

    candidate = scheduler.transfer_ref(
        skill_id="coord_plane_basics",
        contexts_seen={"space_logistics:grid"},
        preferred_theme="drone_physics",
    )

    assert candidate.realization_key == "drone_physics"
    assert candidate != RealizedProblemRef("lf_p01", "space_logistics")


def test_scheduler_selects_retention_review_for_same_skill():
    scheduler = RoundRobinScheduler(load_gold_problem_bank())

    candidate = scheduler.retention_ref(skill_id="lin_slope_two_points", preferred_theme="space_logistics")

    public = scheduler.problem_bank.public_problem(candidate)
    assert public.skill_id == "lin_slope_two_points"
    assert candidate.realization_key == "space_logistics"
