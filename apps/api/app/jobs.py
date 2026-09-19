"""Transactional approval and durable job enqueue primitives."""

from dataclasses import dataclass
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import Artifact, Attempt, BriefRevision, Job, Project, ProductionRun, Task, utc_now


class ApprovalConflict(RuntimeError):
    """Raised when an approval cannot safely create a new production run."""


class StaleRevision(ApprovalConflict):
    """Raised when approval does not bind the currently expected brief hash."""


class StaleLease(RuntimeError):
    """Raised when a worker mutation does not hold the current fencing lease."""


class CancellationRejected(StaleLease):
    """Raised when a worker reports after its run cancellation epoch changed."""


@dataclass(frozen=True)
class ApprovalResult:
    """Stable identifiers returned by an idempotent approval operation."""

    run_id: UUID
    task_id: UUID
    job_id: UUID


@dataclass(frozen=True)
class ArtRevisionResult:
    """Stable identifiers returned when an owner requests new artwork."""

    run_id: UUID
    task_id: UUID
    job_id: UUID
    source_artifact_id: UUID


@dataclass(frozen=True)
class OrchestratorAgentResult:
    """Stable identifiers for a bounded agent task spawned from owner chat."""

    run_id: UUID
    task_id: UUID
    job_id: UUID
    task_type: str


@dataclass(frozen=True)
class JobLease:
    """The committed lease identity a worker must echo on every mutation."""

    job_id: UUID
    task_id: UUID
    run_id: UUID
    attempt_id: UUID
    generation: int
    cancellation_epoch: int
    lease_until: datetime


@dataclass(frozen=True)
class HeartbeatResult:
    """The new committed lease expiry."""

    lease_until: datetime


WORKER_ACTIVITY_TYPES = {
    "session.started",
    "session.completed",
    "message.started",
    "message.delta",
    "message.completed",
    "tool.started",
    "tool.updated",
    "tool.completed",
    "tool.failed",
}
_WORKER_ACTIVITY_SENSITIVE_KEYS = ("token", "secret", "password", "credential", "authorization", "private_key")


def _sanitize_activity_text(value: str) -> str:
    value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", value)
    value = re.sub(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|password|secret)\s*[:=]\s*)[^\s,;]+",
        r"\1[redacted]",
        value,
    )
    value = re.sub(r"(?i)\b(?:sk|rk)-[A-Za-z0-9_-]{16,}", "[redacted]", value)
    return value[:8_000]


def _bounded_result_refs(result_refs: dict[str, Any], *, max_text: int = 2_000) -> dict[str, Any]:
    """Keep lifecycle events useful without copying unbounded worker output."""

    bounded: dict[str, Any] = {}
    for key, value in result_refs.items():
        if isinstance(value, str):
            bounded[key] = value[:max_text]
        elif isinstance(value, (int, float, bool)) or value is None:
            bounded[key] = value
        elif isinstance(value, list):
            bounded[key] = [str(item)[:256] for item in value[:32]]
        elif isinstance(value, dict):
            bounded[key] = {str(child_key): str(child_value)[:256] for child_key, child_value in list(value.items())[:32]}
        else:
            bounded[key] = str(value)[:256]
    return bounded


def _sanitize_worker_activity(value: Any, *, depth: int = 0) -> Any:
    """Bound worker trace payloads before writing owner-visible replay events."""

    if depth > 4:
        return "[nested value omitted]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:40]:
            name = str(key)
            if any(part in name.lower() for part in _WORKER_ACTIVITY_SENSITIVE_KEYS):
                result[name] = "[redacted]"
            else:
                result[name] = _sanitize_worker_activity(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_worker_activity(child, depth=depth + 1) for child in list(value)[:40]]
    if isinstance(value, str):
        return _sanitize_activity_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_activity_text(str(value))


