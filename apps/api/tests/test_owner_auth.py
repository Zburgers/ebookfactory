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


def test_owner_login_limits_repeated_invalid_tokens(tmp_path) -> None:
    settings = Settings(database_url=None, owner_token="owner-secret", worker_token="worker-secret", auth_rate_limit_file=tmp_path / "login-rate.json")
    with TestClient(create_app(settings)) as http:
        responses = [http.post("/auth/login", json={"token": "wrong"}) for _ in range(6)]

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429
    assert responses[5].headers["retry-after"]


def test_owner_login_limit_is_shared_between_listener_processes(tmp_path) -> None:
    rate_file = tmp_path / "login-rate.json"
    first_settings = Settings(database_url=None, owner_token="owner-secret", worker_token="worker-secret", auth_rate_limit_file=rate_file)
    second_settings = Settings(database_url=None, owner_token="owner-secret", worker_token="worker-secret", auth_rate_limit_file=rate_file)
    with TestClient(create_app(first_settings)) as first, TestClient(create_app(second_settings)) as second:
        assert [first.post("/auth/login", json={"token": "wrong"}).status_code for _ in range(3)] == [401] * 3
        assert second.post("/auth/login", json={"token": "wrong"}).status_code == 401
        assert second.post("/auth/login", json={"token": "wrong"}).status_code == 401
        assert first.post("/auth/login", json={"token": "wrong"}).status_code == 429


def test_openapi_declares_owner_and_worker_auth_contracts() -> None:
    with client() as http:
        schema = http.get("/openapi.json").json()

    assert schema["components"]["securitySchemes"]["OwnerBearer"] == {"type": "http", "scheme": "bearer"}
    assert schema["components"]["securitySchemes"]["WorkerToken"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Ebook-Worker-Token",
    }
    assert schema["components"]["securitySchemes"]["ToolCapability"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Tool-Capability",
    }
    assert schema["paths"]["/projects"]["get"]["security"] == [{"OwnerBearer": []}]
    assert schema["paths"]["/private/orchestrator/claim"]["post"]["security"] == [{"WorkerToken": []}]
    assert schema["paths"]["/usage/calls"]["post"]["security"] == [{"OwnerBearer": [], "WorkerToken": []}]
    assert schema["paths"]["/private/tools/{tool}"]["post"]["security"] == [{"ToolCapability": []}]
