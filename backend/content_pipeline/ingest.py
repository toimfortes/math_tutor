from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from backend.app.content.seed_loader import DEFAULT_GOLD_PATH, RealizedProblemRef
from backend.content_pipeline.calibration import PRIOR_STRENGTH, calibrate
from backend.content_pipeline.candidate_generation import (
    GENERATORS,
    generate_validated_candidates,
    validate_stored_candidate,
)
from backend.content_pipeline.difficulty import band_to_logit, difficulty_band, heuristic_difficulty
from backend.content_pipeline.review import DEFAULT_INTERVAL_SECONDS, review_due
from backend.content_pipeline.provenance import build_promotion_manifest
from backend.content_pipeline.templates.linear_functions import LINEAR_FUNCTION_TEMPLATE_CASES, LinearTemplateCase

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OER_MANIFEST_PATH = ROOT / "backend/content_pipeline/oer_sources/linear_functions_starter.json"


class DeploymentMode(StrEnum):
    FREE_NONCOMMERCIAL = "free_noncommercial"
    COMMERCIAL = "commercial"


@dataclass(frozen=True)
class IngestionSummary:
    db_path: str
    source_id: str
    deployment_mode: str
    license_status: str
    skill_count: int
    theme_count: int
    problem_count: int
    realization_count: int


@dataclass(frozen=True)
class OerIngestionSummary:
    db_path: str
    manifest_path: str
    deployment_mode: str
    source_count: int
    item_count: int
    license_statuses: list[str]


@dataclass(frozen=True)
class CandidateGenerationSummary:
    db_path: str
    per_skill: int
    created_by_skill: dict[str, int]
    total_created: int


@dataclass(frozen=True)
class PromotionSummary:
    db_path: str
    promotion_id: str
    promoted: int
    rejected: int
    verifier_ok: bool


@dataclass(frozen=True)
class PracticeVerificationReport:
    ok: bool
    problem_count: int
    errors: list[str]


PROBLEM_LEVEL_REALIZATION = "__problem__"


SCHEMA = """
CREATE TABLE IF NOT EXISTS content_source (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    retrieval_method TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    domain TEXT NOT NULL,
    description TEXT NOT NULL,
    usage_notes_json TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_license (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES content_source(id),
    license_name TEXT NOT NULL,
    license_url TEXT NOT NULL,
    license_status TEXT NOT NULL,
    attribution_text TEXT NOT NULL,
    commercial_use_allowed INTEGER NOT NULL,
    noncommercial_use_allowed INTEGER NOT NULL,
    sharealike_required INTEGER NOT NULL,
    free_access_required INTEGER NOT NULL,
    trademark_restrictions TEXT NOT NULL,
    reviewed_by TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_item (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES content_source(id),
    external_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    grade_band TEXT NOT NULL,
    domain TEXT NOT NULL,
    standard_tags TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    license_id TEXT NOT NULL REFERENCES content_license(id),
    ingestion_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    standard_tags TEXT NOT NULL,
    prerequisite_skill_ids TEXT NOT NULL,
    description TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS theme (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    generative_for TEXT NOT NULL,
    mapping_hint TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS template (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skill(id),
    domain TEXT NOT NULL,
    template_kind TEXT NOT NULL,
    answer_type TEXT NOT NULL,
    checker TEXT NOT NULL,
    param_schema TEXT NOT NULL,
    solve_function_ref TEXT NOT NULL,
    diagnostic_catalog_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_item (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES template(id),
    skill_id TEXT NOT NULL REFERENCES skill(id),
    difficulty INTEGER NOT NULL,
    answer_type TEXT NOT NULL,
    checker TEXT NOT NULL,
    representations TEXT NOT NULL,
    assessment_role TEXT NOT NULL,
    source_item_id TEXT NOT NULL REFERENCES source_item(id),
    curation_status TEXT NOT NULL,
    extra_json TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_realization (
    problem_item_id TEXT NOT NULL REFERENCES problem_item(id),
    realization_key TEXT NOT NULL,
    theme_id TEXT,
    prompt TEXT NOT NULL,
    canonical_answer TEXT NOT NULL,
    solution_method TEXT NOT NULL,
    param_values TEXT NOT NULL,
    semantic_roles TEXT NOT NULL,
    table_json TEXT,
    extra_json TEXT NOT NULL,
    source_item_id TEXT NOT NULL REFERENCES source_item(id),
    license_id TEXT NOT NULL REFERENCES content_license(id),
    order_index INTEGER NOT NULL,
    PRIMARY KEY (problem_item_id, realization_key)
);

CREATE TABLE IF NOT EXISTS hint_scaffold (
    problem_item_id TEXT PRIMARY KEY REFERENCES problem_item(id),
    max_safe_hint_level INTEGER NOT NULL,
    level_0 TEXT NOT NULL,
    level_1 TEXT NOT NULL,
    level_2 TEXT NOT NULL,
    level_3 TEXT
);

CREATE TABLE IF NOT EXISTS representation_payload (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_item_id TEXT NOT NULL REFERENCES problem_item(id),
    realization_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_promotion (
    id TEXT PRIMARY KEY,
    artifact_sha256 TEXT NOT NULL,
    promoted_at TEXT NOT NULL,
    promoted_by TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    problem_count INTEGER NOT NULL,
    realization_count INTEGER NOT NULL,
    verifier_ok INTEGER NOT NULL,
    verifier_report_json TEXT NOT NULL,
    provider_runs_json TEXT NOT NULL
);
"""