def record_worker_activity(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    activity_type: str,
    payload: dict[str, Any],
) -> None:
    """Append a fenced generic-agent trace event for the owner replay view."""

    if activity_type not in WORKER_ACTIVITY_TYPES:
        raise ValueError("unsupported worker activity type")
    bounded_payload = _sanitize_worker_activity(payload)
    if not isinstance(bounded_payload, dict):
        raise ValueError("worker activity payload must be an object")
    with session.begin():
        job, task, run, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind=f"agent.{activity_type}",
            payload={
                **bounded_payload,
                "job_id": str(job.id),
                "attempt_id": str(attempt.id),
                "generation": generation,
            },
        )


def _existing_approval(session: Session, *, project_id: UUID, brief_id: UUID) -> ApprovalResult | None:
    statement = (
        select(ProductionRun, Task, Job)
        .join(Task, Task.run_id == ProductionRun.id)
        .join(Job, Job.task_id == Task.id)
        .where(
            ProductionRun.project_id == project_id,
            ProductionRun.approved_brief_id == brief_id,
            Task.task_type == "production",
        )
        .order_by(ProductionRun.created_at)
    )
    row = session.execute(statement).first()
    if row is None:
        return None
    run, task, job = row
    return ApprovalResult(run_id=run.id, task_id=task.id, job_id=job.id)


def approve_brief_and_enqueue(
    session: Session,
    *,
    project_id: UUID,
    brief_id: UUID,
    expected_content_hash: str,
    budget: dict[str, Any],
) -> ApprovalResult:
    """Atomically approve a hash-bound brief and enqueue its root task.

    The caller supplies a fresh SQLAlchemy session with no active transaction.
    The project row is locked before checking for an existing run, which makes
    duplicate dashboard/Telegram approvals converge on one durable run.
    """

    with session.begin():
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        brief = session.scalar(select(BriefRevision).where(BriefRevision.id == brief_id).with_for_update())
        if project is None or brief is None or brief.project_id != project_id:
            raise ApprovalConflict("project or brief not found")
        if brief.content_hash != expected_content_hash:
            raise StaleRevision("brief content hash no longer matches approval")

        existing = _existing_approval(session, project_id=project_id, brief_id=brief_id)
        if existing is not None:
            return existing

        active_states = {"queued", "running", "paused", "producing", "draft_review", "art_review", "packaging"}
        active_run = session.scalar(
            select(ProductionRun)
            .where(ProductionRun.project_id == project_id, ProductionRun.state.in_(active_states))
            .with_for_update()
        )
        if active_run is not None:
            raise ApprovalConflict("project already has an active production run")

        brief.approved_at = brief.approved_at or utc_now()
        project.active_brief_id = brief.id
        project.state = "producing"
        run = ProductionRun(project_id=project_id, approved_brief_id=brief.id, budget=budget, state="queued")
        session.add(run)
        session.flush()
        outline = Task(
            run_id=run.id,
            task_type="outline",
            input_revision_ids=[str(brief.id)],
            result_refs={},
            status="queued",
        )
        session.add(outline)
        session.flush()
        task = Task(
            run_id=run.id,
            parent_task_id=outline.id,
            task_type="production",
            dependencies=[str(outline.id)],
            input_revision_ids=[str(brief.id)],
            result_refs={},
            status="queued",
        )
        session.add(task)
        session.flush()
        review = Task(
            run_id=run.id,
            parent_task_id=task.id,
            task_type="review",
            dependencies=[str(task.id)],
            input_revision_ids=[str(brief.id)],
            result_refs={},
            status="queued",
        )
        session.add(review)
        session.flush()
        job = Job(
            task_id=task.id,
            job_type="production.start",
            payload={"run_id": str(run.id), "task_id": str(task.id), "cancellation_epoch": run.cancellation_epoch},
            dedupe_key=f"approval:{brief.id}:{expected_content_hash}",
            state="queued",
        )
        session.add(job)
        session.flush()
        outline_job = Job(
            task_id=outline.id,
            job_type="outline.start",
            payload={"run_id": str(run.id), "task_id": str(outline.id), "cancellation_epoch": run.cancellation_epoch},
            dedupe_key=f"outline:{brief.id}:{expected_content_hash}",
            state="queued",
        )
        session.add(outline_job)
        session.flush()
        review_job = Job(
            task_id=review.id,
            job_type="review.start",
            payload={"run_id": str(run.id), "task_id": str(review.id), "cancellation_epoch": run.cancellation_epoch},
            dedupe_key=f"review:{brief.id}:{expected_content_hash}",
            state="queued",
        )
        session.add(review_job)
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="run.approved",
            payload={"brief_id": str(brief.id), "run_id": str(run.id), "job_id": str(job.id)},
        )
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            kind="run.plan.created",
            payload={
                "brief_id": str(brief.id),
                "tasks": [
                    {
                        "task_id": str(candidate.id),
                        "task_type": candidate.task_type,
                        "parent_task_id": str(candidate.parent_task_id) if candidate.parent_task_id else None,
                        "dependencies": candidate.dependencies,
                        "input_revision_ids": candidate.input_revision_ids,
                        "job_id": str(candidate_job.id),
                        "job_type": candidate_job.job_type,
                        "dedupe_key": candidate_job.dedupe_key,
                    }
                    for candidate, candidate_job in ((outline, outline_job), (task, job), (review, review_job))
                ],
            },
        )
        return ApprovalResult(run_id=run.id, task_id=task.id, job_id=job.id)


