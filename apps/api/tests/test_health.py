from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_health_is_available_without_database_configuration() -> None:
    client = TestClient(create_app(Settings(database_url=None)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_explains_missing_database_without_leaking_configuration() -> None:
    client = TestClient(create_app(Settings(database_url=None)))

    response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["dependencies"]["database"]["status"] == "missing_configuration"
    assert "postgresql://" not in response.text


def test_readiness_checks_a_real_sqlite_connection(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'readiness.db'}"
    client = TestClient(create_app(Settings(database_url=database_url)))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["dependencies"]["database"]["status"] == "ok"


def test_openapi_lists_health_contracts() -> None:
    client = TestClient(create_app(Settings(database_url=None)))

    schema = client.get("/openapi.json").json()

    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]


def test_dashboard_is_served_same_origin() -> None:
    client = TestClient(create_app(Settings(database_url=None)))

    response = client.get("/")

    assert response.status_code == 200
    assert "Ebook Factory" in response.text


def test_private_worker_requires_configured_token() -> None:
    client = TestClient(create_app(Settings(database_url=None, worker_token="local-secret")))

    response = client.post(
        "/private/worker/claim",
        json={"worker_id": "worker-a"},
        headers={"X-Ebook-Worker-Token": "wrong"},
    )

    assert response.status_code == 401
    assert "local-secret" not in response.text
