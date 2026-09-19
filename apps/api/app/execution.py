"""Owner-scoped execution snapshots for the book workspace."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Artifact, Attempt, BriefRevision, Event, Job, Message, OrchestratorTurn, ProductionRun, Project, Section, SectionRevision, Task, UsageCall
from app.usage import usage_totals


MAX_TEXT = 20_000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "authorization", "private_key")


def _safe_value(value: Any, *, limit: int = MAX_TEXT, depth: int = 0) -> Any:
    """Project JSON-like values into a bounded owner-safe representation."""

    if depth > 4:
        return "[nested value omitted]"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:100]:
            normalized_key = str(key)
            if any(part in normalized_key.lower() for part in SENSITIVE_KEY_PARTS):
                continue
            result[normalized_key] = _safe_value(child, limit=min(limit, 4_000), depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_value(child, limit=min(limit, 4_000), depth=depth + 1) for child in list(value)[:100]]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:limit]


def _task_result_refs(task: Task) -> dict[str, Any]:
    return _safe_value(task.result_refs or {}, limit=4_000)


def _event_view(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "version": 1,
        "timestamp": event.created_at,
        "project_id": event.project_id,
        "run_id": event.run_id,
        "task_id": event.task_id,
        "kind": event.kind,
        "payload": _safe_value(event.data or {}, limit=8_000),
    }


def build_execution_snapshot(
    session: Session,
    *,
    project_id: UUID,
    after_event_id: int = 0,
    limit: int = 250,
) -> dict[str, Any]:
    """Build one bounded owner-facing view from durable project records."""

    bounded_limit = max(1, min(limit, 500))
    project = session.get(Project, project_id)
    if project is None:
        raise LookupError("project not found")

    brief = None
    if project.active_brief_id:
        brief = session.get(BriefRevision, project.active_brief_id)
    if brief is None:
        brief = session.scalar(
            select(BriefRevision)
            .where(BriefRevision.project_id == project_id)
            .order_by(BriefRevision.revision.desc())
            .limit(1)
        )
    brief_view: dict[str, Any] | None = None
    if brief is not None:
        brief_view = {
            **_safe_value(brief.structured_brief or {}, limit=12_000),
            "brief_id": brief.id,
            "revision": brief.revision,
            "content_hash": brief.content_hash,
            "approved_at": brief.approved_at,
            "created_at": brief.created_at,
        }

    events = list(
        session.scalars(
            select(Event)
            .where(Event.project_id == project_id, Event.id > after_event_id)
            .order_by(Event.id)
            .limit(bounded_limit)
        )
    )
    event_views = [_event_view(event) for event in events]
    worker_by_attempt: dict[str, str | None] = {}
    for event in session.scalars(
        select(Event).where(Event.project_id == project_id, Event.kind == "agent.started").order_by(Event.id)
    ).all():
        attempt_id = (event.data or {}).get("attempt_id")
        if attempt_id:
            worker_by_attempt[str(attempt_id)] = (event.data or {}).get("worker_id")

    runs = session.scalars(
        select(ProductionRun).where(ProductionRun.project_id == project_id).order_by(ProductionRun.created_at.desc()).limit(50)
    ).all()
    run_ids = [run.id for run in runs]
    tasks = (
        session.scalars(select(Task).where(Task.run_id.in_(run_ids)).order_by(Task.created_at)).all()
        if run_ids
        else []
    )
    task_ids = [task.id for task in tasks]
    jobs = session.scalars(select(Job).where(Job.task_id.in_(task_ids)).order_by(Job.created_at)).all() if task_ids else []
    attempts = session.scalars(select(Attempt).where(Attempt.task_id.in_(task_ids)).order_by(Attempt.created_at)).all() if task_ids else []
    jobs_by_task: dict[UUID, list[Job]] = {}
    attempts_by_task: dict[UUID, list[Attempt]] = {}
    for job in jobs:
        jobs_by_task.setdefault(job.task_id, []).append(job)
    for attempt in attempts:
        attempts_by_task.setdefault(attempt.task_id, []).append(attempt)

    task_views: dict[UUID, dict[str, Any]] = {}
    for task in tasks:
        task_views[task.id] = {
            "task_id": task.id,
            "task_type": task.task_type,
            "parent_task_id": task.parent_task_id,
            "dependencies": task.dependencies,
            "input_revision_ids": task.input_revision_ids,
            "provider": task.provider,
            "model": task.model,
            "session_id": task.session_id,
            "status": task.status,
            "result_refs": _task_result_refs(task),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "jobs": [
                {
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "state": job.state,
                    "attempts": job.attempts,
                    "max_attempts": job.max_attempts,
                    "fencing_generation": job.fencing_generation,
                    "available_at": job.available_at,
                    "error_class": job.error_class,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                }
                for job in jobs_by_task.get(task.id, [])
            ],
            "attempts": [
                {
                    "attempt_id": attempt.id,
                    "attempt_no": attempt.attempt_no,
                    "input_revision_ids": attempt.input_revision_ids,
                    "provider": attempt.provider,
                    "model": attempt.model,
                    "session_id": attempt.session_id,
                    "status": attempt.status,
                    "fencing_generation": attempt.fencing_generation,
                    "worker_id": worker_by_attempt.get(str(attempt.id)),
                    "result_refs": _safe_value(attempt.result_refs or {}, limit=4_000),
                    "error_class": attempt.error_class,
                    "started_at": attempt.started_at,
                    "finished_at": attempt.finished_at,
                }
                for attempt in attempts_by_task.get(task.id, [])
            ],
        }

    usage_calls = session.scalars(
        select(UsageCall).where(UsageCall.project_id == project_id).order_by(UsageCall.started_at.desc()).limit(300)
    ).all()
    usage_views = [
        {
            "call_id": call.id,
            "provider_request_id": call.provider_request_id,
            "run_id": call.run_id,
            "task_id": call.task_id,
            "attempt_id": call.attempt_id,
            "agent_id": call.agent_id,
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
            "source_metadata": _safe_value(call.source_metadata or {}, limit=2_000),
        }
        for call in usage_calls
    ]

    section_revision_ids = select(SectionRevision.id).join(Section, Section.id == SectionRevision.section_id).where(Section.project_id == project_id)
    artifact_statement = select(Artifact).where(
        or_(Artifact.run_id.in_(run_ids), Artifact.revision_id.in_(section_revision_ids))
    ).order_by(Artifact.created_at.desc()).limit(500) if run_ids else select(Artifact).where(Artifact.revision_id.in_(section_revision_ids)).order_by(Artifact.created_at.desc()).limit(500)
    artifacts = session.scalars(artifact_statement).all()
    artifact_views = [
        {
            "artifact_id": artifact.id,
            "run_id": artifact.run_id,
            "attempt_id": artifact.attempt_id,
            "usage_call_id": artifact.usage_call_id,
            "revision_id": artifact.revision_id,
            "relative_path": artifact.relative_path,
            "mime_type": artifact.mime_type,
            "byte_count": artifact.byte_count,
            "sha256": artifact.sha256,
            "validation_state": artifact.validation_state,
            "owner_review_state": artifact.owner_review_state,
            "owner_review_note": artifact.owner_review_note,
            "owner_reviewed_at": artifact.owner_reviewed_at,
            "download_path": f"/projects/{project_id}/artifacts/{artifact.id}/download",
        }
        for artifact in artifacts
    ]

    turns = session.scalars(select(OrchestratorTurn).where(OrchestratorTurn.project_id == project_id)).all()
    turn_by_message = {str(turn.user_message_id): turn for turn in turns}
    turn_by_assistant = {str(turn.assistant_message_id): turn for turn in turns if turn.assistant_message_id}
    messages = session.scalars(select(Message).where(Message.project_id == project_id).order_by(Message.sequence).limit(500)).all()
    conversation = [
        {
            "message_id": message.id,
            "sequence": message.sequence,
            "channel": message.channel,
            "role": message.role,
            "content": message.content[:MAX_TEXT],
            "turn_state": message.turn_state,
            "turn_id": (turn_by_message.get(str(message.id)) or turn_by_assistant.get(str(message.id))).id if (turn_by_message.get(str(message.id)) or turn_by_assistant.get(str(message.id))) else None,
            "created_at": message.created_at,
        }
        for message in messages
    ]

    return {
        "project": {
            "project_id": project.id,
            "title": project.title,
            "profile": project.profile,
            "language": project.language,
            "state": project.state,
            "active_brief_id": project.active_brief_id,
            "updated_at": project.updated_at,
        },
        "brief": brief_view,
        "conversation": conversation,
        "turns": [
            {
                "turn_id": turn.id,
                "state": turn.state,
                "provider": turn.provider,
                "model": turn.model,
                "generation": turn.generation,
                "attempts": turn.attempts,
                "created_at": turn.created_at,
                "updated_at": turn.updated_at,
            }
            for turn in turns
        ],
        "runs": [
            {
                "run_id": run.id,
                "approved_brief_id": run.approved_brief_id,
                "plan_revision": run.plan_revision,
                "state": run.state,
                "budget": _safe_value(run.budget or {}, limit=4_000),
                "cancellation_epoch": run.cancellation_epoch,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
                "tasks": [task_views[task.id] for task in tasks if task.run_id == run.id],
            }
            for run in runs
        ],
        "artifacts": artifact_views,
        "usage_calls": usage_views,
        "usage_totals": usage_totals(session, project_id=project_id),
        "activities": event_views,
        "next_event_id": events[-1].id if events else after_event_id,
    }
