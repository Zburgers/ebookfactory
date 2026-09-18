"""Replay-safe normalized provider usage accounting."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UsageCall, utc_now


@dataclass(frozen=True)
class UsageResult:
    call_id: UUID
    outcome: str
    finalized: bool


def record_usage_call(
    session: Session,
    *,
    call_id: UUID,
    provider: str,
    model: str,
    purpose: str,
    outcome: str,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    provider_request_id: str | None = None,
    project_id: UUID | None = None,
    run_id: UUID | None = None,
    task_id: UUID | None = None,
    attempt_id: UUID | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    source_metadata: dict | None = None,
) -> UsageResult:
    """Insert one call or return its existing aggregate on stream replay."""

    with session.begin():
        usage = session.scalar(select(UsageCall).where(UsageCall.id == call_id).with_for_update())
        if usage is not None:
            return UsageResult(call_id=usage.id, outcome=usage.outcome, finalized=usage.ended_at is not None)
        usage = UsageCall(
            id=call_id,
            provider_request_id=provider_request_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            attempt_id=attempt_id,
            purpose=purpose,
            provider=provider,
            model=model,
            started_at=started_at or utc_now(),
            ended_at=ended_at,
            outcome=outcome,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            normalization_version="v1",
            source_metadata=source_metadata or {},
        )
        session.add(usage)
        session.flush()
        return UsageResult(call_id=usage.id, outcome=usage.outcome, finalized=usage.ended_at is not None)


def finalize_usage_call(
    session: Session,
    *,
    call_id: UUID,
    ended_at: datetime | None = None,
    outcome: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    source_metadata: dict | None = None,
) -> UsageResult:
    """Finalize one call once; later stream replays cannot double-count it."""

    with session.begin():
        usage = session.scalar(select(UsageCall).where(UsageCall.id == call_id).with_for_update())
        if usage is None:
            raise ValueError("usage call not found")
        if usage.ended_at is None:
            usage.ended_at = ended_at or utc_now()
            if outcome is not None:
                usage.outcome = outcome
            if input_tokens is not None:
                usage.input_tokens = input_tokens
            if output_tokens is not None:
                usage.output_tokens = output_tokens
            if reasoning_tokens is not None:
                usage.reasoning_tokens = reasoning_tokens
            if source_metadata:
                usage.source_metadata = {**usage.source_metadata, **source_metadata}
        return UsageResult(call_id=usage.id, outcome=usage.outcome, finalized=True)


def usage_totals(session: Session, *, project_id: UUID | None = None) -> dict[str, int | None]:
    """Return token totals while leaving unknown billing as null, never zero."""

    statement = select(
        func.sum(UsageCall.input_tokens),
        func.sum(UsageCall.output_tokens),
        func.sum(UsageCall.reasoning_tokens),
        func.count(UsageCall.id),
    )
    if project_id is not None:
        statement = statement.where(UsageCall.project_id == project_id)
    input_tokens, output_tokens, reasoning_tokens, calls = session.execute(statement).one()
    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "estimated_cost": None,
        "reported_billed_cost": None,
    }


def list_usage_calls(session: Session, *, project_id: UUID | None = None) -> list[dict]:
    """Return bounded call-level lineage while preserving unknown billing as null."""

    statement = select(UsageCall).order_by(UsageCall.started_at.desc()).limit(200)
    if project_id is not None:
        statement = statement.where(UsageCall.project_id == project_id)
    calls = session.scalars(statement).all()
    return [
        {
            "call_id": call.id,
            "provider_request_id": call.provider_request_id,
            "project_id": call.project_id,
            "run_id": call.run_id,
            "task_id": call.task_id,
            "attempt_id": call.attempt_id,
            "purpose": call.purpose,
            "provider": call.provider,
            "model": call.model,
            "outcome": call.outcome,
            "started_at": call.started_at,
            "ended_at": call.ended_at,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "reasoning_tokens": call.reasoning_tokens,
            "estimated_cost": call.estimated_cost,
            "reported_billed_cost": call.reported_billed_cost,
        }
        for call in calls
    ]
