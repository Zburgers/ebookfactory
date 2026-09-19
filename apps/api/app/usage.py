"""Replay-safe normalized provider usage accounting and reference estimates."""

from dataclasses import dataclass
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UsageCall, utc_now
from app.pricing import COPILOT_AI_CREDIT_USD, UsageEstimate, estimate_usage, price_card_summary, pricing_catalog


@dataclass(frozen=True)
class UsageResult:
    call_id: UUID
    outcome: str
    finalized: bool


def _decimal(value: float | int | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _estimate_payload(estimate: UsageEstimate) -> dict[str, object]:
    return {
        "reference_usd": estimate.reference_usd,
        "cache_savings_usd": estimate.cache_savings_usd,
        "copilot_ai_credits": estimate.copilot_ai_credits,
        "complete": estimate.complete,
        "rate_tier": estimate.rate_tier,
        "price_version": estimate.price_version,
        "pricing_basis": estimate.pricing_basis,
        "source_url": estimate.source_url,
        "components": estimate.components,
        "unknown_reason": estimate.unknown_reason,
    }


def _estimate_for(call: UsageCall) -> UsageEstimate:
    return estimate_usage(
        provider=call.provider,
        model=call.model,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        cache_read_tokens=call.cache_read_tokens,
        cache_write_tokens=call.cache_write_tokens,
    )


def _apply_estimate(call: UsageCall, source_metadata: dict | None = None) -> UsageEstimate:
    estimate = _estimate_for(call)
    metadata = dict(call.source_metadata or {})
    if source_metadata:
        metadata.update(source_metadata)
    metadata["pricing"] = _estimate_payload(estimate)
    call.source_metadata = metadata
    call.price_version = estimate.price_version
    call.estimated_cost = _decimal(estimate.reference_usd)
    call.provider_credit_units = _decimal(estimate.copilot_ai_credits)
    return estimate


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
    expected_attempt_id: UUID | None = None,
    expected_purpose: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    source_metadata: dict | None = None,
    manage_transaction: bool = True,
) -> UsageResult:
    """Insert one call or return its existing aggregate on stream replay."""

    with (session.begin() if manage_transaction else nullcontext()):
        usage = session.scalar(select(UsageCall).where(UsageCall.id == call_id).with_for_update())
        if usage is not None:
            if attempt_id is not None and usage.attempt_id != attempt_id:
                raise ValueError("usage call binding does not match attempt")
            if usage.purpose != purpose:
                raise ValueError("usage call binding does not match purpose")
            if expected_attempt_id is not None and usage.attempt_id != expected_attempt_id:
                raise ValueError("usage call binding does not match expected attempt")
            if expected_purpose is not None and usage.purpose != expected_purpose:
                raise ValueError("usage call binding does not match expected purpose")
            return UsageResult(call_id=usage.id, outcome=usage.outcome, finalized=usage.ended_at is not None)
        if expected_attempt_id is not None and expected_attempt_id != attempt_id:
            raise ValueError("usage call binding does not match expected attempt")
        if expected_purpose is not None and expected_purpose != purpose:
            raise ValueError("usage call binding does not match expected purpose")
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
        _apply_estimate(usage)
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
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
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
            if cache_read_tokens is not None:
                usage.cache_read_tokens = cache_read_tokens
            if cache_write_tokens is not None:
                usage.cache_write_tokens = cache_write_tokens
            if reasoning_tokens is not None:
                usage.reasoning_tokens = reasoning_tokens
            _apply_estimate(usage, source_metadata)
        return UsageResult(call_id=usage.id, outcome=usage.outcome, finalized=True)


def _sum_optional(calls: list[UsageCall], field: str) -> int | None:
    values = [getattr(call, field) for call in calls if getattr(call, field) is not None]
    return sum(values) if values else None