def enqueue_orchestrator_agent(
    session: Session,
    *,
    project_id: UUID,
    turn_id: UUID,
    worker_id: str,
    generation: int,
    role: str,
    instruction: str,
    context: dict[str, Any] | None = None,
) -> OrchestratorAgentResult:
    """Queue one allowlisted child task under the project's active production run."""

    task_type_by_role = {
        "research": "orchestrator-research",
        "review": "review",
        "section-draft": "section-draft",
    }
    task_type = task_type_by_role.get(role)
    cleaned_instruction = instruction.strip()
    if task_type is None:
        raise ValueError("unsupported orchestrator agent role")
    if not cleaned_instruction:
        raise ValueError("agent instruction is required")
    if len(cleaned_instruction) > 8_000:
        raise ValueError("agent instruction is too long")
    instruction_hash = hashlib.sha256(cleaned_instruction.encode()).hexdigest()
    dedupe_key = f"orchestrator-agent:{turn_id}:{role}:{instruction_hash}"
    with session.begin():
        from app.orchestrator import locked_turn

        turn = locked_turn(session, turn_id=turn_id, worker_id=worker_id, generation=generation)
        if turn.project_id != project_id:
            raise ValueError("orchestrator turn is outside the project")
        existing_job = session.scalar(select(Job).where(Job.dedupe_key == dedupe_key).with_for_update())
        if existing_job is not None:
            existing_task = session.get(Task, existing_job.task_id)
            if existing_task is None:
                raise ValueError("spawned agent job has no task")
            return OrchestratorAgentResult(
                run_id=existing_task.run_id,
                task_id=existing_task.id,
                job_id=existing_job.id,
                task_type=existing_task.task_type,
            )
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        active_states = {"queued", "running", "paused", "producing", "draft_review", "art_review", "packaging"}
        run = session.scalar(
            select(ProductionRun)
            .where(ProductionRun.project_id == project_id, ProductionRun.state.in_(active_states))
            .order_by(ProductionRun.created_at.desc())
            .with_for_update()
        )
        if project is None or run is None:
            raise ValueError("an approved active production run is required before spawning an agent")
        result_refs: dict[str, Any] = {
            "instruction": cleaned_instruction,
            "role": role,
            "spawned_by_turn_id": str(turn_id),
            "instruction_hash": instruction_hash,
        }
        if context:
            result_refs["context"] = _bounded_result_refs(context, max_text=4_000)
        task = Task(
            run_id=run.id,
            task_type=task_type,
            dependencies=[],
            input_revision_ids=[],
            result_refs=result_refs,
            status="queued",
        )
        session.add(task)
        session.flush()
        job = Job(
            task_id=task.id,
            job_type=f"{task_type}.start",
            payload={"run_id": str(run.id), "task_id": str(task.id), "cancellation_epoch": run.cancellation_epoch},
            dedupe_key=dedupe_key,
            state="queued",
        )
        session.add(job)
        session.flush()
        run.state = "producing"
        project.state = "producing"
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="orchestrator.subagent.queued",
            payload={
                "turn_id": str(turn_id),
                "job_id": str(job.id),
                "task_id": str(task.id),
                "role": role,
                "task_type": task_type,
                "instruction": cleaned_instruction,
            },
        )
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="task.enqueued",
            payload={
                "job_id": str(job.id),
                "task_id": str(task.id),
                "task_type": task_type,
                "parent_task_id": None,
                "input_revision_ids": [],
                "dedupe_key": dedupe_key,
            },
        )
        return OrchestratorAgentResult(run_id=run.id, task_id=task.id, job_id=job.id, task_type=task_type)