TABLES = (
    "content_promotion",
    "representation_payload",
    "hint_scaffold",
    "problem_realization",
    "problem_item",
    "template",
    "theme",
    "skill",
    "source_item",
    "content_license",
    "content_source",
)


def is_license_allowed(license_status: str, deployment_mode: DeploymentMode | str) -> bool:
    mode = DeploymentMode(deployment_mode)
    if license_status in {"permission_required", "excluded"}:
        return False
    if mode == DeploymentMode.FREE_NONCOMMERCIAL:
        return license_status in {"internal_gold", "commercial_ok", "commercial_ok_sharealike", "noncommercial_only"}
    return license_status in {"internal_gold", "commercial_ok", "commercial_ok_sharealike"}


def connect_content_db(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ingest_gold_bank(
    gold_path: Path = DEFAULT_GOLD_PATH,
    db_path: Path | str = Path("content.sqlite3"),
    *,
    deployment_mode: DeploymentMode | str = DeploymentMode.FREE_NONCOMMERCIAL,
    source_id: str = "gold_linear_functions",
    replace: bool = False,
) -> IngestionSummary:
    data = json.loads(Path(gold_path).read_text())
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    license_status = "internal_gold"
    if not is_license_allowed(license_status, deployment_mode):
        raise ValueError(f"license status {license_status!r} is not allowed for {deployment_mode!r}")

    with connect_content_db(db_path) as conn:
        conn.executescript(SCHEMA)
        if _has_content(conn):
            if not replace:
                raise ValueError(f"{db_path} already contains content; pass replace=True to overwrite it")
            _reset_tables(conn)
        license_id = f"{source_id}:license"
        _insert_source(conn, source_id, data, gold_path)
        _insert_license(conn, license_id, source_id, license_status)
        _insert_themes(conn, data)
        _insert_skills(conn, data)
        _insert_problems(conn, data, source_id, license_id)
        _insert_promotion(conn, source_id, gold_path)
        conn.commit()

    return IngestionSummary(
        db_path=str(db_path),
        source_id=source_id,
        deployment_mode=str(DeploymentMode(deployment_mode)),
        license_status=license_status,
        skill_count=len(data.get("skills", [])),
        theme_count=len(data.get("themes", [])),
        problem_count=len(data.get("problems", [])),
        realization_count=sum(1 + len(problem.get("themed", {})) for problem in data.get("problems", [])),
    )


def ingest_oer_manifest(
    manifest_path: Path = DEFAULT_OER_MANIFEST_PATH,
    db_path: Path | str = Path("content.sqlite3"),
    *,
    deployment_mode: DeploymentMode | str = DeploymentMode.FREE_NONCOMMERCIAL,
    replace_sources: bool = False,
) -> OerIngestionSummary:
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_content_db(db_path) as conn:
        conn.executescript(SCHEMA)
        _validate_oer_manifest(data, deployment_mode)
        if replace_sources:
            _delete_oer_sources(conn, [source["id"] for source in data.get("sources", [])])
        _insert_oer_sources(conn, data, manifest_path)
        conn.commit()

    statuses = sorted({source["license"]["license_status"] for source in data.get("sources", [])})
    return OerIngestionSummary(
        db_path=str(db_path),
        manifest_path=str(manifest_path),
        deployment_mode=str(DeploymentMode(deployment_mode)),
        source_count=len(data.get("sources", [])),
        item_count=sum(len(source.get("items", [])) for source in data.get("sources", [])),
        license_statuses=statuses,
    )


def export_gold_bank(db_path: Path | str, output_path: Path | str) -> None:
    output_path = Path(output_path)
    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source = conn.execute("SELECT * FROM content_source ORDER BY id LIMIT 1").fetchone()
        if source is None:
            raise ValueError("content database has no content_source row")
        base = {
            "schema_version": source["schema_version"],
            "domain": source["domain"],
            "description": source["description"],
            "usage_notes": json.loads(source["usage_notes_json"]),
            "themes": _export_themes(conn),
            "skills": _export_skills(conn),
            "problems": _export_problems(conn),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n")


def generate_candidates(
    db_path: Path | str = Path("content.sqlite3"),
    *,
    per_skill: int = 5,
) -> CandidateGenerationSummary:
    """Generate gated, deterministic problem candidates from staged source items.

    For each generatable skill that a staged OER item aligns to, produce
    `per_skill` validated candidates and store them as problem_item rows with
    curation_status='candidate', linked to the source item for provenance. These
    are NOT promoted: the export-gold runtime bank ignores them.
    """
    db_path = Path(db_path)
    with connect_content_db(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.row_factory = sqlite3.Row

        existing_skills = {row[0] for row in conn.execute("SELECT id FROM skill")}
        provenance: dict[str, tuple[str, str]] = {}
        for row in conn.execute(
            "SELECT id, raw_json, license_id FROM source_item WHERE ingestion_status = 'staged_oer'"
        ).fetchall():
            raw = json.loads(row["raw_json"])
            for skill_id in raw.get("candidate_skill_ids", []):
                if skill_id in GENERATORS and skill_id in existing_skills and skill_id not in provenance:
                    provenance[skill_id] = (row["id"], row["license_id"])

        _clear_candidates(conn)
        base_order = conn.execute("SELECT COALESCE(MAX(order_index), -1) FROM problem_item").fetchone()[0] + 1
        order = base_order
        created: dict[str, int] = {}

        for skill_id, (source_item_id, license_id) in sorted(provenance.items()):
            spec = GENERATORS[skill_id]
            template_id = f"candidate_template:{skill_id}"
            conn.execute(
                "INSERT OR IGNORE INTO template VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    template_id,
                    skill_id,
                    "linear_functions",
                    spec.kind,
                    spec.answer_type,
                    spec.checker,
                    "{}",
                    "backend.content_pipeline.candidate_generation.generate_candidate",
                    "backend.app.domain.diagnostic_catalog",
                ),
            )
            candidates = generate_validated_candidates(skill_id, per_skill)
            for position, candidate in enumerate(candidates):
                problem_id = f"candidate:{skill_id}:{position}"
                prior = heuristic_difficulty(skill_id, candidate.kind, candidate.params)
                conn.execute(
                    "INSERT INTO problem_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        problem_id,
                        template_id,
                        skill_id,
                        difficulty_band(prior),
                        candidate.answer_type,
                        candidate.checker,
                        _to_json(["text"]),
                        "practice",
                        source_item_id,
                        "candidate",
                        _to_json(
                            {
                                "generated": True,
                                "params": candidate.params,
                                "known_wrong_answers": candidate.known_wrong,
                                "difficulty_prior": prior,
                            }
                        ),
                        order,
                    ),
                )
                scaffold = candidate.hint_scaffold
                conn.execute(
                    "INSERT INTO hint_scaffold VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        problem_id,
                        scaffold["max_safe_hint_level"],
                        scaffold["level_0"],
                        scaffold["level_1"],
                        scaffold["level_2"],
                        scaffold.get("level_3"),
                    ),
                )
                conn.execute(
                    "INSERT INTO problem_realization VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        problem_id,
                        "neutral",
                        None,
                        candidate.prompt,
                        candidate.canonical_answer,
                        "",
                        _to_json(candidate.params),
                        _to_json({}),
                        None,
                        _to_json({}),
                        source_item_id,
                        license_id,
                        0,
                    ),
                )
                order += 1
            created[skill_id] = len(candidates)

        conn.commit()

    return CandidateGenerationSummary(
        db_path=str(db_path),
        per_skill=per_skill,
        created_by_skill=created,
        total_created=sum(created.values()),
    )


