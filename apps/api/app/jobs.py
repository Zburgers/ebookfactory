"""Transactional approval and durable job enqueue primitives."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import Attempt, BriefRevision, Job, Project, ProductionRun, Task, utc_now


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


def _existing_approval(session: Session, *, project_id: UUID, brief_id: UUID) -> ApprovalResult | None:
    statement = (
        select(ProductionRun, Task, Job)
        .join(Task, Task.run_id == ProductionRun.id)
        .join(Job, Job.task_id == Task.id)
        .where(ProductionRun.project_id == project_id, ProductionRun.approved_brief_id == brief_id)
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
        task = Task(
            run_id=run.id,
            task_type="production",
            input_revision_ids=[str(brief.id)],
            result_refs={},
            status="queued",
        )
        session.add(task)
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
        append_event(
            session,
            project_id=project_id,
            run_id=run.id,
            task_id=task.id,
            kind="run.approved",
            payload={"brief_id": str(brief.id), "run_id": str(run.id), "job_id": str(job.id)},
        )
        return ApprovalResult(run_id=run.id, task_id=task.id, job_id=job.id)


def claim_job(session: Session, *, worker_id: str, lease_seconds: int = 60) -> JobLease | None:
    """Claim one eligible job with a committed PostgreSQL fencing generation."""

    now = utc_now()
    eligibility = or_(
        and_(Job.state.in_(["queued", "retry_wait"]), Job.available_at <= now),
        and_(Job.state == "running", Job.lease_until.is_not(None), Job.lease_until <= now),
    )
    with session.begin():
        row = session.execute(
            select(Job, Task, ProductionRun)
            .join(Task, Task.id == Job.task_id)
            .join(ProductionRun, ProductionRun.id == Task.run_id)
            .where(eligibility)
            .order_by(Job.available_at, Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if row is None:
            return None
        job, task, run = row
        if run.state == "cancelled" or job.state == "cancelled":
            return None

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
        or job.lease_until < utc_now()
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
) -> None:
    """Commit a successful result only under the current lease and epoch."""

    with session.begin():
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
        if run.state == "producing":
            run.state = "draft_review"
        if project is not None and project.state == "producing":
            project.state = "draft_review"
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind="job.completed",
            payload={"job_id": str(job.id), "generation": generation, "result_refs": result_refs},
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
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            task_id=task.id,
            kind=event_kind,
            payload={"job_id": str(job.id), "generation": generation, "error_class": error_class},
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
        append_event(
            session,
            project_id=run.project_id,
            run_id=run.id,
            kind="run.cancelled",
            payload={"run_id": str(run.id), "cancellation_epoch": run.cancellation_epoch, "reason": reason},
        )
        return run.cancellation_epoch
