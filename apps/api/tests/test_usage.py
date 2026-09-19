from datetime import datetime, timezone
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Base
from app.settings import Settings
from app.models import UsageCall
from app.pricing import estimate_usage, pricing_catalog
from app.github_billing import fetch_github_billing
from app.usage import finalize_usage_call, list_usage_calls, record_usage_call, usage_overview, usage_totals


def test_github_billing_is_explicitly_unconfigured_without_a_pat() -> None:
    result = fetch_github_billing(Settings(_env_file=None, database_url=None))

    assert result["status"] == "not_configured"
    assert result["configured"] is False
    assert result["items"] == []
    assert result["totals"]["net_amount"] is None


def test_github_billing_fetches_live_ai_credit_usage_without_leaking_pat(monkeypatch) -> None:
    requests = []
    token = "github-pat-that-must-never-be-returned"

    def fake_request(url, request_token, *, timeout_seconds):
        requests.append((url, request_token, timeout_seconds))
        if url.endswith("/user"):
            return {"login": "owner"}
        return {
            "usageItems": [
                {
                    "date": "2026-09-20",
                    "model": "GPT-5.6 Luna",
                    "unitType": "credits",
                    "grossQuantity": 125,
                    "pricePerUnit": 0.01,
                    "grossAmount": 1.25,
                    "discountAmount": 0.25,
                    "netAmount": 1.0,
                    "inputTokens": 1_000_000,
                    "outputTokens": 500_000,
                    "cacheReadTokens": 250_000,
                    "cacheWriteTokens": 50_000,
                }
            ]
        }

    monkeypatch.setattr("app.github_billing._request_json", fake_request)
    result = fetch_github_billing(
        Settings(
            _env_file=None,
            database_url=None,
            github_billing_token=token,
            github_billing_account_type="user",
        )
    )

    assert result["status"] == "ok"
    assert result["account"]["identifier"] == "owner"
    assert result["totals"]["ai_credits"] == 125
    assert result["totals"]["gross_amount"] == 1.25
    assert result["totals"]["net_amount"] == 1.0
    assert result["items"][0]["cache_read_tokens"] == 250_000
    assert requests[0][0].endswith("/user")
    assert requests[0][1] == token
    serialized = str(result)
    assert token not in serialized


def test_github_billing_reports_verified_identity_when_personal_usage_is_missing(monkeypatch) -> None:
    def fake_request(url, _token, *, timeout_seconds):
        if url.endswith("/user"):
            return {"login": "owner"}
        raise HTTPError(url, 404, "not found", {}, None)

    monkeypatch.setattr("app.github_billing._request_json", fake_request)
    result = fetch_github_billing(
        Settings(_env_file=None, database_url=None, github_billing_token="pat", github_billing_account_type="user")
    )

    assert result["status"] == "error"
    assert result["http_status"] == 404
    assert result["identity_verified"] is True
    assert result["account"]["identifier"] == "owner"


def test_pricing_estimate_includes_cache_dimensions_and_copilot_credits() -> None:
    estimate = estimate_usage(
        provider="github-copilot",
        model="github-copilot/gpt-5.6-luna",
        input_tokens=1_000_000,
        cache_read_tokens=2_000_000,
        cache_write_tokens=3_000_000,
        output_tokens=4_000_000,
    )

    assert estimate.pricing_basis == "github_ai_credits"
    assert estimate.reference_usd == 9.18
    assert estimate.copilot_ai_credits == 918
    assert estimate.cache_savings_usd == 0.72
    assert estimate.rate_tier == "long_context"
    assert estimate.complete is True
    assert estimate.source_url.endswith("models-and-pricing")


