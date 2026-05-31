from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from backend.content_pipeline.verify import verify_frozen_gold_bank


@dataclass(frozen=True)
class ProviderRun:
    provider: str
    model: str
    role: str
    prompt_version: str
    run_id: str


@dataclass(frozen=True)
class PromotionManifest:
    artifact_path: str
    artifact_sha256: str
    generated_at: str
    verifier_ok: bool
    problem_count: int
    realization_count: int
    template_case_count: int
    verifier_errors: list[str]
    provider_runs: list[ProviderRun]

    def to_dict(self) -> dict:
        return {
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "generated_at": self.generated_at,
            "verifier_ok": self.verifier_ok,
            "problem_count": self.problem_count,
            "realization_count": self.realization_count,
            "template_case_count": self.template_case_count,
            "verifier_errors": list(self.verifier_errors),
            "provider_runs": [asdict(run) for run in self.provider_runs],
        }


def build_promotion_manifest(
    *,
    artifact_path: Path,
    provider_runs: list[ProviderRun],
    generated_at: str | None = None,
) -> PromotionManifest:
    report = verify_frozen_gold_bank(artifact_path)
    return PromotionManifest(
        artifact_path=str(artifact_path),
        artifact_sha256=_sha256(artifact_path),
        generated_at=generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        verifier_ok=report.ok,
        problem_count=report.problem_count,
        realization_count=report.realization_count,
        template_case_count=report.template_case_count,
        verifier_errors=_report_errors(report),
        provider_runs=provider_runs,
    )


def write_promotion_manifest(manifest: PromotionManifest, output_path: Path) -> None:
    output_path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _report_errors(report) -> list[str]:
    errors = (
        report.schema_errors
        + report.template_errors
        + report.role_errors
        + report.public_leaks
        + report.graph_errors
        + report.table_errors
        + report.grid_errors
    )
    if report.safety_terms:
        errors.append(f"unsafe terms: {', '.join(report.safety_terms)}")
    return errors
