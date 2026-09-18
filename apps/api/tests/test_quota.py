from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models import Base, QuotaSnapshot, utc_now
from app.main import create_app
from app.settings import Settings
from app.quota import list_quota_snapshots, record_quota_snapshot


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
