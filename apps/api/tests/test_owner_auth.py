from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def client() -> TestClient:
    return TestClient(create_app(Settings(database_url=None, owner_token="owner-secret", worker_token="worker-secret")))


def test_health_and_login_bootstrap_are_public_but_owner_data_is_not() -> None:
    with client() as http:
        assert http.get("/health").status_code == 200
        assert http.get("/projects").status_code == 401
        assert http.get("/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert http.post("/auth/login", json={"token": "owner-secret"}).json() == {"authenticated": True}
        assert http.get("/auth/verify", headers={"Authorization": "Bearer owner-secret"}).status_code == 200


def test_owner_token_is_not_worker_token_and_missing_configuration_fails_closed() -> None:
    with client() as http:
        assert http.get("/projects", headers={"X-Ebook-Worker-Token": "worker-secret"}).status_code == 401
        assert http.get("/private/worker/providers").status_code == 401
    with TestClient(create_app(Settings(_env_file=None, database_url=None, worker_token="worker-secret"))) as http:
        assert http.get("/projects").status_code == 503
        assert http.post("/auth/login", json={"token": "owner-secret"}).status_code == 503
