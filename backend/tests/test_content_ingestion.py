from __future__ import annotations

import json
import sqlite3

from backend.app.content.seed_loader import DEFAULT_GOLD_PATH
from backend.content_pipeline.ingest import (
    DeploymentMode,
    DEFAULT_OER_MANIFEST_PATH,
    connect_content_db,
    export_gold_bank,
    export_practice_bank,
    generate_candidates,
    ingest_oer_manifest,
    ingest_gold_bank,
    is_license_allowed,
    promote_candidates,
    verify_practice_bank,
)
from backend.content_pipeline.verify import verify_frozen_gold_bank


def _staged_db(tmp_path, per_skill=5):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    generate_candidates(db_path, per_skill=per_skill)
    return db_path


def test_promote_approves_candidates_but_keeps_runtime_bank_frozen(tmp_path):
    db_path = _staged_db(tmp_path)
    export_path = tmp_path / "linear_functions.exported.json"

    summary = promote_candidates(db_path, promoted_at="2026-06-01T00:00:00Z")

    assert summary.promoted > 0
    assert summary.rejected == 0
    assert summary.verifier_ok is True

    with connect_content_db(db_path) as conn:
        statuses = dict(conn.execute("SELECT curation_status, COUNT(*) FROM problem_item GROUP BY curation_status").fetchall())
        assert statuses["promoted"] == 16  # authored gold, untouched
        assert statuses["approved"] == summary.promoted
        assert "candidate" not in statuses  # all candidates were approved
        assert conn.execute("SELECT COUNT(*) FROM content_promotion").fetchone()[0] == 2  # gold + this one

    # the runtime export still excludes approved-generated content and verifies
    export_gold_bank(db_path, export_path)
    assert len(json.loads(export_path.read_text())["problems"]) == 16
    assert verify_frozen_gold_bank(export_path).ok is True


def test_export_practice_emits_approved_pool_and_verifies(tmp_path):
    db_path = _staged_db(tmp_path, per_skill=4)
    practice_path = tmp_path / "practice.json"
    gold_path = tmp_path / "gold.json"
    promotion = promote_candidates(db_path, promoted_at="2026-06-01T00:00:00Z")

    count = export_practice_bank(db_path, practice_path)

    bank = json.loads(practice_path.read_text())
    assert bank["pool"] == "practice"
    assert count == promotion.promoted
    assert len(bank["problems"]) == promotion.promoted
    assert verify_practice_bank(practice_path).ok is True

    # the frozen gold assessment bank is a separate artifact, still exactly 16
    export_gold_bank(db_path, gold_path)
    assert len(json.loads(gold_path.read_text())["problems"]) == 16


def test_practice_verifier_rejects_a_tampered_problem(tmp_path):
    db_path = _staged_db(tmp_path, per_skill=3)
    practice_path = tmp_path / "practice.json"
    promote_candidates(db_path, promoted_at="2026-06-01T00:00:00Z")
    export_practice_bank(db_path, practice_path)

    bank = json.loads(practice_path.read_text())
    bank["problems"][0]["neutral"]["canonical_answer"] = "999999"  # no longer the solver result
    practice_path.write_text(json.dumps(bank))

    report = verify_practice_bank(practice_path)
    assert report.ok is False
    assert report.errors


def test_promote_can_target_a_single_skill(tmp_path):
    db_path = _staged_db(tmp_path)

    summary = promote_candidates(db_path, skill_id="lin_evaluate", promoted_at="2026-06-01T00:00:00Z")

    with connect_content_db(db_path) as conn:
        approved_skills = {row[0] for row in conn.execute("SELECT DISTINCT skill_id FROM problem_item WHERE curation_status = 'approved'")}
        assert approved_skills == {"lin_evaluate"}
        remaining = conn.execute("SELECT COUNT(*) FROM problem_item WHERE curation_status = 'candidate'").fetchone()[0]
        assert remaining > 0  # other skills' candidates were left untouched
    assert summary.promoted == 5


