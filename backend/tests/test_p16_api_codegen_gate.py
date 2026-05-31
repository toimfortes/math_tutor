from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_package_has_reproducible_api_codegen_scripts():
    package = json.loads((ROOT / "frontend/package.json").read_text())

    assert package["scripts"]["generate:api"] == "python ../scripts/export_openapi.py && openapi-typescript openapi.json -o src/generated/apiSchema.ts"
    assert package["scripts"]["check:api"] == "npm run generate:api && git diff --exit-code src/generated/apiSchema.ts"
    assert package["devDependencies"]["openapi-typescript"] == "7.13.0"


def test_readme_documents_checked_api_codegen_path():
    readme = (ROOT / "README.md").read_text()

    assert "npm run generate:api" in readme
    assert "npm run check:api" in readme
    assert "python -c" not in readme


def test_ci_checks_generated_api_schema_drift():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "name: Check generated API schema drift" in workflow
    assert "run: npm run check:api" in workflow
    assert "name: Install backend dependencies for OpenAPI export" in workflow


def test_ci_uses_node24_action_versions():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "actions/checkout@v6" in workflow
    assert "actions/setup-node@v6" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-node@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow


def test_openapi_export_script_is_tracked():
    script = ROOT / "scripts/export_openapi.py"

    assert script.exists()
    assert "create_app().openapi()" in script.read_text()