def promote_candidates(
    db_path: Path | str = Path("content.sqlite3"),
    *,
    skill_id: str | None = None,
    limit: int | None = None,
    promoted_by: str = "promote_candidates",
    promoted_at: str = "1970-01-01T00:00:00Z",
) -> PromotionSummary:
    """Approve generated candidates after re-verifying them, in the DB only.

    Each selected candidate is re-validated through the generated-content gates
    (deterministic solver result, checker round-trip, safety, no leak). Passing
    candidates move curation_status 'candidate' -> 'approved' and a
    content_promotion audit row is written. This does NOT touch the runtime gold
    bank: export-gold still emits only 'promoted' (authored gold) problems, and
    nothing here changes what learners are served.
    """
    db_path = Path(db_path)
    with connect_content_db(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.row_factory = sqlite3.Row

        query = (
            "SELECT pi.id AS id, pi.skill_id AS skill_id, pi.answer_type AS answer_type, "
            "t.template_kind AS kind, pr.prompt AS prompt, pr.canonical_answer AS canonical_answer, "
            "pr.param_values AS param_values "
            "FROM problem_item pi "
            "JOIN template t ON t.id = pi.template_id "
            "JOIN problem_realization pr ON pr.problem_item_id = pi.id AND pr.realization_key = 'neutral' "
            "WHERE pi.curation_status = 'candidate'"
        )
        params: list[Any] = []
        if skill_id is not None:
            query += " AND pi.skill_id = ?"
            params.append(skill_id)
        query += " ORDER BY pi.order_index"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        promoted_ids: list[str] = []
        rejected = 0
        for row in rows:
            errors = validate_stored_candidate(
                skill_id=row["skill_id"],
                kind=row["kind"],
                answer_type=row["answer_type"],
                params=json.loads(row["param_values"]),
                prompt=row["prompt"],
                canonical_answer=row["canonical_answer"],
            )
            if errors:
                rejected += 1
                continue
            conn.execute("UPDATE problem_item SET curation_status = 'approved' WHERE id = ?", (row["id"],))
            promoted_ids.append(row["id"])

        verifier_ok = rejected == 0
        fingerprint = "\n".join(sorted(promoted_ids))
        promotion_index = conn.execute("SELECT COUNT(*) FROM content_promotion").fetchone()[0]
        promotion_id = f"generated_promotion:{promotion_index}"
        report = {
            "kind": "generated_candidates",
            "promoted": len(promoted_ids),
            "rejected": rejected,
            "skill_id": skill_id,
            "promoted_ids": promoted_ids,
        }
        conn.execute(
            "INSERT INTO content_promotion VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                promotion_id,
                hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
                promoted_at,
                promoted_by,
                0,
                len(promoted_ids),
                len(promoted_ids),
                1 if verifier_ok else 0,
                _to_json(report),
                "[]",
            ),
        )
        conn.commit()

    return PromotionSummary(
        db_path=str(db_path),
        promotion_id=promotion_id,
        promoted=len(promoted_ids),
        rejected=rejected,
        verifier_ok=verifier_ok,
    )


