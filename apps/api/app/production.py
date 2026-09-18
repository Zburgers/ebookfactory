"""Fenced acceptance of bounded production text into document state."""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import append_event
from app.jobs import CancellationRejected, StaleLease
from app.models import Attempt, Job, Project, ProductionRun, Section, SectionRevision, Task, utc_now


@dataclass(frozen=True)
class ProductionOutput:
    project_id: UUID
    run_id: UUID
    task_id: UUID
    revision_id: UUID
    content_hash: str
    duplicate: bool


def accept_production_output(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    content: str,
    provider: str | None = None,
    model: str | None = None,
) -> ProductionOutput:
    """Persist one fenced output as the latest revision of the opening section."""

    if not content.strip():
        raise ValueError("production output is empty")
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    with session.begin():
        row = session.execute(
            select(Job, Task, ProductionRun, Project)
            .join(Task, Task.id == Job.task_id)
            .join(ProductionRun, ProductionRun.id == Task.run_id)
            .join(Project, Project.id == ProductionRun.project_id)
            .where(Job.id == job_id)
            .with_for_update()
        ).first()
        if row is None:
            raise StaleLease("job lease is no longer current")
        job, task, run, project = row
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
        if provider:
            task.provider = provider
        if model:
            task.model = model
        attempt = session.scalar(
            select(Attempt)
            .where(Attempt.task_id == task.id, Attempt.fencing_generation == generation)
            .with_for_update()
        )
        if attempt is not None:
            if provider:
                attempt.provider = provider
            if model:
                attempt.model = model
        run.state = "producing"
        project.state = "producing"

        section = session.scalar(
            select(Section)
            .where(Section.project_id == project.id, Section.order_no == 1)
            .with_for_update()
        )
        if section is None:
            section = Section(project_id=project.id, order_no=1, heading="Draft manuscript")
            session.add(section)
            session.flush()
        latest = session.scalar(
            select(SectionRevision)
            .where(SectionRevision.section_id == section.id)
            .order_by(SectionRevision.revision.desc())
            .with_for_update()
        )
        if latest is not None and latest.content_hash == content_hash:
            revision = latest
            duplicate = True
        else:
            revision = SectionRevision(
                section_id=section.id,
                revision=(latest.revision if latest else 0) + 1,
                content=content,
                summary="Pi production output",
                parent_revision_id=latest.id if latest else None,
                source_refs=[],
                knowledge_refs=[],
                approval_status="draft",
                content_hash=content_hash,
            )
            session.add(revision)
            session.flush()
            duplicate = False
            append_event(
                session,
                project_id=project.id,
                run_id=run.id,
                task_id=task.id,
                kind="production.output.accepted",
                payload={"revision_id": str(revision.id), "content_hash": content_hash},
            )
        return ProductionOutput(
            project_id=project.id,
            run_id=run.id,
            task_id=task.id,
            revision_id=revision.id,
            content_hash=content_hash,
            duplicate=duplicate,
        )
