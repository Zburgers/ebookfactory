from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Base
from app.settings import Settings
from app.models import UsageCall
from app.usage import finalize_usage_call, list_usage_calls, record_usage_call, usage_totals


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
        "output_tokens": 4,
        "reasoning_tokens": None,
        "estimated_cost": None,
        "reported_billed_cost": None,
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
    assert calls[0]["estimated_cost"] is None
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
            "output_tokens": 3,
        },
        headers={"X-Ebook-Worker-Token": "worker-secret"},
    )
    assert recorded.status_code == 201
    calls = client.get(f"/usage/calls?project_id={project_id}").json()
    assert calls[0]["call_id"] == str(call_id)
    assert calls[0]["estimated_cost"] is None
