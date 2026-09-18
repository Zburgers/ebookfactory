import os
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from app import model_catalog
from app.main import create_app
from app.settings import Settings


TABLE = """provider        model                context  max-out  thinking  images
openai-codex    gpt-5.6-luna         272K     128K     yes       yes
github-copilot gpt-5-mini           264K     64K      yes       no
"""


def test_parse_pi_model_table_preserves_qualified_identity() -> None:
    result = model_catalog.parse_model_table(TABLE)
    assert result == [
        {
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "qualified_model": "openai-codex/gpt-5.6-luna",
            "context": "272K",
            "max_output": "128K",
            "thinking": True,
            "images": True,
        },
        {
            "provider": "github-copilot",
            "model": "gpt-5-mini",
            "qualified_model": "github-copilot/gpt-5-mini",
            "context": "264K",
            "max_output": "64K",
            "thinking": True,
            "images": False,
        },
    ]


def test_parse_model_table_skips_malformed_rows_and_rejects_invalid_table() -> None:
    malformed = TABLE + "openai-codex only-two-columns\n" + "bad model 12K 4K maybe yes\n"
    assert model_catalog.parse_model_table(malformed) == model_catalog.parse_model_table(TABLE)
    with pytest.raises(model_catalog.ModelCatalogError, match="empty or malformed"):
        model_catalog.parse_model_table("provider model context max-out thinking images\nwrong row\n")


def test_catalog_subprocess_failure_timeout_and_output_bound(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise OSError("private failure")

    monkeypatch.setattr(model_catalog.subprocess, "Popen", fail_run)
    with pytest.raises(model_catalog.ModelCatalogError, match="failed"):
        model_catalog.fetch_model_catalog()

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pi", 3)

    monkeypatch.setattr(model_catalog.subprocess, "Popen", timeout_run)
    with pytest.raises(model_catalog.ModelCatalogError, match="timed out"):
        model_catalog.fetch_model_catalog()

    class PipeProcess:
        def __init__(self):
            out_read, out_write = os.pipe()
            err_read, err_write = os.pipe()
            self.stdout = os.fdopen(out_read, "rb")
            self.stderr = os.fdopen(err_read, "rb")
            def write_and_close():
                os.write(out_write, b"x" * (model_catalog.MAX_OUTPUT_BYTES + 1))
                os.close(out_write)
                os.close(err_write)
            threading.Thread(target=write_and_close, daemon=True).start()

        def poll(self): return 0
        def wait(self, **_kwargs): return 0
        def terminate(self): return None
        def kill(self): return None

    monkeypatch.setattr(model_catalog.subprocess, "Popen", lambda *_args, **_kwargs: PipeProcess())
    with pytest.raises(model_catalog.ModelCatalogError, match="exceeded"):
        model_catalog.fetch_model_catalog()


def test_catalog_route_returns_models_and_sanitized_error(monkeypatch) -> None:
    monkeypatch.setattr(model_catalog, "fetch_model_catalog", lambda: {"source": "pi", "fetched_at": "2026-09-19T00:00:00+00:00", "models": model_catalog.parse_model_table(TABLE)})
    client = TestClient(create_app(Settings(database_url=None)))
    response = client.get("/providers/catalog")
    assert response.status_code == 200
    assert response.json()["models"][0]["qualified_model"] == "openai-codex/gpt-5.6-luna"

    monkeypatch.setattr(model_catalog, "fetch_model_catalog", lambda: (_ for _ in ()).throw(model_catalog.ModelCatalogError("private failure")))
    response = client.get("/providers/catalog")
    assert response.status_code == 503
    assert response.json()["detail"] == "Pi model catalog unavailable"
    assert "private failure" not in response.text
