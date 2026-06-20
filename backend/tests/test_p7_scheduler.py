from backend.app.content.seed_loader import RealizedProblemRef, load_gold_problem_bank
from backend.app.domain.scheduler import RoundRobinScheduler


def test_next_ref_interleaves_skills_rather_than_blocking():
    bank = load_gold_problem_bank()
    scheduler = RoundRobinScheduler(bank)

    sequence = [scheduler.first_ref(theme="space_logistics")]
    for _ in range(20):
        sequence.append(scheduler.next_ref(sequence[-1], theme="space_logistics"))

    skills = [bank.public_problem(ref).skill_id for ref in sequence]
    # No two consecutive problems share a skill (interleaving, not blocking).
    assert all(skills[i] != skills[i + 1] for i in range(len(skills) - 1))
    # A full pass still covers every skill in the theme.
    assert set(skills) == {bank.public_problem(ref).skill_id for ref in bank.public_refs()}


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