def enqueue_art_revision(
    session: Session,
    *,
    project_id: UUID,
    artifact_id: UUID,
    note: str,
    manage_transaction: bool = True,
) -> ArtRevisionResult:
    """Create one durable artwork revision job for one immutable source artifact.

    The source artifact is never changed. The note hash is part of the job
    dedupe key, so repeated browser retries converge on one task and job.
    """

    cleaned_note = note.strip()
    if not cleaned_note:
        raise ValueError("art revision feedback is required")
    note_hash = hashlib.sha256(cleaned_note.encode()).hexdigest()
    dedupe_key = f"art-revision:{artifact_id}:{note_hash}"
    with (session.begin() if manage_transaction else nullcontext()):
        existing_job = session.scalar(select(Job).where(Job.dedupe_key == dedupe_key).with_for_update())
        if existing_job is not None:
            existing_task = session.get(Task, existing_job.task_id)
            if existing_task is None:
                raise ValueError("art revision job has no task")
            existing_run = session.get(ProductionRun, existing_task.run_id)
            if existing_run is None or existing_run.project_id != project_id:
                raise ValueError("art revision job is outside the project")
            source_id = UUID(existing_task.result_refs["source_artifact_id"])
            return ArtRevisionResult(existing_run.id, existing_task.id, existing_job.id, source_id)

        source = session.scalar(select(Artifact).where(Artifact.id == artifact_id).with_for_update())
        if source is None or not source.mime_type.lower().startswith("image/") or source.run_id is None:
            raise ValueError("source artwork is not revisionable")
        run = session.scalar(select(ProductionRun).where(ProductionRun.id == source.run_id).with_for_update())
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        if run is None or project is None or run.project_id != project_id:
            raise ValueError("source artwork is outside the project")
        if run.state in {"cancelled", "failed", "blocked"}:
            raise ValueError("production run is not accepting revisions")
        parent_task = session.scalar(
            select(Task).where(Task.run_id == run.id, Task.task_type == "production").order_by(Task.created_at.desc())
        )
        result_refs = {
            "source_artifact_id": str(source.id),
            "source_sha256": source.sha256,
            "feedback": cleaned_note[:4_000],
            "feedback_hash": note_hash,
        }
        task = Task(
            run_id=run.id,
            parent_task_id=parent_task.id if parent_task else None,
            task_type="art-revision",
            dependencies=[],
            input_revision_ids=[str(source.revision_id)] if source.revision_id else [],
            result_refs=result_refs,
            status="queued",
        )
        session.add(task)
        session.flush()
        job = Job(
            task_id=task.id,
            job_type="art-revision.start",
            payload={"run_id": str(run.id), "task_id": str(task.id), "cancellation_epoch": run.cancellation_epoch},
            dedupe_key=dedupe_key,
            state="queued",
        )
        session.add(job)
        session.flush()
        run.state = "producing"
        project.state = "producing"
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="art.revision.queued",
            payload={
                "job_id": str(job.id),
                "source_artifact_id": str(source.id),
                "source_sha256": source.sha256,
                "feedback": cleaned_note[:4_000],
                "feedback_hash": note_hash,
            },
        )
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="task.enqueued",
            payload={
                "job_id": str(job.id),
                "task_id": str(task.id),
                "task_type": task.task_type,
                "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
                "input_revision_ids": task.input_revision_ids,
                "dedupe_key": job.dedupe_key,
            },
        )
        return ArtRevisionResult(run.id, task.id, job.id, source.id)