def _clear_candidates(conn: sqlite3.Connection) -> None:
    candidate_ids = [row[0] for row in conn.execute("SELECT id FROM problem_item WHERE curation_status = 'candidate'")]
    for problem_id in candidate_ids:
        conn.execute("DELETE FROM problem_realization WHERE problem_item_id = ?", (problem_id,))
        conn.execute("DELETE FROM hint_scaffold WHERE problem_item_id = ?", (problem_id,))
        conn.execute("DELETE FROM representation_payload WHERE problem_item_id = ?", (problem_id,))
    conn.execute("DELETE FROM problem_item WHERE curation_status = 'candidate'")


def export_practice_bank(db_path: Path | str, output_path: Path | str) -> int:
    """Export approved-generated problems to a separate practice bank JSON.

    This is the 'extra practice' pool, distinct from the frozen gold assessment
    bank. Each problem carries its kind + params so the practice verifier can
    re-derive the answer deterministically.
    """
    output_path = Path(output_path)
    with connect_content_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT pi.id AS id, pi.skill_id AS skill_id, pi.answer_type AS answer_type, pi.checker AS checker, "
            "pi.representations AS representations, pi.extra_json AS extra_json, pi.difficulty AS difficulty, "
            "t.template_kind AS kind, "
            "pr.prompt AS prompt, pr.canonical_answer AS canonical_answer, pr.param_values AS param_values, "
            "hs.max_safe_hint_level AS msh, hs.level_0 AS l0, hs.level_1 AS l1, hs.level_2 AS l2, hs.level_3 AS l3 "
            "FROM problem_item pi "
            "JOIN template t ON t.id = pi.template_id "
            "JOIN problem_realization pr ON pr.problem_item_id = pi.id AND pr.realization_key = 'neutral' "
            "JOIN hint_scaffold hs ON hs.problem_item_id = pi.id "
            "WHERE pi.curation_status = 'approved' ORDER BY pi.order_index"
        ).fetchall()

    problems = [
        {
            "id": row["id"],
            "skill_id": row["skill_id"],
            "kind": row["kind"],
            "answer_type": row["answer_type"],
            "checker": row["checker"],
            "representations": json.loads(row["representations"]),
            "difficulty": row["difficulty"],
            "params": json.loads(row["param_values"]),
            "known_wrong_answers": json.loads(row["extra_json"]).get("known_wrong_answers", {}),
            "neutral": {
                "prompt": row["prompt"],
                "canonical_answer": row["canonical_answer"],
                "solution_method": "",
            },
            "hint_scaffold": {
                "max_safe_hint_level": row["msh"],
                "level_0": row["l0"],
                "level_1": row["l1"],
                "level_2": row["l2"],
                "level_3": row["l3"],
            },
        }
        for row in rows
    ]
    bank = {"schema_version": "1.0", "domain": "linear_functions", "pool": "practice", "problems": problems}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bank, indent=2, ensure_ascii=False) + "\n")
    return len(problems)


def verify_practice_bank(path: Path | str) -> PracticeVerificationReport:
    """Re-derive and gate every problem in a practice bank artifact."""
    data = json.loads(Path(path).read_text())
    errors: list[str] = []
    for problem in data.get("problems", []):
        problem_errors = validate_stored_candidate(
            skill_id=problem["skill_id"],
            kind=problem["kind"],
            answer_type=problem["answer_type"],
            params=problem["params"],
            prompt=problem["neutral"]["prompt"],
            canonical_answer=problem["neutral"]["canonical_answer"],
        )
        errors.extend(f"{problem['id']}: {error}" for error in problem_errors)
    return PracticeVerificationReport(
        ok=not errors, problem_count=len(data.get("problems", [])), errors=errors
    )


_OUTCOMES = {"correct", "incorrect", "undecidable"}


def calibrate_difficulty(
    session_db_path: Path | str,
    content_db_path: Path | str | None = None,
    *,
    prior_strength: float = PRIOR_STRENGTH,
) -> dict[str, dict]:
    """Empirical-Bayes difficulty report from the append-only attempt log.

    Decoupled, offline reporting step: reads first-attempt-per-(student,item)
    outcomes from the attempt log (strict first by autoincrement id), seeds each
    item with its heuristic/authored prior from the content DB, and shrinks. Does
    not write back to any DB or touch scheduling.
    """
    with connect_content_db(session_db_path) as conn:
        # Exclude the adaptively-exposed practice stream so the offline calibrator is
        # not biased by the live difficulty-targeting/review policy. The exclusion sits
        # on the OUTER query (not the MIN(id) subquery) so the subquery still finds each
        # (student, item)'s TRUE first attempt: an item first seen in practice is dropped
        # entirely rather than counting a warmed-up post-practice assessment retry as a
        # "first attempt". The calibration cohort is thus cold, non-practice first attempts.
        rows = conn.execute(
            "SELECT problem_id, check_result FROM attempt_log "
            "WHERE id IN (SELECT MIN(id) FROM attempt_log GROUP BY student_id, problem_id) "
            "AND session_id NOT LIKE 'practice:%'"
        ).fetchall()
    first_attempts = [(pid, result if result in _OUTCOMES else "undecidable") for pid, result in rows]

    priors: dict[str, float] = {}
    if content_db_path is not None:
        with connect_content_db(content_db_path) as conn:
            for item_id, difficulty, extra_json in conn.execute(
                "SELECT id, difficulty, extra_json FROM problem_item"
            ):
                extra = json.loads(extra_json) if extra_json else {}
                priors[item_id] = (
                    extra["difficulty_prior"] if "difficulty_prior" in extra else band_to_logit(difficulty)
                )

    calibrated = calibrate(first_attempts, priors, prior_strength=prior_strength)
    return {
        item_id: {
            "difficulty": value.difficulty,
            "responses": value.responses,
            "prior": value.prior,
            "calibrated": value.calibrated,
            "undecidable": value.undecidable,
        }
        for item_id, value in calibrated.items()
    }