def _tracked_tokens(call: UsageCall) -> int | None:
    values = [
        call.input_tokens,
        call.cache_read_tokens,
        call.cache_write_tokens,
        call.output_tokens,
    ]
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _aggregate(calls: list[UsageCall]) -> dict[str, object]:
    estimates = [_estimate_for(call) for call in calls]
    known_estimates = [estimate for estimate in estimates if estimate.reference_usd is not None]
    cache_savings = [estimate.cache_savings_usd for estimate in estimates if estimate.cache_savings_usd is not None]
    credits = [estimate.copilot_ai_credits for estimate in estimates if estimate.copilot_ai_credits is not None]
    reported = [call.reported_billed_cost for call in calls if call.reported_billed_cost is not None]
    estimated_cost = sum((_decimal(estimate.reference_usd) for estimate in known_estimates), Decimal(0)) if known_estimates else None
    estimated_cache_savings = sum((_decimal(value) for value in cache_savings), Decimal(0)) if cache_savings else None
    estimated_credits = sum((_decimal(credit) for credit in credits), Decimal(0)) if credits else None
    reported_cost = sum(reported, Decimal(0)) if reported else None
    input_tokens = _sum_optional(calls, "input_tokens")
    cache_read_tokens = _sum_optional(calls, "cache_read_tokens")
    cache_write_tokens = _sum_optional(calls, "cache_write_tokens")
    output_tokens = _sum_optional(calls, "output_tokens")
    reasoning_tokens = _sum_optional(calls, "reasoning_tokens")
    tracked = [_tracked_tokens(call) for call in calls]
    pricing_sources = []
    pricing_cards = []
    seen_sources: set[tuple[str, str, str]] = set()
    seen_cards: set[tuple[str, str]] = set()
    for call, estimate in zip(calls, estimates):
        if not estimate.source_url or not estimate.pricing_basis:
            continue
        key = (estimate.pricing_basis, estimate.source_url, estimate.price_version or "")
        if key in seen_sources:
            continue
        seen_sources.add(key)
        pricing_sources.append({
            "pricing_basis": estimate.pricing_basis,
            "source_url": estimate.source_url,
            "price_version": estimate.price_version,
        })
        card = price_card_summary(call.provider, call.model)
        card_key = (call.provider, call.model)
        if card and card_key not in seen_cards:
            seen_cards.add(card_key)
            pricing_cards.append(card)
    return {
        "calls": len(calls),
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "processed_tokens": sum(value for value in tracked if value is not None) if any(value is not None for value in tracked) else None,
        "estimated_cost": estimated_cost,
        "estimated_cache_savings": estimated_cache_savings,
        "estimated_cost_complete": bool(calls) and all(estimate.complete for estimate in estimates),
        "estimated_copilot_ai_credits": estimated_credits,
        "estimated_copilot_usd_equivalent": estimated_credits * COPILOT_AI_CREDIT_USD if estimated_credits is not None else None,
        "reported_billed_cost": reported_cost,
        "pricing_sources": pricing_sources,
        "pricing_cards": pricing_cards,
    }


def _call_view(call: UsageCall) -> dict[str, object]:
    estimate = _estimate_for(call)
    return {
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
        "cache_read_tokens": call.cache_read_tokens,
        "cache_write_tokens": call.cache_write_tokens,
        "output_tokens": call.output_tokens,
        "reasoning_tokens": call.reasoning_tokens,
        "processed_tokens": _tracked_tokens(call),
        "estimated_cost": call.estimated_cost if call.estimated_cost is not None else _decimal(estimate.reference_usd),
        "estimated_cache_savings": _decimal(estimate.cache_savings_usd),
        "estimated_cost_complete": estimate.complete,
        "estimated_copilot_ai_credits": call.provider_credit_units if call.provider_credit_units is not None else _decimal(estimate.copilot_ai_credits),
        "reported_billed_cost": call.reported_billed_cost,
        "price_version": estimate.price_version,
        "pricing_basis": estimate.pricing_basis,
        "pricing_source_url": estimate.source_url,
        "pricing_rate_tier": estimate.rate_tier,
        "pricing_components": estimate.components,
        "pricing_unknown_reason": estimate.unknown_reason,
    }


def usage_totals(session: Session, *, project_id: UUID | None = None) -> dict[str, object]:
    """Return token totals and clearly labelled reference/accounting fields."""

    statement = select(UsageCall).order_by(UsageCall.started_at)
    if project_id is not None:
        statement = statement.where(UsageCall.project_id == project_id)
    return _aggregate(list(session.scalars(statement).all()))


def _utc_date(value: datetime) -> str:
    observed = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return observed.date().isoformat()


def usage_overview(session: Session, *, project_id: UUID | None = None) -> dict[str, object]:
    """Return totals plus model and UTC-day rollups for the Usage workspace."""

    statement = select(UsageCall).order_by(UsageCall.started_at)
    if project_id is not None:
        statement = statement.where(UsageCall.project_id == project_id)
    calls = list(session.scalars(statement).all())
    model_groups: dict[tuple[str, str], list[UsageCall]] = {}
    day_groups: dict[str, list[UsageCall]] = {}
    for call in calls:
        model_groups.setdefault((call.provider, call.model), []).append(call)
        day_groups.setdefault(_utc_date(call.started_at), []).append(call)
    model_breakdown = [
        {"provider": provider, "model": model, **_aggregate(group)}
        for (provider, model), group in model_groups.items()
    ]
    daily_breakdown = [{"date": day, **_aggregate(group)} for day, group in day_groups.items()]
    model_breakdown.sort(key=lambda row: (-(row["estimated_cost"] or Decimal(0)), row["provider"], row["model"]))
    daily_breakdown.sort(key=lambda row: row["date"])
    return {
        **_aggregate(calls),
        "model_breakdown": model_breakdown,
        "daily_breakdown": daily_breakdown,
        "pricing_catalog": pricing_catalog(),
    }


def list_usage_calls(session: Session, *, project_id: UUID | None = None) -> list[dict[str, object]]:
    """Return bounded call-level lineage with estimate provenance."""

    statement = select(UsageCall).order_by(UsageCall.started_at.desc()).limit(200)
    if project_id is not None:
        statement = statement.where(UsageCall.project_id == project_id)
    return [_call_view(call) for call in session.scalars(statement).all()]