def claim_job(session: Session, *, worker_id: str, lease_seconds: int = 60) -> JobLease | None:
    """Claim one eligible job with a committed PostgreSQL fencing generation."""

    now = utc_now()
    eligibility = or_(
        and_(Job.state.in_(["queued", "retry_wait"]), Job.available_at <= now),
        and_(Job.state == "running", Job.lease_until.is_not(None), Job.lease_until <= now),
    )
    with session.begin():
        rows = session.execute(
            select(Job, Task, ProductionRun)
            .join(Task, Task.id == Job.task_id)
            .join(ProductionRun, ProductionRun.id == Task.run_id)
            .where(eligibility)
            .order_by(Job.available_at, Job.job_type, Job.created_at)
            .with_for_update(skip_locked=True)
        ).all()
        row = None
        for candidate in rows:
            candidate_job, candidate_task, candidate_run = candidate
            if candidate_run.state in {"cancelled", "failed", "blocked"} or candidate_job.state == "cancelled":
                continue
            dependency_ids = [UUID(value) for value in (candidate_task.dependencies or [])]
            if dependency_ids:
                succeeded = set(
                    session.scalars(
                        select(Task.id).where(Task.id.in_(dependency_ids), Task.status == "succeeded")
                    ).all()
                )
                if succeeded != set(dependency_ids):
                    continue
            row = candidate
            break
        if row is None:
            return None
        job, task, run = row

        previous_attempt = session.scalar(
            select(Attempt)
            .where(Attempt.task_id == task.id, Attempt.status == "running")
            .with_for_update()
        )
        if previous_attempt is not None:
            previous_attempt.status = "expired"
            previous_attempt.finished_at = now

        job.state = "running"
        job.lease_owner = worker_id
        job.lease_until = now + timedelta(seconds=lease_seconds)
        job.fencing_generation += 1
        job.attempts += 1
        attempt = Attempt(
            task_id=task.id,
            attempt_no=job.attempts,
            input_revision_ids=task.input_revision_ids,
            provider=task.provider,
            model=task.model,
            session_id=task.session_id,
            status="running",
            fencing_generation=job.fencing_generation,
            lease_owner=worker_id,
            lease_until=job.lease_until,
            started_at=now,
        )
        session.add(attempt)
        session.flush()
        task.status = "running"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.claimed",
            payload={
                "job_id": str(job.id),
                "worker_id": worker_id,
                "generation": job.fencing_generation,
                "attempt_id": str(attempt.id),
            },
        )
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="agent.started",
            payload={
                "job_id": str(job.id),
                "attempt_id": str(attempt.id),
                "attempt_no": attempt.attempt_no,
                "worker_id": worker_id,
                "generation": job.fencing_generation,
                "task_type": task.task_type,
                "provider": task.provider,
                "model": task.model,
                "input_revision_ids": task.input_revision_ids,
                "started_at": now.isoformat(),
            },
        )
        return JobLease(
            job_id=job.id,
            task_id=task.id,
            run_id=run.id,
            attempt_id=attempt.id,
            generation=job.fencing_generation,
            cancellation_epoch=run.cancellation_epoch,
            lease_until=job.lease_until,
        )