def test_promotion_re_verifies_and_rejects_a_tampered_candidate(tmp_path):
    db_path = _staged_db(tmp_path)
    with connect_content_db(db_path) as conn:
        target = conn.execute(
            "SELECT problem_item_id FROM problem_realization pr "
            "JOIN problem_item pi ON pi.id = pr.problem_item_id WHERE pi.curation_status = 'candidate' LIMIT 1"
        ).fetchone()[0]
        # corrupt the stored answer so it no longer matches the deterministic solver
        conn.execute(
            "UPDATE problem_realization SET canonical_answer = 'tampered' WHERE problem_item_id = ?", (target,)
        )
        conn.commit()

    summary = promote_candidates(db_path, promoted_at="2026-06-01T00:00:00Z")

    assert summary.rejected >= 1
    assert summary.verifier_ok is False
    with connect_content_db(db_path) as conn:
        status = conn.execute("SELECT curation_status FROM problem_item WHERE id = ?", (target,)).fetchone()[0]
        assert status == "candidate"  # the tampered candidate was not approved


def test_generate_candidates_stages_gated_problems_without_promoting_them(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    export_path = tmp_path / "linear_functions.exported.json"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    summary = generate_candidates(db_path, per_skill=5)

    assert summary.total_created == sum(summary.created_by_skill.values())
    assert summary.total_created > 0

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        statuses = dict(conn.execute("SELECT curation_status, COUNT(*) FROM problem_item GROUP BY curation_status").fetchall())
        assert statuses["promoted"] == 16  # gold runtime bank untouched
        assert statuses["candidate"] == summary.total_created
        orphan = conn.execute(
            "SELECT COUNT(*) FROM problem_item pi "
            "WHERE pi.curation_status = 'candidate' "
            "AND pi.source_item_id NOT IN (SELECT id FROM source_item WHERE ingestion_status = 'staged_oer')"
        ).fetchone()[0]
        assert orphan == 0  # every candidate is provenance-linked to a staged source item

    export_gold_bank(db_path, export_path)
    exported = json.loads(export_path.read_text())
    assert len(exported["problems"]) == 16  # candidates excluded from the runtime bank
    assert verify_frozen_gold_bank(export_path).ok is True


def test_generate_candidates_is_idempotent(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    first = generate_candidates(db_path, per_skill=4)
    second = generate_candidates(db_path, per_skill=4)

    assert first.total_created == second.total_created
    with connect_content_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM problem_item WHERE curation_status = 'candidate'").fetchone()[0]
        assert count == second.total_created  # re-running replaced, did not duplicate


def test_ingest_gold_bank_populates_content_tables(tmp_path):
    db_path = tmp_path / "content.sqlite3"

    summary = ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    assert summary.problem_count == 16
    assert summary.realization_count == 48
    assert summary.skill_count == 8
    assert summary.theme_count == 2
    assert summary.license_status == "internal_gold"

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in (
                "content_source",
                "content_license",
                "source_item",
                "skill",
                "theme",
                "problem_item",
                "problem_realization",
                "hint_scaffold",
                "representation_payload",
            )
        }
        p03_drone = conn.execute(
            "SELECT canonical_answer, prompt FROM problem_realization "
            "WHERE problem_item_id = ? AND realization_key = ?",
            ("lf_p03", "drone_physics"),
        ).fetchone()

    assert counts == {
        "content_source": 1,
        "content_license": 1,
        "source_item": 16,
        "skill": 8,
        "theme": 2,
        "problem_item": 16,
        "problem_realization": 48,
        "hint_scaffold": 16,
        "representation_payload": 14,
    }
    assert p03_drone["canonical_answer"] == "-10"
    assert "velocity" in p03_drone["prompt"].lower()


def test_exported_gold_bank_round_trips_through_existing_verifier(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    exported_path = tmp_path / "linear_functions.exported.json"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    export_gold_bank(db_path, exported_path)

    original = json.loads(DEFAULT_GOLD_PATH.read_text())
    exported = json.loads(exported_path.read_text())
    assert exported == original
    assert verify_frozen_gold_bank(exported_path).ok


def test_license_gate_allows_noncommercial_only_only_in_free_mode():
    assert is_license_allowed("noncommercial_only", DeploymentMode.FREE_NONCOMMERCIAL)
    assert not is_license_allowed("noncommercial_only", DeploymentMode.COMMERCIAL)
    assert not is_license_allowed("permission_required", DeploymentMode.FREE_NONCOMMERCIAL)
    assert not is_license_allowed("excluded", DeploymentMode.FREE_NONCOMMERCIAL)


def test_content_connection_enforces_foreign_keys(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    with connect_content_db(db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        try:
            conn.execute(
                "INSERT INTO problem_realization VALUES "
                "('missing-problem', 'neutral', NULL, 'prompt', 'answer', 'method', '{}', '{}', NULL, '{}', "
                "'missing-source', 'missing-license', 0)"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("dangling realization insert should violate foreign keys")


def test_ingest_refuses_to_replace_existing_database_without_explicit_flag(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    try:
        ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    except ValueError as exc:
        assert "already contains content" in str(exc)
    else:
        raise AssertionError("second ingest should require replace=True")

    summary = ingest_gold_bank(
        DEFAULT_GOLD_PATH,
        db_path,
        deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL,
        replace=True,
    )
    assert summary.problem_count == 16


def test_export_does_not_depend_on_raw_source_json_blob(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    exported_path = tmp_path / "linear_functions.exported.json"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    with connect_content_db(db_path) as conn:
        conn.execute("UPDATE content_source SET raw_json = ?", (json.dumps({"corrupted": True}),))

    export_gold_bank(db_path, exported_path)

    assert json.loads(exported_path.read_text()) == json.loads(DEFAULT_GOLD_PATH.read_text())


def test_problem_level_representation_payloads_are_not_duplicated_per_realization(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        by_kind = {
            row["kind"]: row["count"]
            for row in conn.execute(
                "SELECT kind, COUNT(*) AS count FROM representation_payload GROUP BY kind"
            ).fetchall()
        }
        non_problem_level_graphs = conn.execute(
            "SELECT COUNT(*) FROM representation_payload WHERE kind IN ('graph', 'grid') AND realization_key != ?",
            ("__problem__",),
        ).fetchone()[0]

    assert by_kind == {"graph": 7, "grid": 1, "table": 6}
    assert non_problem_level_graphs == 0


def test_ingest_records_promotion_provenance(tmp_path):
    db_path = tmp_path / "content.sqlite3"

    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        promotion = conn.execute("SELECT * FROM content_promotion").fetchone()

    assert promotion["artifact_sha256"]
    assert len(promotion["artifact_sha256"]) == 64
    assert promotion["verifier_ok"] == 1
    assert promotion["problem_count"] == 16
    assert promotion["realization_count"] == 48


def test_ingest_records_real_template_bindings(tmp_path):
    db_path = tmp_path / "content.sqlite3"

    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        template = conn.execute("SELECT * FROM template WHERE id = ?", ("linear_functions:lf_p04",)).fetchone()
        realization = conn.execute(
            "SELECT param_values, semantic_roles FROM problem_realization "
            "WHERE problem_item_id = ? AND realization_key = ?",
            ("lf_p04", "neutral"),
        ).fetchone()

    assert template["template_kind"] == "slope_two_points"
    assert json.loads(template["param_schema"]) == {"x1": "int", "x2": "int", "y1": "int", "y2": "int"}
    assert json.loads(realization["param_values"]) == {"x1": 1, "x2": 5, "y1": 4, "y2": 16}
    assert json.loads(realization["semantic_roles"])["y2"] == "second output"


def test_ingest_oer_manifest_appends_staged_sources_without_touching_runtime_bank(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    summary = ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    assert summary.source_count == 3
    assert summary.item_count == 10
    assert summary.license_statuses == ["commercial_ok", "noncommercial_only"]

    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("content_source", "content_license", "source_item", "problem_item", "problem_realization")
        }
        statuses = {
            row["ingestion_status"]
            for row in conn.execute(
                "SELECT ingestion_status FROM source_item WHERE source_id != ?",
                ("gold_linear_functions",),
            ).fetchall()
        }
        im_item = conn.execute(
            "SELECT raw_title, standard_tags, raw_json FROM source_item WHERE id = ?",
            ("illustrative_math_grade_8_unit_5:lesson_8_linear_functions",),
        ).fetchone()

    assert counts == {
        "content_source": 4,
        "content_license": 4,
        "source_item": 26,
        "problem_item": 16,
        "problem_realization": 48,
    }
    assert statuses == {"staged_oer"}
    assert im_item["raw_title"] == "Lesson 8: Linear Functions"
    assert "CCSS.8.F.B.4" in json.loads(im_item["standard_tags"])
    assert json.loads(im_item["raw_json"])["candidate_skill_ids"] == ["lin_rate_of_change", "lin_slope_two_points"]


def test_oer_manifest_honors_deployment_license_gate(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)

    try:
        ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.COMMERCIAL)
    except ValueError as exc:
        assert "noncommercial_only" in str(exc)
    else:
        raise AssertionError("noncommercial OER sources should not import under commercial mode")
