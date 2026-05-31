from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_app_health_endpoint_boots():
    app = create_app(Settings(app_name="Math Tutor Test"))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Math Tutor Test"}
