"""Durable measured budget checks for fenced production attempts."""

from __future__ import annotations

from datetime import timezone
from contextlib import nullcontext
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events import append_event
from app.jobs import _locked_lease_context
from app.models import Project, UsageCall, utc_now


def _limit(budget: dict[str, Any], name: str) -> int | None:
    value = budget.get(name)
    return value if isinstance(value, int) and value >= 0 else None


def _exceeded(reason: str | None, value: int | None, limit: int | None, label: str) -> str | None:
    return reason or (None if value is None or limit is None or value <= limit else f"{label}_exceeded")


def enforce_budget(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    input_tokens: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None = None,
    manage_transaction: bool = True,
) -> tuple[bool, str | None]:
    """Allow a fenced attempt or persist a visible blocked transition."""

    with (session.begin() if manage_transaction else nullcontext()):
        job, task, run, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        current = session.execute(
            select(
                func.count(UsageCall.id),
                func.coalesce(func.sum(UsageCall.input_tokens), 0),
                func.coalesce(func.sum(UsageCall.output_tokens), 0),
                func.coalesce(func.sum(UsageCall.reasoning_tokens), 0),
            ).where(UsageCall.run_id == run.id)
        ).one()
        calls, input_total, output_total, reasoning_total = current
        budget = run.budget or {}
        reason = None
        reason = _exceeded(reason, calls + 1, _limit(budget, "max_turns"), "max_turns")
        reason = reason or _exceeded(
            reason,
            (input_total + input_tokens) if input_tokens is not None else None,
            _limit(budget, "max_input_tokens"),
            "max_input_tokens",
        )
        reason = reason or _exceeded(
            reason,
            (output_total + output_tokens) if output_tokens is not None else None,
            _limit(budget, "max_output_tokens"),
            "max_output_tokens",
        )
        total = None
        if input_tokens is not None and output_tokens is not None:
            total = input_total + output_total + reasoning_total + input_tokens + output_tokens + (reasoning_tokens or 0)
        reason = reason or _exceeded(reason, total, _limit(budget, "max_total_tokens"), "max_total_tokens")
        if attempt.started_at is not None:
            started_at = attempt.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = int((utc_now() - started_at).total_seconds())
            reason = reason or _exceeded(reason, elapsed_seconds, _limit(budget, "max_seconds"), "max_seconds")
        if reason is None:
            return True, None

        project = session.scalar(select(Project).where(Project.id == run.project_id).with_for_update())
        now = utc_now()
        job.state = "blocked"
        job.error_class = "budget_exceeded"
        job.lease_owner = None
        job.lease_until = None
        task.status = "blocked"
        attempt.status = "failed"
        attempt.error_class = "budget_exceeded"
        attempt.finished_at = now
        attempt.lease_owner = None
        attempt.lease_until = None
        run.state = "blocked"
        if project is not None:
            project.state = "blocked"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.blocked",
            payload={"job_id": str(job.id), "generation": generation, "reason": reason},
        )
        return False, reason