def test_pricing_estimate_uses_long_context_rate_and_keeps_unknown_models_unknown() -> None:
    long_context = estimate_usage(
        provider="github-copilot",
        model="github-copilot/gpt-5.6-luna",
        input_tokens=250_000,
        output_tokens=1_000_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    unknown = estimate_usage(
        provider="github-copilot",
        model="github-copilot/not-a-real-model",
        input_tokens=10,
        output_tokens=5,
    )

    assert long_context.reference_usd == 1.90
    assert long_context.rate_tier == "long_context"
    assert unknown.reference_usd is None
    assert unknown.complete is False
    assert unknown.unknown_reason == "no verified price card for provider/model"
    assert any(card["model"] == "gpt-5.6-luna" for card in pricing_catalog("openai-codex"))


def test_codex_pricing_matches_published_sol_rate_and_keeps_spark_preview_unknown() -> None:
    sol = estimate_usage(
        provider="openai-codex",
        model="openai-codex/gpt-5.6-sol",
        input_tokens=100_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=1_000_000,
    )
    spark = estimate_usage(
        provider="openai-codex",
        model="openai-codex/gpt-5.3-codex-spark",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )

    assert sol.reference_usd == 20.4
    assert sol.complete is True
    assert spark.reference_usd is None
    assert spark.complete is False
    assert "no verified price card" in (spark.unknown_reason or "")


def test_usage_overview_rolls_up_tokens_costs_models_and_days(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'usage-overview.db'}")
    UsageCall.__table__.create(engine)
    session = Session(engine)
    project_id = uuid4()
    record_usage_call(
        session,
        call_id=uuid4(),
        provider="github-copilot",
        model="github-copilot/gpt-5.6-luna",
        purpose="draft",
        outcome="succeeded",
        project_id=project_id,
        input_tokens=100,
        cache_read_tokens=20,
        cache_write_tokens=10,
        output_tokens=50,
        started_at=datetime(2026, 9, 20, 1, 2, tzinfo=timezone.utc),
    )
    record_usage_call(
        session,
        call_id=uuid4(),
        provider="openai-codex",
        model="openai-codex/gpt-5.6-luna",
        purpose="review",
        outcome="succeeded",
        project_id=project_id,
        input_tokens=200,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=100,
        started_at=datetime(2026, 9, 19, 1, 2, tzinfo=timezone.utc),
    )
    record_usage_call(
        session,
        call_id=uuid4(),
        provider="github-copilot",
        model="github-copilot/not-a-real-model",
        purpose="art",
        outcome="succeeded",
        project_id=project_id,
        input_tokens=5,
        output_tokens=4,
        started_at=datetime(2026, 9, 20, 2, 2, tzinfo=timezone.utc),
    )

    overview = usage_overview(session, project_id=project_id)

    assert overview["calls"] == 3
    assert overview["processed_tokens"] == 489
    assert overview["input_tokens"] == 305
    assert overview["cache_read_tokens"] == 20
    assert overview["cache_write_tokens"] == 10
    assert overview["output_tokens"] == 154
    assert overview["estimated_cost"] is not None
    assert overview["estimated_cost_complete"] is False
    assert overview["estimated_copilot_ai_credits"] is not None
    assert {row["model"] for row in overview["model_breakdown"]} == {
        "github-copilot/gpt-5.6-luna",
        "openai-codex/gpt-5.6-luna",
        "github-copilot/not-a-real-model",
    }
    assert {row["date"] for row in overview["daily_breakdown"]} == {"2026-09-19", "2026-09-20"}


def test_usage_stream_replay_is_idempotent(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    UsageCall.__table__.create(engine)
    session = Session(engine)
    call_id = uuid4()
    first = record_usage_call(
        session,
        call_id=call_id,
        provider="test-provider",
        model="test-model",
        purpose="draft",
        outcome="streaming",
        input_tokens=10,
    )
    replay = record_usage_call(
        session,
        call_id=call_id,
        provider="test-provider",
        model="test-model",
        purpose="draft",
        outcome="streaming",
        input_tokens=999,
    )
    finalize_usage_call(session, call_id=call_id, outcome="succeeded", output_tokens=4)
    finalize_usage_call(session, call_id=call_id, outcome="succeeded", output_tokens=999)

    assert first.call_id == replay.call_id
    assert usage_totals(session) == {
        "calls": 1,
        "input_tokens": 10,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "output_tokens": 4,
        "reasoning_tokens": None,
        "processed_tokens": 14,
        "estimated_cost": None,
        "estimated_cache_savings": None,
        "estimated_cost_complete": False,
        "estimated_copilot_ai_credits": None,
        "estimated_copilot_usd_equivalent": None,
        "reported_billed_cost": None,
        "pricing_sources": [],
        "pricing_cards": [],
    }
    assert len(session.scalars(select(UsageCall)).all()) == 1


def test_usage_stream_replay_rejects_cross_attempt_reuse(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'usage-attempt.db'}")
    UsageCall.__table__.create(engine)
    session = Session(engine)
    call_id = uuid4()
    first_attempt_id, other_attempt_id = uuid4(), uuid4()
    record_usage_call(
        session,
        call_id=call_id,
        provider="test-provider",
        model="test-model",
        purpose="art",
        outcome="succeeded",
        attempt_id=first_attempt_id,
    )
    with pytest.raises(ValueError, match="usage call binding"):
        record_usage_call(
            session,
            call_id=call_id,
            provider="test-provider",
            model="test-model",
            purpose="art",
            outcome="succeeded",
            attempt_id=other_attempt_id,
            expected_attempt_id=other_attempt_id,
            expected_purpose="art",
        )
    with pytest.raises(ValueError, match="usage call binding"):
        record_usage_call(
            session,
            call_id=call_id,
            provider="test-provider",
            model="test-model",
            purpose="art",
            outcome="succeeded",
            attempt_id=other_attempt_id,
        )
    with pytest.raises(ValueError, match="usage call binding"):
        record_usage_call(
            session,
            call_id=uuid4(),
            provider="test-provider",
            model="test-model",
            purpose="art",
            outcome="succeeded",
            attempt_id=first_attempt_id,
            expected_attempt_id=other_attempt_id,
            expected_purpose="art",
        )


def test_usage_call_drilldown_returns_lineage_and_unknown_billing(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'usage-drilldown.db'}")
    UsageCall.__table__.create(engine)
    session = Session(engine)
    project_id = uuid4()
    call_id = uuid4()

    record_usage_call(
        session,
        call_id=call_id,
        provider="openai-codex",
        model="openai-codex/gpt-5.6-luna",
        purpose="production",
        outcome="succeeded",
        project_id=project_id,
        input_tokens=12,
        output_tokens=7,
    )

    calls = list_usage_calls(session, project_id=project_id)

    assert calls[0]["call_id"] == call_id
    assert calls[0]["model"] == "openai-codex/gpt-5.6-luna"
    assert calls[0]["input_tokens"] == 12
    assert calls[0]["estimated_cost"] is not None
    assert calls[0]["estimated_cost_complete"] is False
    assert calls[0]["reported_billed_cost"] is None


def test_usage_call_drilldown_route_is_project_scoped(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'usage-api.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    client = TestClient(create_app(Settings(database_url=database_url, worker_token="worker-secret", owner_token="owner")), headers={"Authorization": "Bearer owner"})
    project_id = uuid4()
    call_id = uuid4()

    recorded = client.post(
        "/usage/calls",
        json={
            "call_id": str(call_id),
            "provider": "openai-codex",
            "model": "openai-codex/gpt-5.6-luna",
            "purpose": "production",
            "outcome": "succeeded",
            "project_id": str(project_id),
            "input_tokens": 4,
            "cache_read_tokens": 2,
            "cache_write_tokens": 1,
            "output_tokens": 3,
        },
    )
    assert recorded.status_code == 401
    recorded = client.post(
        "/usage/calls",
        json={
            "call_id": str(call_id),
            "provider": "openai-codex",
            "model": "openai-codex/gpt-5.6-luna",
            "purpose": "production",
            "outcome": "succeeded",
            "project_id": str(project_id),
            "input_tokens": 4,
            "cache_read_tokens": 2,
            "cache_write_tokens": 1,
            "output_tokens": 3,
        },
        headers={"X-Ebook-Worker-Token": "worker-secret"},
    )
    assert recorded.status_code == 201
    calls = client.get(f"/usage/calls?project_id={project_id}").json()
    assert calls[0]["call_id"] == str(call_id)
    assert calls[0]["cache_read_tokens"] == 2
    assert calls[0]["cache_write_tokens"] == 1
    assert calls[0]["estimated_cost"] is not None
    overview = client.get(f"/usage?project_id={project_id}").json()
    assert overview["processed_tokens"] == 10
    assert overview["model_breakdown"][0]["model"] == "openai-codex/gpt-5.6-luna"
