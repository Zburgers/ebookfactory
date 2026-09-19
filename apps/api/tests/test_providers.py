import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.main import create_app
from app.models import Base
from app.settings import Settings


class ProbeHandler(BaseHTTPRequestHandler):
    seen: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        ProbeHandler.seen = {"path": self.path, "authorization": self.headers.get("authorization")}
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers["content-length"])
        ProbeHandler.seen = {
            "path": self.path,
            "authorization": self.headers.get("authorization"),
            "payload": json.loads(self.rfile.read(length)),
        }
        body = json.dumps({"id": "probe-123", "usage": {"prompt_tokens": 3, "completion_tokens": 2, "secret": "omit-me"}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def test_openai_compatible_connection_test_uses_saved_metadata_and_redacts_secret(tmp_path, monkeypatch) -> None:
    ProbeHandler.seen = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        database_url = f"sqlite:///{tmp_path / 'providers.db'}"
        Base.metadata.create_all(create_engine(database_url))
        monkeypatch.setenv("LOCAL_PROVIDER_SECRET", "super-secret-value")
        client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
        endpoint = f"http://127.0.0.1:{server.server_port}/v1"
        monkeypatch.setenv("EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS", f"http://127.0.0.1:{server.server_port}")
        saved = client.put(
            "/providers/local",
            json={
                "endpoint": endpoint,
                "protocol": "openai-compatible",
                "credential_ref": "LOCAL_PROVIDER_SECRET",
                "orchestration_model": "gpt-test",
            },
        )
        assert saved.status_code == 200

        assert client.post("/providers/local/connection-test").status_code == 403
        response = client.post(
            "/providers/local/connection-test",
            headers={"X-Ebook-Worker-Token": "worker-test"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "provider": "local",
            "protocol": "openai-compatible",
            "model": "gpt-test",
            "outcome": "succeeded",
            "http_status": 200,
            "response_id": "probe-123",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "error": None,
        }
        assert ProbeHandler.seen["path"] == "/v1/chat/completions"
        assert ProbeHandler.seen["authorization"] == "Bearer super-secret-value"
        assert ProbeHandler.seen["payload"] == {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "connection test"}],
            "max_tokens": 8,
        }
        assert "super-secret-value" not in response.text
    finally:
        server.shutdown()
        server.server_close()


def test_connection_test_rejects_unsupported_protocol_and_private_endpoint_without_allowlist(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'providers-invalid.db'}"
    Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})

    assert client.put("/providers/local", json={"endpoint": "http://127.0.0.1:1", "protocol": "pi-native"}).status_code == 200
    unsupported = client.post(
        "/providers/local/connection-test",
        headers={"X-Ebook-Worker-Token": "worker-test"},
    )
    assert unsupported.status_code == 422
    assert "unsupported provider protocol" in unsupported.json()["detail"]

    assert client.put("/providers/private", json={"endpoint": "http://127.0.0.1:1", "protocol": "health-json"}).status_code == 200
    blocked = client.post(
        "/providers/private/connection-test",
        headers={"X-Ebook-Worker-Token": "worker-test"},
    )
    assert blocked.status_code == 422
    assert "explicit allowlist" in blocked.json()["detail"]
    monkeypatch.setenv("EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS", "http://127.0.0.1:1")
    allowed = client.post(
        "/providers/private/connection-test",
        headers={"X-Ebook-Worker-Token": "worker-test"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["outcome"] == "failed"

    monkeypatch.setenv("EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS", "http://127.0.0.1:1/private")
    malformed_allowlist = client.post(
        "/providers/private/connection-test",
        headers={"X-Ebook-Worker-Token": "worker-test"},
    )
    assert malformed_allowlist.status_code == 422
    assert "allowlist" in malformed_allowlist.json()["detail"]

    assert client.put("/providers/bad", json={"endpoint": "http://user:pass@127.0.0.1", "protocol": "health-json"}).status_code == 422
    assert client.put("/providers/query", json={"endpoint": "http://127.0.0.1:1?api_key=secret", "protocol": "health-json"}).status_code == 422


def test_health_json_connection_test_uses_get_and_redacts_response_body(tmp_path, monkeypatch) -> None:
    ProbeHandler.seen = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        database_url = f"sqlite:///{tmp_path / 'health-provider.db'}"
        Base.metadata.create_all(create_engine(database_url))
        monkeypatch.setenv("HEALTH_SECRET", "health-secret")
        client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
        endpoint = f"http://127.0.0.1:{server.server_port}/health"
        monkeypatch.setenv("EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS", f"http://127.0.0.1:{server.server_port}")
        assert client.put(
            "/providers/health",
            json={
                "endpoint": endpoint,
                "protocol": "health-json",
                "credential_ref": "HEALTH_SECRET",
            },
        ).status_code == 200

        response = client.post(
            "/providers/health/connection-test",
            headers={"X-Ebook-Worker-Token": "worker-test"},
        )

        assert response.status_code == 200
        assert response.json()["outcome"] == "succeeded"
        assert response.json()["http_status"] == 200
        assert response.json()["response_id"] is None
        assert response.json()["usage"] is None
        assert ProbeHandler.seen == {"path": "/health", "authorization": "Bearer health-secret"}
        assert "health-secret" not in response.text
    finally:
        server.shutdown()
        server.server_close()


def test_private_worker_provider_metadata_requires_token_and_excludes_secrets(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'worker-providers.db'}"
    Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    assert client.put(
        "/providers/local",
        json={"endpoint": "https://secret.example/v1", "protocol": "openai-compatible", "credential_ref": "LOCAL_SECRET", "orchestration_model": "gpt-test"},
    ).status_code == 200
    assert client.get("/private/worker/providers").status_code == 401
    response = client.get("/private/worker/providers", headers={"X-Ebook-Worker-Token": "worker-test"})
    assert response.status_code == 200
    assert response.json() == [{
        "provider": "local",
        "scope": "app",
        "protocol": "openai-compatible",
        "orchestration_model": "gpt-test",
        "drafting_model": None,
        "review_model": None,
        "credential_configured": True,
    }]
    assert "endpoint" not in response.text
    assert "credential_ref" not in response.text


def test_public_provider_metadata_excludes_endpoint_and_credential_ref(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'public-providers.db'}"
    Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    assert client.put(
        "/providers/local",
        json={"endpoint": "https://secret.example/v1", "protocol": "openai-compatible", "credential_ref": "LOCAL_SECRET", "orchestration_model": "gpt-test"},
    ).status_code == 200
    response = client.get("/providers")
    assert response.status_code == 200
    assert response.json() == [{
        "provider": "local",
        "scope": "app",
        "protocol": "openai-compatible",
        "orchestration_model": "gpt-test",
        "drafting_model": None,
        "review_model": None,
        "credential_configured": True,
    }]
    assert "https://secret.example" not in response.text
    assert "credential_ref" not in response.text


def test_pi_native_provider_rejects_qualified_model_from_other_provider(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'qualified-models.db'}"
    Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    response = client.put(
        "/providers/openai-codex",
        json={
            "protocol": "pi-native",
            "orchestration_model": "github-copilot/gpt-5.6-luna",
            "drafting_model": "openai-codex/gpt-5.6-luna",
        },
    )
    assert response.status_code == 422
    assert "provider/model" in response.json()["detail"]


def test_pi_native_provider_rejects_bare_model(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'bare-model.db'}"
    Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-test", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    response = client.put(
        "/providers/openai-codex",
        json={"protocol": "pi-native", "orchestration_model": "gpt-5.6-luna"},
    )
    assert response.status_code == 422
    assert "provider/model" in response.json()["detail"]
