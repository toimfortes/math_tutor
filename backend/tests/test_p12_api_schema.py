from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def _schema():
    client = TestClient(create_app(Settings.from_env({})))
    return client.get("/openapi.json").json()


def test_openapi_documents_turn_and_skill_state_models():
    schema = _schema()
    components = schema["components"]["schemas"]

    assert "TurnResponseModel" in components
    assert "SkillStateModel" in components
    assert "PublicProblemModel" in components

    turn_response = schema["paths"]["/turn"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "TurnResponseModel" in turn_response["$ref"]

    state_response = schema["paths"]["/student/{student_id}/state"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "SkillStateModel" in state_response["$ref"]


def test_public_problem_schema_documents_representation_payloads():
    components = _schema()["components"]["schemas"]
    public_problem_props = components["PublicProblemModel"]["properties"]

    for field in ("graph", "table", "grid", "hint_scaffold", "representations"):
        assert field in public_problem_props


def test_turn_endpoint_still_returns_the_expected_shape():
    client = TestClient(create_app(Settings.from_env({})))
    start = client.post("/session/start", json={"student_id": "stu", "theme": "space_logistics"}).json()

    assert set(start) >= {"session_id", "public_problem", "dialogue", "check_result", "xp_awarded"}
    assert set(start["public_problem"]) >= {"ref", "skill_id", "representations", "prompt", "hint_scaffold"}