def review_queue(
    session_db_path: Path | str,
    now: float,
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> dict[str, list[dict]]:
    """Offline spaced-review report from the attempt log (no hot-path change)."""
    with connect_content_db(session_db_path) as conn:
        rows = conn.execute(
            "SELECT student_id, skill_id, problem_id, check_result, ts FROM attempt_log"
        ).fetchall()
    due = review_due(
        [(student_id, skill_id, problem_id, result, ts) for student_id, skill_id, problem_id, result, ts in rows],
        now,
        interval_seconds=interval_seconds,
    )
    return {
        student_id: [
            {"skill_id": item.skill_id, "last_correct_ts": item.last_correct_ts, "seconds_since": item.seconds_since}
            for item in items
        ]
        for student_id, items in due.items()
    }


def _reset_tables(conn: sqlite3.Connection) -> None:
    for table in TABLES:
        conn.execute(f"DELETE FROM {table}")


def _delete_oer_sources(conn: sqlite3.Connection, source_ids: list[str]) -> None:
    for source_id in source_ids:
        conn.execute("DELETE FROM source_item WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM content_license WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM content_source WHERE id = ?", (source_id,))


def _has_content(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM content_source").fetchone()[0] > 0


def _insert_source(conn: sqlite3.Connection, source_id: str, data: dict[str, Any], gold_path: Path) -> None:
    conn.execute(
        "INSERT INTO content_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_id,
            "internal_gold",
            data.get("description", "Linear functions gold bank"),
            str(gold_path),
            "math_tutor",
            "2026-05-31T00:00:00Z",
            "checked_in_json",
            _sha256(gold_path),
            data["schema_version"],
            data["domain"],
            data["description"],
            _to_json(data.get("usage_notes", [])),
            _to_json(data),
        ),
    )


def _insert_license(conn: sqlite3.Connection, license_id: str, source_id: str, license_status: str) -> None:
    conn.execute(
        "INSERT INTO content_license VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            license_id,
            source_id,
            "Internal gold fixture",
            "",
            license_status,
            "Authored internal gold fixture for regression testing.",
            1,
            1,
            0,
            0,
            "",
            "repo",
            "2026-05-31T00:00:00Z",
        ),
    )


def _validate_oer_manifest(data: dict[str, Any], deployment_mode: DeploymentMode | str) -> None:
    if data.get("schema_version") != "1.0":
        raise ValueError("OER manifest schema_version must be 1.0")
    if not data.get("sources"):
        raise ValueError("OER manifest must contain at least one source")
    for source in data["sources"]:
        license_status = source["license"]["license_status"]
        if not is_license_allowed(license_status, deployment_mode):
            raise ValueError(
                f"OER source {source['id']} has license status {license_status!r}, "
                f"which is not allowed for {DeploymentMode(deployment_mode).value}"
            )
        if not source.get("items"):
            raise ValueError(f"OER source {source['id']} must contain at least one item")
        if not source.get("edition", "").strip():
            raise ValueError(f"OER source {source['id']} must record an 'edition' for license provenance")
        _check_illustrative_math_edition(source)


# Illustrative Mathematics K-12 (2019-2021) is CC BY 4.0 (commercial use allowed with
# attribution); the v.360 (2024) edition is CC BY-NC and must not be used commercially.
# Reject an IM source that claims commercial use while naming the NC v.360/2024 edition.
_IM_NONCOMMERCIAL_EDITION_MARKERS = ("v.360", "v360", "2024")


def _check_illustrative_math_edition(source: dict[str, Any]) -> None:
    if source.get("provider") != "illustrative_mathematics":
        return
    if not source["license"].get("commercial_use_allowed"):
        return
    edition = source.get("edition", "").lower()
    for marker in _IM_NONCOMMERCIAL_EDITION_MARKERS:
        if marker in edition:
            raise ValueError(
                f"OER source {source['id']} claims commercial use but its edition references "
                f"the non-commercial IM '{marker}' edition (CC BY-NC); pin the 2019-2021 CC BY 4.0 edition"
            )


def _insert_oer_sources(conn: sqlite3.Connection, data: dict[str, Any], manifest_path: Path) -> None:
    for source in data["sources"]:
        license_id = f"{source['id']}:license"
        conn.execute(
            "INSERT INTO content_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source["id"],
                source["provider"],
                source["title"],
                source["source_url"],
                source["publisher"],
                source["retrieved_at"],
                "reviewed_oer_manifest",
                _sha256(manifest_path),
                data["schema_version"],
                "linear_functions",
                data["description"],
                "[]",
                _to_json(source),
            ),
        )
        _insert_oer_license(conn, license_id, source)
        for item in source["items"]:
            _insert_oer_source_item(conn, source, item, license_id)


