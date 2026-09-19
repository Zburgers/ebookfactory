from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models import Base, QuotaSnapshot, utc_now
from app.main import create_app
from app.settings import Settings
from app.quota import list_quota_snapshots, record_quota_snapshot
from app import codex_quota


def test_parse_codexctl_status_redacts_account_and_parses_live_windows() -> None:
    output = """Live status fetched at Sat Sep 19 04:15:02
Rate-Limited Accounts
│ Account                               ┆ 5h  ┆ 5h Reset  ┆ 7d  ┆ 7d Reset  ┆ Resets ┆ Token  │
│ * gkvxjbz2r8@privaterelay.appleid.com ┆ 24% ┆ in 3h 38m ┆ 34% ┆ in 9h 23m ┆ 2      ┆ 9d 17h │
"""
    parsed = codex_quota.parse_codexctl_status(output)
    assert parsed == [
        {"account_index": 1, "window_seconds": 18000, "used": 24, "remaining": 76, "reset": "in 3h 38m"},
        {"account_index": 1, "window_seconds": 604800, "used": 34, "remaining": 66, "reset": "in 9h 23m"},
    ]
    assert "gkvxjbz2r8" not in str(parsed)


def test_parse_codexctl_status_rejects_invalid_percentages() -> None:
    import pytest
    with pytest.raises(codex_quota.CodexQuotaError):
        codex_quota.parse_codexctl_status("│ account ┆ 101% ┆ in 1h ┆ 20% ┆ in 2h ┆ 2 ┆ 1d │")


def test_parse_codexctl_status_keeps_all_redacted_accounts() -> None:
    output = """│ * account-one ┆ 24% ┆ in 3h ┆ 34% ┆ in 9h ┆ 2 ┆ 1d │
│ * account-two ┆ 61% ┆ in 2h ┆ 48% ┆ in 8h ┆ 1 ┆ 2d │
"""
    parsed = codex_quota.parse_codexctl_status(output)
    assert [window["account_index"] for window in parsed] == [1, 1, 2, 2]
    assert [window["used"] for window in parsed] == [24, 34, 61, 48]


def test_usage_call_routes_require_worker_token(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'usage-auth.db'}"; Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret")))
    assert client.post("/usage/calls/00000000-0000-4000-8000-000000000001/finalize", json={}).status_code == 401


def test_dashboard_usage_drilldown_remains_readable(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'usage-read.db'}"; Base.metadata.create_all(create_engine(database_url))
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret")))
    response = client.get("/usage/calls")
    assert response.status_code == 200
    assert response.json() == []


def test_live_quota_route_returns_adapter_result_without_database_snapshot(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'live-quota.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(codex_quota, "fetch_live_quota", lambda: {"fetched_at": "2026-09-19T00:00:00Z", "source": "codexctl status", "windows": [{"account_index": 1, "window_seconds": 18000, "used": 24, "remaining": 76, "reset": "in 3h"}]})
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret")))
    response = client.get("/quota/live")
    assert response.status_code == 200
    assert response.json()["windows"][0]["remaining"] == 76
    assert client.get("/quota").json() == []


def test_live_quota_route_reports_unavailable_without_placeholder_data(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'live-quota-error.db'}"
    Base.metadata.create_all(create_engine(database_url))
    monkeypatch.setattr(codex_quota, "fetch_live_quota", lambda: (_ for _ in ()).throw(codex_quota.CodexQuotaError("codexctl unavailable")))
    response = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret"))).get("/quota/live")
    assert response.status_code == 503
    assert response.json()["detail"] == "Codex live quota unavailable"


def test_quota_snapshot_preserves_unknowns_and_marks_stale(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        observed = utc_now()
        record_quota_snapshot(
            session,
            provider="openai-codex",
            account_alias="subscription",
            bucket="codex-primary",
            source="codex app-server account/rateLimits/read",
            observed_at=observed,
            stale_after=observed + timedelta(seconds=1),
            used=29,
            remaining=71,
            units="percent",
            window_seconds=300 * 60,
            resets_at=observed + timedelta(minutes=5),
            plan_label="plus",
            capability_state="supported",
        )
        session.commit()

        snapshots = list_quota_snapshots(session, provider="openai-codex", now=observed + timedelta(seconds=2))

        assert snapshots[0]["capability_state"] == "stale"
        assert snapshots[0]["account_alias"] == "subscription"
        assert session.scalar(select(QuotaSnapshot.account_alias)) == "subscription"


def test_quota_routes_require_worker_token_and_redact_account_identity(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'quota-api.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret")))
    observed = utc_now()
    payload = {
        "provider": "openai-codex",
        "account_alias": "subscription",
        "bucket": "primary-300m",
        "source": "codex app-server account/rateLimits/read",
        "observed_at": observed.isoformat(),
        "stale_after": (observed + timedelta(minutes=5)).isoformat(),
        "used": 29,
        "remaining": 71,
        "units": "percent",
        "window_seconds": 18000,
        "resets_at": (observed + timedelta(minutes=5)).isoformat(),
        "plan_label": "plus",
        "capability_state": "supported",
    }

    assert client.post("/private/quota/snapshots", json=payload).status_code == 401
    response = client.post(
        "/private/quota/snapshots",
        json=payload,
        headers={"X-Ebook-Worker-Token": "worker-secret"},
    )
    assert response.status_code == 201
    snapshots = client.get("/quota?provider=openai-codex").json()
    assert snapshots[0]["account_alias"] == "subscription"
    assert "accountId" not in response.text
    assert "accountId" not in client.get("/quota").text
