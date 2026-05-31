import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.content_pipeline.safety import check_gold_file  # noqa: E402

GOLD = ROOT / "backend/content_pipeline/gold/linear_functions.json"
BUILD_PLAN = ROOT / "docs/build-plan.md"
LLM_CONTRACT = ROOT / "docs/llm-contract.md"
PROVIDER_POLICY = ROOT / "docs/provider-policy-sources.md"
CONTENT_SAFETY_REVIEW = ROOT / "docs/content-safety-review.md"
GRAPHVIEW_FALLBACK = ROOT / "docs/graphview-fallback.md"


def test_gold_set_has_no_unsafe_theme_terms():
    assert check_gold_file(GOLD) == []


def test_gold_set_authors_leak_safe_hint_scaffolds():
    data = json.loads(GOLD.read_text())
    for problem in data["problems"]:
        scaffold = problem.get("hint_scaffold")
        assert scaffold, problem["id"]
        assert set(scaffold) >= {"max_safe_hint_level", "level_0", "level_1", "level_2"}
        assert scaffold["max_safe_hint_level"] <= 2

        scaffold_text = " ".join(
            str(scaffold[f"level_{level}"]).lower() for level in range(3)
        )
        variants = [problem["neutral"], *problem["themed"].values()]
        for variant in variants:
            answer = str(variant["canonical_answer"]).lower()
            assert answer not in scaffold_text, (problem["id"], answer)


def test_llm_contract_handles_undecidable_and_child_safety():
    text = LLM_CONTRACT.read_text()
    assert "request_clarification" in text
    assert "CHECK_RESULT" in text and "undecidable" in text
    assert "trusted adult" in text
    assert "self-harm" in text
    assert "content filter" in text
    assert "single-step" in text and "max_safe_hint_level" in text


def test_build_plan_closes_state_machine_and_codegen_gaps():
    text = BUILD_PLAN.read_text()
    assert "check_result IN ('correct', 'incorrect')" in text
    assert "decidable attempts" in text
    assert "request_clarification" in text
    assert "proposed_hint_level=0" in text
    assert "orval.config" in text
    assert "OAuth redirect/callback" in text
    assert "local SVG/canvas graph fallback" in text
    assert "interpretation skills" in text and "weakest" in text


def test_provider_policy_sources_are_pinned_before_llm_use():
    text = PROVIDER_POLICY.read_text()
    assert "Last verified: 2026-05-31" in text
    assert "https://platform.openai.com/docs/guides/your-data" in text
    assert "https://platform.openai.com/docs/guides/safety-checks/under-18-api-guidance" in text
    assert "https://platform.claude.com/docs/en/manage-claude/api-and-data-retention" in text
    assert "P0b decision" in text
    assert "P6 re-check" in text
    assert "Zero Data Retention" in text


def test_semantic_safety_review_is_specified_beyond_denylist():
    text = CONTENT_SAFETY_REVIEW.read_text()
    assert "Semantic Review Prompt" in text
    assert "Banned Register" in text
    assert "Allowlist" in text
    assert "space colony logistics" in text.lower()
    assert "drone / flight motion" in text.lower()
    assert "reject" in text.lower()
    assert "backend/content_pipeline/safety.py" in text


def test_graphview_local_fallback_is_specified_for_v1_graph_items():
    text = GRAPHVIEW_FALLBACK.read_text()
    assert "Local SVG" in text or "local SVG" in text
    assert "Desmos is not required" in text
    assert "lin_slope_from_graph" in text
    assert "lin_y_intercept" in text
    assert "no network" in text.lower()
    assert "P4 gate" in text


def test_realization_binding_and_runtime_prompt_freeze_are_specified():
    text = BUILD_PLAN.read_text()
    assert "(problem_id, realization_key)" in text
    assert "same `RealizedProblemRef`" in text
    assert "no runtime re-narration" in text
    assert "runtime-rendered prompt" in text
    assert "vetted bank string" in text


def test_undecidable_resolution_and_turn_concurrency_are_specified():
    text = BUILD_PLAN.read_text()
    assert "undecidable_retry_count" in text
    assert "numeric sampling fallback" in text
    assert "human review" in text
    assert "optimistic-lock" in text
    assert "idempotency key" in text
    assert "transaction" in text


def test_content_pipeline_ci_boundary_and_product_limits_are_explicit():
    text = BUILD_PLAN.read_text()
    assert "live model generation is not a reproducible CI gate" in text
    assert "frozen artifact" in text
    assert "Known v1 limitation" in text
    assert "does not grade free-form reasoning" in text
    assert "XP is optional" in text
    assert "no streaks" in text
    assert "cache economics" in text