def _insert_oer_license(conn: sqlite3.Connection, license_id: str, source: dict[str, Any]) -> None:
    license_data = source["license"]
    conn.execute(
        "INSERT INTO content_license VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            license_id,
            source["id"],
            license_data["license_name"],
            license_data["license_url"],
            license_data["license_status"],
            license_data["attribution_text"],
            1 if license_data["commercial_use_allowed"] else 0,
            1 if license_data["noncommercial_use_allowed"] else 0,
            1 if license_data["sharealike_required"] else 0,
            1 if license_data["free_access_required"] else 0,
            license_data.get("trademark_restrictions", ""),
            "repo",
            source["retrieved_at"],
        ),
    )


def _insert_oer_source_item(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    item: dict[str, Any],
    license_id: str,
) -> None:
    raw_json = {
        **item,
        "source_url": item["source_url"],
        "candidate_skill_ids": item.get("candidate_skill_ids", []),
        "learning_goal": item.get("learning_goal", ""),
    }
    conn.execute(
        "INSERT INTO source_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{source['id']}:{item['external_id']}",
            source["id"],
            item["external_id"],
            item["item_type"],
            item["grade_band"],
            item["domain"],
            _to_json(item.get("standard_tags", [])),
            item["raw_title"],
            item["raw_text"],
            _to_json(raw_json),
            license_id,
            "staged_oer",
        ),
    )


def _insert_themes(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    for index, theme in enumerate(data.get("themes", [])):
        conn.execute(
            "INSERT INTO theme VALUES (?, ?, ?, ?, ?)",
            (
                theme["id"],
                theme["label"],
                _to_json(theme.get("generative_for", [])),
                theme.get("mapping_hint", ""),
                index,
            ),
        )


def _insert_skills(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    for index, skill in enumerate(data.get("skills", [])):
        conn.execute(
            "INSERT INTO skill VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                skill["id"],
                skill["name"],
                data["domain"],
                _to_json(skill.get("standard_tags", [])),
                _to_json(skill.get("prerequisites", [])),
                skill.get("description", ""),
                index,
            ),
        )


def _insert_problems(conn: sqlite3.Connection, data: dict[str, Any], source_id: str, license_id: str) -> None:
    cases_by_ref = {case.ref: case for case in LINEAR_FUNCTION_TEMPLATE_CASES}
    for index, problem in enumerate(data.get("problems", [])):
        source_item_id = f"{source_id}:{problem['id']}"
        template_id = f"{data['domain']}:{problem['id']}"
        neutral_case = cases_by_ref[RealizedProblemRef(problem["id"], "neutral")]
        conn.execute(
            "INSERT INTO source_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_item_id,
                source_id,
                problem["id"],
                "problem",
                "",
                data["domain"],
                _to_json(_skill_tags(data, problem["skill_id"])),
                problem["id"],
                problem["neutral"]["prompt"],
                _to_json(problem),
                license_id,
                "promoted",
            ),
        )
        conn.execute(
            "INSERT INTO template VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                template_id,
                problem["skill_id"],
                data["domain"],
                neutral_case.kind,
                problem["answer_type"],
                problem["checker"],
                _to_json(_param_schema(neutral_case)),
                "backend.content_pipeline.templates.linear_functions.solve_case",
                "backend.app.domain.diagnostic_catalog",
            ),
        )
        conn.execute(
            "INSERT INTO problem_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                problem["id"],
                template_id,
                problem["skill_id"],
                problem.get("difficulty", 1),
                problem["answer_type"],
                problem["checker"],
                _to_json(problem.get("representations", [])),
                problem.get("assessment_role", "practice"),
                source_item_id,
                "promoted",
                _to_json(_problem_extra(problem)),
                index,
            ),
        )
        _insert_hint_scaffold(conn, problem)
        _insert_realizations(conn, problem, source_item_id, license_id, cases_by_ref)
        if "graph" in problem:
            _insert_representation(conn, problem["id"], PROBLEM_LEVEL_REALIZATION, "graph", problem["graph"])
        if "grid" in problem:
            _insert_representation(conn, problem["id"], PROBLEM_LEVEL_REALIZATION, "grid", problem["grid"])


def _insert_hint_scaffold(conn: sqlite3.Connection, problem: dict[str, Any]) -> None:
    scaffold = problem["hint_scaffold"]
    conn.execute(
        "INSERT INTO hint_scaffold VALUES (?, ?, ?, ?, ?, ?)",
        (
            problem["id"],
            scaffold["max_safe_hint_level"],
            scaffold["level_0"],
            scaffold["level_1"],
            scaffold["level_2"],
            scaffold.get("level_3"),
        ),
    )


def _insert_realizations(
    conn: sqlite3.Connection,
    problem: dict[str, Any],
    source_item_id: str,
    license_id: str,
    cases_by_ref: dict[RealizedProblemRef, LinearTemplateCase],
) -> None:
    realizations = [("neutral", problem["neutral"])] + list(problem.get("themed", {}).items())
    for index, (realization_key, realization) in enumerate(realizations):
        template_case = cases_by_ref[RealizedProblemRef(problem["id"], realization_key)]
        conn.execute(
            "INSERT INTO problem_realization VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                problem["id"],
                realization_key,
                None if realization_key == "neutral" else realization_key,
                realization["prompt"],
                realization["canonical_answer"],
                realization["solution_method"],
                _to_json(template_case.params),
                _to_json(template_case.roles),
                _to_json(realization["table"]) if "table" in realization else None,
                _to_json(_realization_extra(realization)),
                source_item_id,
                license_id,
                index,
            ),
        )
        if "table" in realization:
            _insert_representation(conn, problem["id"], realization_key, "table", realization["table"])