def _locked_lease_context(
    session: Session, *, job_id: UUID, worker_id: str, generation: int
) -> tuple[Job, Task, ProductionRun, Attempt]:
    row = session.execute(
        select(Job, Task, ProductionRun)
        .join(Task, Task.id == Job.task_id)
        .join(ProductionRun, ProductionRun.id == Task.run_id)
        .where(Job.id == job_id)
        .with_for_update()
    ).first()
    if row is None:
        raise StaleLease("job lease is no longer current")
    job, task, run = row
    if run.state == "cancelled" or job.payload.get("cancellation_epoch") != run.cancellation_epoch:
        raise CancellationRejected("run cancellation epoch no longer matches")
    if (
        job.state != "running"
        or job.lease_owner != worker_id
        or job.fencing_generation != generation
        or job.lease_until is None
        or (
            job.lease_until.replace(tzinfo=timezone.utc) if job.lease_until.tzinfo is None else job.lease_until
        )
        < utc_now()
    ):
        raise StaleLease("job lease is no longer current")
    attempt = session.scalar(
        select(Attempt)
        .where(
            Attempt.task_id == task.id,
            Attempt.fencing_generation == generation,
            Attempt.lease_owner == worker_id,
        )
        .with_for_update()
    )
    if attempt is None:
        raise StaleLease("attempt lease is no longer current")
    return job, task, run, attempt


def heartbeat_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    lease_seconds: int = 60,
) -> HeartbeatResult:
    """Extend a live lease only when its owner and fencing generation match."""

    with session.begin():
        job, _, _, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        lease_until = utc_now() + timedelta(seconds=lease_seconds)
        job.lease_until = lease_until
        attempt.lease_until = lease_until
        return HeartbeatResult(lease_until=lease_until)


def checkpoint_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    checkpoint: dict[str, Any],
) -> None:
    """Persist a bounded worker checkpoint under the current fence."""

    with session.begin():
        job, task, run, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        attempt.result_refs = checkpoint
        task.result_refs = checkpoint
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.checkpointed",
            payload={"job_id": str(job.id), "generation": generation, "checkpoint": checkpoint},
        )


def complete_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    result_refs: dict[str, Any],
    manage_transaction: bool = True,
) -> None:
    """Commit a successful result only under the current lease and epoch."""

    with (session.begin() if manage_transaction else nullcontext()):
        job, task, run, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        project = session.scalar(select(Project).where(Project.id == run.project_id).with_for_update())
        now = utc_now()
        job.state = "succeeded"
        job.lease_owner = None
        job.lease_until = None
        task.status = "succeeded"
        task.result_refs = result_refs
        attempt.status = "succeeded"
        attempt.result_refs = result_refs
        attempt.finished_at = now
        attempt.lease_owner = None
        attempt.lease_until = None
        if run.state == "producing" and task.task_type == "review":
            run.state = "draft_review"
        if project is not None and project.state == "producing" and task.task_type == "review":
            project.state = "draft_review"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.completed",
            payload={"job_id": str(job.id), "generation": generation, "result_refs": result_refs},
        )
        started_at = attempt.started_at
        if started_at is not None and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        duration_seconds = max(0.0, (now - started_at).total_seconds()) if started_at is not None else None
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="agent.completed",
            payload={
                "job_id": str(job.id),
                "attempt_id": str(attempt.id),
                "attempt_no": attempt.attempt_no,
                "generation": generation,
                "task_type": task.task_type,
                "provider": task.provider,
                "model": task.model,
                "status": task.status,
                "finished_at": now.isoformat(),
                "duration_seconds": duration_seconds,
                "result_refs": _bounded_result_refs(result_refs),
            },
        )


