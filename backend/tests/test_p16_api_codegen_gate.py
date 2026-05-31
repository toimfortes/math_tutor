from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_package_has_reproducible_api_codegen_scripts():
    package = json.loads((ROOT / "frontend/package.json").read_text())

    assert package["scripts"]["generate:api"] == "python ../scripts/export_openapi.py && openapi-typescript openapi.json -o src/generated/apiSchema.ts"
    assert package["scripts"]["check:api"] == "npm run generate:api && git diff --exit-code src/generated/apiSchema.ts"
    assert package["devDependencies"]["openapi-typescript"] == "7.13.0"


def test_ci_checks_generated_api_schema_drift():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    frontend_steps = workflow["jobs"]["frontend"]["steps"]

    assert any(step.get("name") == "Check generated API schema drift" for step in frontend_steps)
    assert any(step.get("run") == "npm run check:api" for step in frontend_steps)


def test_openapi_export_script_is_tracked():
    script = ROOT / "scripts/export_openapi.py"

    assert script.exists()
    assert "create_app().openapi()" in script.read_text()