def _insert_representation(
    conn: sqlite3.Connection,
    problem_id: str,
    realization_key: str,
    kind: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO representation_payload (problem_item_id, realization_key, kind, payload_json) VALUES (?, ?, ?, ?)",
        (problem_id, realization_key, kind, _to_json(payload)),
    )


def _export_themes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM theme ORDER BY order_index").fetchall()
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "generative_for": json.loads(row["generative_for"]),
            "mapping_hint": row["mapping_hint"],
        }
        for row in rows
    ]


def _export_skills(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM skill ORDER BY order_index").fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "standard_tags": json.loads(row["standard_tags"]),
            "prerequisites": json.loads(row["prerequisite_skill_ids"]),
            "description": row["description"],
        }
        for row in rows
    ]


def _export_problems(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # Only promoted problems reach the runtime bank. Generated candidates
    # (curation_status='candidate') are deliberately excluded until a separate,
    # gated promotion step reviews them.
    problem_rows = conn.execute(
        "SELECT * FROM problem_item WHERE curation_status = 'promoted' ORDER BY order_index"
    ).fetchall()
    return [_export_problem(conn, row) for row in problem_rows]


def _export_problem(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    problem: dict[str, Any] = {
        "id": row["id"],
        "skill_id": row["skill_id"],
        "difficulty": row["difficulty"],
        "answer_type": row["answer_type"],
        "checker": row["checker"],
        "representations": json.loads(row["representations"]),
    }
    problem.update(json.loads(row["extra_json"]))
    graph = _payload(conn, row["id"], "graph")
    if graph is not None:
        problem["graph"] = graph
    grid = _payload(conn, row["id"], "grid")
    if grid is not None:
        problem["grid"] = grid
    problem["assessment_role"] = row["assessment_role"]

    realization_rows = conn.execute(
        "SELECT * FROM problem_realization WHERE problem_item_id = ? ORDER BY order_index",
        (row["id"],),
    ).fetchall()
    themed: dict[str, Any] = {}
    for realization in realization_rows:
        exported = {
            "prompt": realization["prompt"],
            "canonical_answer": realization["canonical_answer"],
            "solution_method": realization["solution_method"],
        }
        if realization["table_json"]:
            exported["table"] = json.loads(realization["table_json"])
        exported.update(json.loads(realization["extra_json"]))
        if realization["realization_key"] == "neutral":
            problem["neutral"] = exported
        else:
            themed[realization["realization_key"]] = exported
    problem["themed"] = themed
    problem["hint_scaffold"] = _export_hint_scaffold(conn, row["id"])
    return problem


def _payload(conn: sqlite3.Connection, problem_id: str, kind: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM representation_payload "
        "WHERE problem_item_id = ? AND kind = ? AND realization_key = ? ORDER BY id LIMIT 1",
        (problem_id, kind, PROBLEM_LEVEL_REALIZATION),
    ).fetchone()
    return None if row is None else json.loads(row["payload_json"])


def _export_hint_scaffold(conn: sqlite3.Connection, problem_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM hint_scaffold WHERE problem_item_id = ?", (problem_id,)).fetchone()
    if row is None:
        raise ValueError(f"missing hint scaffold for {problem_id}")
    scaffold = {
        "max_safe_hint_level": row["max_safe_hint_level"],
        "level_0": row["level_0"],
        "level_1": row["level_1"],
        "level_2": row["level_2"],
    }
    if row["level_3"] is not None:
        scaffold["level_3"] = row["level_3"]
    return scaffold


def _skill_tags(data: dict[str, Any], skill_id: str) -> list[str]:
    for skill in data.get("skills", []):
        if skill["id"] == skill_id:
            return list(skill.get("standard_tags", []))
    return []


def _param_schema(template_case: LinearTemplateCase) -> dict[str, str]:
    return {key: type(template_case.params[key]).__name__ for key in sorted(template_case.params)}


def _problem_extra(problem: dict[str, Any]) -> dict[str, Any]:
    known = {
        "id",
        "skill_id",
        "difficulty",
        "answer_type",
        "checker",
        "representations",
        "graph",
        "grid",
        "assessment_role",
        "neutral",
        "themed",
        "hint_scaffold",
    }
    return {key: value for key, value in problem.items() if key not in known}


def _realization_extra(realization: dict[str, Any]) -> dict[str, Any]:
    known = {"prompt", "canonical_answer", "solution_method", "table"}
    return {key: value for key, value in realization.items() if key not in known}


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _insert_promotion(conn: sqlite3.Connection, source_id: str, gold_path: Path) -> None:
    manifest = build_promotion_manifest(artifact_path=gold_path, provider_runs=[], generated_at="2026-05-31T00:00:00Z")
    conn.execute(
        "INSERT INTO content_promotion VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"{source_id}:promotion",
            manifest.artifact_sha256,
            manifest.generated_at,
            "ingest_gold_bank",
            1,
            manifest.problem_count,
            manifest.realization_count,
            1 if manifest.verifier_ok else 0,
            _to_json(manifest.to_dict()),
            _to_json([run.__dict__ for run in manifest.provider_runs]),
        ),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest and export math tutor content artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("gold", help="Ingest the checked-in gold bank into SQLite.")
    ingest_parser.add_argument("--input", type=Path, default=DEFAULT_GOLD_PATH)
    ingest_parser.add_argument("--db", type=Path, required=True)
    ingest_parser.add_argument("--deployment-mode", choices=[mode.value for mode in DeploymentMode], default=DeploymentMode.FREE_NONCOMMERCIAL.value)
    ingest_parser.add_argument("--replace", action="store_true", help="Overwrite existing content tables in the target database.")

    export_parser = subparsers.add_parser("export-gold", help="Export a verifier-compatible gold bank from SQLite.")
    export_parser.add_argument("--db", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)

    oer_parser = subparsers.add_parser("oer", help="Stage reviewed OER source metadata into SQLite.")
    oer_parser.add_argument("--manifest", type=Path, default=DEFAULT_OER_MANIFEST_PATH)
    oer_parser.add_argument("--db", type=Path, required=True)
    oer_parser.add_argument("--deployment-mode", choices=[mode.value for mode in DeploymentMode], default=DeploymentMode.FREE_NONCOMMERCIAL.value)
    oer_parser.add_argument("--replace-sources", action="store_true", help="Replace only sources present in the OER manifest.")

    candidates_parser = subparsers.add_parser(
        "generate-candidates", help="Generate gated candidate problems from staged source alignment (not promoted)."
    )
    candidates_parser.add_argument("--db", type=Path, required=True)
    candidates_parser.add_argument("--per-skill", type=int, default=5)

    promote_parser = subparsers.add_parser(
        "promote", help="Re-verify and approve generated candidates (DB only; not exported to the runtime bank)."
    )
    promote_parser.add_argument("--db", type=Path, required=True)
    promote_parser.add_argument("--skill", type=str, default=None)
    promote_parser.add_argument("--limit", type=int, default=None)

    export_practice_parser = subparsers.add_parser(
        "export-practice", help="Export approved-generated problems to a separate practice bank JSON."
    )
    export_practice_parser.add_argument("--db", type=Path, required=True)
    export_practice_parser.add_argument("--output", type=Path, required=True)

    verify_practice_parser = subparsers.add_parser(
        "verify-practice", help="Re-derive and gate every problem in a practice bank artifact."
    )
    verify_practice_parser.add_argument("--input", type=Path, required=True)

    calibrate_parser = subparsers.add_parser(
        "calibrate", help="Empirical-Bayes difficulty report from the attempt log (offline, JSON only)."
    )
    calibrate_parser.add_argument("--session-db", type=Path, required=True, help="DB holding the attempt_log")
    calibrate_parser.add_argument("--content-db", type=Path, default=None, help="DB holding problem_item priors")
    calibrate_parser.add_argument("--output", type=Path, required=True)

    review_parser = subparsers.add_parser(
        "review-queue", help="Offline spaced-review report: skills mastered but lapsed past the interval."
    )
    review_parser.add_argument("--session-db", type=Path, required=True, help="DB holding the attempt_log")
    review_parser.add_argument("--now", type=float, default=None, help="Epoch seconds 'now' (default: current time)")
    review_parser.add_argument("--interval-days", type=float, default=2.0)
    review_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "gold":
        summary = ingest_gold_bank(args.input, args.db, deployment_mode=args.deployment_mode, replace=args.replace)
        print(json.dumps(summary.__dict__, indent=2, sort_keys=True))
        return
    if args.command == "export-gold":
        export_gold_bank(args.db, args.output)
        print(f"exported gold bank: {args.output}")
        return
    if args.command == "oer":
        summary = ingest_oer_manifest(
            args.manifest,
            args.db,
            deployment_mode=args.deployment_mode,
            replace_sources=args.replace_sources,
        )
        print(json.dumps(summary.__dict__, indent=2, sort_keys=True))
        return
    if args.command == "generate-candidates":
        summary = generate_candidates(args.db, per_skill=args.per_skill)
        print(json.dumps(summary.__dict__, indent=2, sort_keys=True))
        return
    if args.command == "promote":
        from datetime import UTC, datetime

        summary = promote_candidates(
            args.db,
            skill_id=args.skill,
            limit=args.limit,
            promoted_by="cli_promote",
            promoted_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        print(json.dumps(summary.__dict__, indent=2, sort_keys=True))
        return
    if args.command == "export-practice":
        count = export_practice_bank(args.db, args.output)
        print(f"exported practice bank: {args.output} ({count} problems)")
        return
    if args.command == "verify-practice":
        report = verify_practice_bank(args.input)
        if not report.ok:
            raise SystemExit("\n".join(report.errors))
        print(f"practice bank verified: {report.problem_count} problems")
        return
    if args.command == "calibrate":
        report = calibrate_difficulty(args.session_db, args.content_db)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"calibrated {len(report)} items -> {args.output}")
        return
    if args.command == "review-queue":
        import time

        now = args.now if args.now is not None else time.time()
        report = review_queue(args.session_db, now, interval_seconds=args.interval_days * 86400.0)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        due = sum(len(v) for v in report.values())
        print(f"review queue: {due} due across {len(report)} students -> {args.output}")


if __name__ == "__main__":
    main()