def complete_task_result(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    result_refs: dict[str, Any],
    manage_transaction: bool = True,
) -> None:
    """Complete a bounded non-manuscript task result under its current fence."""

    complete_job(
        session,
        job_id=job_id,
        worker_id=worker_id,
        generation=generation,
        result_refs=result_refs,
        manage_transaction=manage_transaction,
    )


def _fail_running_attempts(session: Session, *, task_id: UUID, error_class: str) -> None:
    """Close active attempts when a run-level failure fences their jobs."""

    now = utc_now()
    attempts = session.scalars(
        select(Attempt).where(Attempt.task_id == task_id, Attempt.status == "running").with_for_update()
    ).all()
    for attempt in attempts:
        attempt.status = "failed"
        attempt.error_class = f"run_failed:{error_class}"[:128]
        attempt.finished_at = now
        attempt.lease_owner = None
        attempt.lease_until = None


def _fail_dependent_tasks(session: Session, *, failed_task: Task, run: ProductionRun, error_class: str) -> None:
    """Propagate a terminal task failure through every queued descendant."""

    tasks = session.scalars(select(Task).where(Task.run_id == run.id)).all()
    failed_ids = {str(failed_task.id)}
    pending = [failed_task.id]
    while pending:
        dependency_id = str(pending.pop(0))
        for dependent in tasks:
            if dependency_id not in (dependent.dependencies or []) or str(dependent.id) in failed_ids:
                continue
            if dependent.status in {"succeeded", "failed", "cancelled"}:
                failed_ids.add(str(dependent.id))
                pending.append(dependent.id)
                continue
            dependent.status = "failed"
            failed_ids.add(str(dependent.id))
            pending.append(dependent.id)
            dependent_job = session.scalar(select(Job).where(Job.task_id == dependent.id).with_for_update())
            if dependent_job is not None and dependent_job.state not in {"succeeded", "failed", "cancelled"}:
                dependent_job.state = "failed"
                dependent_job.error_class = f"dependency_failed:{error_class}"[:128]
                dependent_job.lease_owner = None
                dependent_job.lease_until = None
            _fail_running_attempts(session, task_id=dependent.id, error_class=error_class)
            append_event(
                session,
                project_id=run.project_id,
                run_id=run.id,
                task_id=dependent.id,
                kind="job.failed",
                payload={
                    "job_id": str(dependent_job.id) if dependent_job is not None else None,
                    "error_class": "dependency_failed",
                    "dependency_task_id": dependency_id,
                },
            )
    # A terminal failure closes the run as a unit: no sibling or remaining
    # task may become claimable while the failed run is being inspected.
    for remaining in tasks:
        if remaining.id == failed_task.id or remaining.status in {"succeeded", "failed", "cancelled"}:
            continue
        remaining.status = "failed"
        remaining_job = session.scalar(select(Job).where(Job.task_id == remaining.id).with_for_update())
        if remaining_job is not None and remaining_job.state not in {"succeeded", "failed", "cancelled"}:
            remaining_job.state = "failed"
            remaining_job.error_class = f"run_failed:{error_class}"[:128]
            remaining_job.lease_owner = None
            remaining_job.lease_until = None
        _fail_running_attempts(session, task_id=remaining.id, error_class=error_class)
        append_event(
            session, project_id=run.project_id, run_id=run.id, task_id=remaining.id,
            kind="job.failed", payload={"job_id": str(remaining_job.id) if remaining_job else None,
                                         "error_class": "run_failed", "failed_task_id": str(failed_task.id)},
        )


