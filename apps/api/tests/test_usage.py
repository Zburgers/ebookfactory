from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import UsageCall
from app.usage import finalize_usage_call, record_usage_call, usage_totals


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
