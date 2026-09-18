"""Provider quota snapshots with explicit stale and unavailable states."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuotaSnapshot, utc_now


def record_quota_snapshot(
    session: Session,
    *,
    provider: str,
    account_alias: str,
    bucket: str,
    source: str,
    observed_at: datetime,
    stale_after: datetime,
    used: Decimal | int | float | None,
    remaining: Decimal | int | float | None,
    units: str | None,
    window_seconds: int | None,
    resets_at: datetime | None,
    plan_label: str | None,
    capability_state: str,
    error: str | None = None,
) -> UUID:
    """Append one provider observation without assigning account quota to a project."""

    with session.begin():
        snapshot = QuotaSnapshot(
            provider=provider,
            account_alias=account_alias,
            bucket=bucket,
            source=source,
            observed_at=observed_at,
            stale_after=stale_after,
            used=used,
            remaining=remaining,
            units=units,
            window_seconds=window_seconds,
            resets_at=resets_at,
            plan_label=plan_label,
            capability_state=capability_state,
            error=error,
        )
        session.add(snapshot)
        session.flush()
        return snapshot.id


def list_quota_snapshots(
    session: Session, *, provider: str | None = None, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Return recent quota observations, marking expired supported windows stale."""

    observed_now = now or utc_now()
    rows = session.scalars(
        select(QuotaSnapshot)
        .where(QuotaSnapshot.provider == provider if provider else True)
        .order_by(QuotaSnapshot.observed_at.desc())
        .limit(100)
    ).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        stale_after = row.stale_after
        if stale_after.tzinfo is None:
            stale_after = stale_after.replace(tzinfo=timezone.utc)
        state = "stale" if row.capability_state == "supported" and observed_now >= stale_after else row.capability_state
        result.append(
            {
                "snapshot_id": row.id,
                "provider": row.provider,
                "account_alias": row.account_alias,
                "bucket": row.bucket,
                "source": row.source,
                "observed_at": row.observed_at,
                "stale_after": row.stale_after,
                "used": row.used,
                "remaining": row.remaining,
                "units": row.units,
                "window_seconds": row.window_seconds,
                "resets_at": row.resets_at,
                "plan_label": row.plan_label,
                "capability_state": state,
                "error": row.error,
            }
        )
    return result