def fail_job(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    error_class: str,
    retryable: bool,
    retry_after: timedelta | None = None,
) -> None:
    """Persist a retry or terminal failure without permitting infinite retries."""

    with session.begin():
        job, task, run, attempt = _locked_lease_context(
            session, job_id=job_id, worker_id=worker_id, generation=generation
        )
        now = utc_now()
        attempt.status = "failed"
        attempt.error_class = error_class
        attempt.finished_at = now
        attempt.lease_owner = None
        attempt.lease_until = None
        job.error_class = error_class
        job.lease_owner = None
        job.lease_until = None
        if retryable and job.attempts < job.max_attempts:
            job.state = "retry_wait"
            job.available_at = now + (retry_after if retry_after is not None else timedelta(seconds=1))
            task.status = "retry_wait"
            event_kind = "job.retry_wait"
        else:
            job.state = "failed"
            task.status = "failed"
            event_kind = "job.failed"
            _fail_dependent_tasks(session, failed_task=task, run=run, error_class=error_class)
            run.state = "failed"
            project = session.scalar(select(Project).where(Project.id == run.project_id).with_for_update())
            if project is not None:
                project.state = "failed"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind=event_kind,
            payload={"job_id": str(job.id), "generation": generation, "error_class": error_class},
        )
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="agent.failed",
            payload={
                "job_id": str(job.id),
                "attempt_id": str(attempt.id),
                "attempt_no": attempt.attempt_no,
                "generation": generation,
                "task_type": task.task_type,
                "status": task.status,
                "error_class": error_class,
                "retryable": retryable and job.state == "retry_wait",
                "finished_at": now.isoformat(),
            },
        )


def pause_job(session: Session, *, job_id: UUID, reason: str) -> None:
    """Persist a pause so a supervisor restart cannot lose the operator decision."""

    with session.begin():
        row = session.execute(
            select(Job, Task, ProductionRun)
            .join(Task, Task.id == Job.task_id)
            .join(ProductionRun, ProductionRun.id == Task.run_id)
            .where(Job.id == job_id)
            .with_for_update()
        ).first()
        if row is None:
            raise ApprovalConflict("job not found")
        job, task, run = row
        if job.state in {"succeeded", "failed", "cancelled"}:
            raise ApprovalConflict("job is not pausable")
        job.state = "paused"
        job.lease_owner = None
        job.lease_until = None
        task.status = "paused"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.paused",
            payload={"job_id": str(job.id), "reason": reason},
        )


def resume_job(session: Session, *, job_id: UUID) -> None:
    """Make a persisted paused job eligible for a new fenced attempt."""

    with session.begin():
        row = session.execute(
            select(Job, Task, ProductionRun)
            .join(Task, Task.id == Job.task_id)
            .join(ProductionRun, ProductionRun.id == Task.run_id)
            .where(Job.id == job_id)
            .with_for_update()
        ).first()
        if row is None:
            raise ApprovalConflict("job not found")
        job, task, run = row
        if job.state != "paused":
            raise ApprovalConflict("job is not paused")
        job.state = "queued"
        job.available_at = utc_now()
        task.status = "queued"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.resumed",
            payload={"job_id": str(job.id)},
        )


def cancel_run(session: Session, *, run_id: UUID, reason: str) -> int:
    """Advance the cancellation epoch before cancelling owned jobs."""

    with session.begin():
        run = session.scalar(select(ProductionRun).where(ProductionRun.id == run_id).with_for_update())
        if run is None:
            raise ApprovalConflict("run not found")
        run.cancellation_epoch += 1
        run.state = "cancelled"
        task_ids = select(Task.id).where(Task.run_id == run.id)
        session.execute(
            update(Job)
            .where(Job.task_id.in_(task_ids), Job.state.not_in(["succeeded", "failed"]))
            .values(state="cancelled", lease_owner=None, lease_until=None)
        )
        session.execute(
            update(Task)
            .where(Task.run_id == run.id, Task.status.not_in(["succeeded", "failed"]))
            .values(status="cancelled")
        )
        session.execute(
            update(Attempt)
            .where(Attempt.task_id.in_(task_ids), Attempt.status == "running")
            .values(status="cancelled", lease_owner=None, lease_until=None, finished_at=utc_now())
        )
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            kind="run.cancelled",
            payload={"run_id": str(run.id), "cancellation_epoch": run.cancellation_epoch, "reason": reason},
        )
        return run.cancellation_epoch
