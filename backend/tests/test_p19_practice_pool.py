from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.content.seed_loader import DEFAULT_GOLD_PATH
from backend.app.main import create_app
from backend.content_pipeline.ingest import (
    DeploymentMode,
    DEFAULT_OER_MANIFEST_PATH,
    export_practice_bank,
    generate_candidates,
    ingest_gold_bank,
    ingest_oer_manifest,
    promote_candidates,
)


def _practice_bank(tmp_path):
    db_path = tmp_path / "content.sqlite3"
    ingest_gold_bank(DEFAULT_GOLD_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    ingest_oer_manifest(DEFAULT_OER_MANIFEST_PATH, db_path, deployment_mode=DeploymentMode.FREE_NONCOMMERCIAL)
    generate_candidates(db_path, per_skill=3)
    promote_candidates(db_path, promoted_at="2026-06-01T00:00:00Z")
    practice_path = tmp_path / "practice.json"
    export_practice_bank(db_path, practice_path)
    return practice_path


def _auth(client, student="ada"):
    client.post("/auth/register", json={"student_id": student, "password": "pw"})
    token = client.post("/auth/login", json={"student_id": student, "password": "pw"}).json()["auth_token"]
    return {"Authorization": f"Bearer {token}"}


def test_practice_problems_are_served_without_answers(tmp_path):
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(_practice_bank(tmp_path))})
    client = TestClient(create_app(settings))
    auth = _auth(client)

    response = client.get("/practice/problems", headers=auth)

    assert response.status_code == 200
    problems = response.json()["problems"]
    assert len(problems) > 0
    sample = problems[0]
    assert set(sample) >= {"id", "skill_id", "prompt", "answer_type", "hint_scaffold"}
    assert "canonical_answer" not in sample  # answers are never served


def test_practice_check_grades_with_the_code_owned_checker(tmp_path):
    practice_path = _practice_bank(tmp_path)
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(practice_path)})
    client = TestClient(create_app(settings))
    auth = _auth(client)

    problems = client.get("/practice/problems", headers=auth).json()["problems"]
    # find the canonical answer from the exported artifact for one problem
    import json

    bank = json.loads(practice_path.read_text())
    answers = {p["id"]: p["neutral"]["canonical_answer"] for p in bank["problems"]}
    target = problems[0]

    correct = client.post(
        "/practice/check", json={"problem_id": target["id"], "answer": answers[target["id"]]}, headers=auth
    )
    wrong = client.post(
        "/practice/check", json={"problem_id": target["id"], "answer": "999999"}, headers=auth
    )

    assert correct.status_code == 200 and correct.json()["check_result"] == "correct"
    assert wrong.json()["check_result"] != "correct"


def test_practice_check_returns_a_misconception_diagnostic(tmp_path):
    import json

    practice_path = _practice_bank(tmp_path)
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(practice_path)})
    client = TestClient(create_app(settings))
    auth = _auth(client)

    bank = json.loads(practice_path.read_text())
    slope = next(p for p in bank["problems"] if p["skill_id"] == "lin_slope_two_points")
    inverted_answer = slope["known_wrong_answers"]["inverted_slope"]

    response = client.post(
        "/practice/check", json={"problem_id": slope["id"], "answer": inverted_answer}, headers=auth
    ).json()

    assert response["check_result"] != "correct"
    assert response["diagnostic"]["student_error_tag"] == "inverted_slope"


def test_practice_endpoints_require_auth_and_handle_unknown_problem(tmp_path):
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(_practice_bank(tmp_path))})
    client = TestClient(create_app(settings))

    assert client.get("/practice/problems").status_code == 401  # no token
    auth = _auth(client)
    assert client.post("/practice/check", json={"problem_id": "nope", "answer": "1"}, headers=auth).status_code == 404


def test_practice_pool_is_empty_when_unconfigured():
    client = TestClient(create_app(Settings.from_env({})))
    auth = _auth(client)

    assert client.get("/practice/problems", headers=auth).json()["problems"] == []


def test_practice_check_emits_a_structured_log(tmp_path, caplog):
    import logging

    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(_practice_bank(tmp_path))})
    client = TestClient(create_app(settings))
    auth = _auth(client)
    target = client.get("/practice/problems", headers=auth).json()["problems"][0]

    with caplog.at_level(logging.INFO, logger="math_tutor.practice"):
        client.post("/practice/check", json={"problem_id": target["id"], "answer": "999"}, headers=auth)

    record = next(r for r in caplog.records if r.msg == "practice_checked")
    assert record.problem_id == target["id"]
    assert record.skill_id == target["skill_id"]
    assert record.check_result in {"correct", "incorrect", "undecidable"}


def test_practice_attempts_are_persisted_to_the_attempt_log(tmp_path):
    import sqlite3

    practice_path = _practice_bank(tmp_path)
    session_db = tmp_path / "session.db"
    settings = Settings.from_env({"PRACTICE_BANK_PATH": str(practice_path), "SESSION_DB_PATH": str(session_db)})
    client = TestClient(create_app(settings))
    auth = _auth(client)
    target = client.get("/practice/problems", headers=auth).json()["problems"][0]

    client.post("/practice/check", json={"problem_id": target["id"], "answer": "999"}, headers=auth)

    rows = sqlite3.connect(str(session_db)).execute(
        "SELECT session_id, problem_id, check_result FROM attempt_log"
    ).fetchall()
    assert any(row[1] == target["id"] and row[0].startswith("practice:") for row in rows)
