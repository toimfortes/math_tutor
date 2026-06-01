import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def login():
    """Register + log a student in; return the auth Authorization header.

    start_session now requires an authenticated student, so API tests use this
    to obtain a bearer auth token before starting a session.
    """

    def _login(client, student_id: str = "stu", password: str = "pw") -> dict:
        client.post("/auth/register", json={"student_id": student_id, "password": password})
        response = client.post("/auth/login", json={"student_id": student_id, "password": password})
        return {"Authorization": f"Bearer {response.json()['auth_token']}"}

    return _login