def test_llm_contract_uses_private_teacher_check_not_cot_scratchpad():
    text = LLM_CONTRACT.read_text()
    assert "<teacher_scratchpad>" not in text
    assert "chain-of-thought" in text
    assert "teacher_check" in text
    assert "student_error_tag" in text
    assert "next_scaffold_id" in text
    assert "leak_risk" in text
    assert "uses_only_authored_scaffold" in text
    assert "server-only" in text
    assert "hidden conversation history" in text
    assert "do not persist provider reasoning" in text
    assert "display: \"omitted\"" in text


def test_llm_contract_uses_strict_pedagogical_state_machine():
    text = LLM_CONTRACT.read_text()
    for move in [
        "review_concept",
        "offer_heuristic_hint",
        "rectify_error",
        "request_clarification",
        "reflect",
        "summarize_mastery",
        "present_next_problem",
    ]:
        assert move in text

    for old_move in [
        "ask_question",
        "diagnose_misconception",
        "give_hint",
        "encourage_retry",
    ]:
        assert old_move not in text


def test_turn_orchestration_does_not_hold_db_lock_across_llm_io():
    text = BUILD_PLAN.read_text()
    assert "never hold a DB lock across `LLMClient.generate`" in text
    assert "Phase A" in text and "Phase B" in text
    assert "turn_generation_job" in text
    assert "state_snapshot_id" in text
    assert "stale generation" in text


def test_teacher_check_is_backend_hidden_history_not_frontend_state():
    build = BUILD_PLAN.read_text()
    contract = LLM_CONTRACT.read_text()
    assert "hidden conversation history" in build
    assert "hidden conversation history" in contract
    assert "not exposed to the frontend" in contract
    assert "teacher_check_retention" in build
    assert "pedagogical continuity" in contract


def test_abandon_skip_and_help_escalation_are_deterministic():
    text = BUILD_PLAN.read_text()
    assert "POST /session/skip" in text
    assert "abandoned" in text
    assert "same-problem failed attempts" in text
    assert "increase `allowed_help_level`" in text
    assert "deterministic" in text
    assert "help_ceiling.py" in text


def test_single_digit_answer_leak_limit_is_explicit():
    text = BUILD_PLAN.read_text()
    assert "single-digit answer" in text
    assert "regex cannot prove semantic non-leakage" in text
    assert "live prompt eval" in text
    assert "not a proof" in text


def test_diagnostic_checker_is_the_source_of_misconception_signal():
    text = BUILD_PLAN.read_text()
    contract = LLM_CONTRACT.read_text()
    assert "DiagnosticResult" in text
    assert "diagnostic_checker.py" in text
    assert "linear-functions misconception taxonomy" in text
    assert "known wrong-answer patterns" in text
    assert "inverted_slope" in text
    assert "student_error_tag" in text
    assert "unknown" in contract
    assert "must not choose `rectify_error`" in contract


def test_attempt_accounting_and_xp_dedup_are_defined():
    text = BUILD_PLAN.read_text()
    assert "ProblemAttempt" in text
    assert "SubmissionEvent" in text
    assert "first decidable submission" in text
    assert "self_correction" in text
    assert "XP is awarded at most once per ProblemAttempt" in text
    assert "resubmitting the same correct answer cannot farm XP" in text


def test_transfer_is_student_relative_not_static_content_tag():
    text = BUILD_PLAN.read_text()
    gold = GOLD.read_text()
    assert "transfer_passed is computed relative to `contexts_seen`" in text
    assert "assessment_role='transfer' is a candidate marker" in text
    assert "not sufficient by itself" in text
    assert "already_seen_realization" in text
    assert "candidate marker" in gold


def test_hint_scaffold_ladder_scope_is_explicit():
    text = BUILD_PLAN.read_text()
    assert "structured hint ladder" in text
    assert "level_0" in text and "level_1" in text and "level_2" in text
    assert "level_3" in text
    assert "per-realization override" in text
    assert "theme-neutral shared scaffold" in text
    assert "not synthesize missing levels" in text


def test_input_normalization_and_undecidable_bias_are_explicit():
    text = BUILD_PLAN.read_text()
    assert "answer_normalizer.py" in text
    assert "unicode minus" in text
    assert "prose wrapper stripping" in text
    assert "unit stripping" in text
    assert "messy_input_count" in text
    assert "undecidable rate" in text


def test_mastery_language_and_provider_diversity_limits_are_explicit():
    text = BUILD_PLAN.read_text()
    contract = LLM_CONTRACT.read_text()
    assert "summarize_mastery" in contract
    assert "must not claim mastery" in contract
    assert "concept_mastered=true" in contract
    assert "provider diversity is not statistical independence" in text
    assert "correlated verifier failure" in text
