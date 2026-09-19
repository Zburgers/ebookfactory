"""Fenced acceptance of bounded production text into document state."""

import hashlib
import re
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import append_event
from app.jobs import CancellationRejected, StaleLease
from app.models import Attempt, BriefRevision, Job, Project, ProductionRun, Section, SectionRevision, Task, utc_now


@dataclass(frozen=True)
class ProductionOutput:
    project_id: UUID
    run_id: UUID
    task_id: UUID
    revision_id: UUID
    content_hash: str
    duplicate: bool


@dataclass(frozen=True)
class ParsedSection:
    heading: str
    content: str


def validate_production_text(content: str, *, page_target: bool) -> None:
    if not content.strip():
        raise ValueError("production output is empty")
    lowered = content.lower()
    if any(marker in lowered for marker in ("todo:", "[insert", "lorem ipsum", "tbd", "write this later")):
        raise ValueError("production output contains a placeholder")
    if page_target and len(parse_production_sections(content, page_target=True)) < 2:
        raise ValueError("page-target production requires multiple manuscript sections")


def parse_production_sections(content: str, *, page_target: bool) -> list[ParsedSection]:
    headings = list(re.finditer(r"(?m)^##[ \t]+([^\n#].*?)\s*$", content))
    if not headings:
        if page_target:
            return []
        return [ParsedSection("Draft manuscript", content.strip())]
    sections: list[ParsedSection] = []
    for index, match in enumerate(headings):
        body_start = match.end()
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        body = content[body_start:body_end].strip()
        if not body:
            raise ValueError(f"section '{match.group(1).strip()}' is incomplete")
        sections.append(ParsedSection(match.group(1).strip(), body))
    return sections


def accept_production_output(
    session: Session,
    *,
    job_id: UUID,
    worker_id: str,
    generation: int,
    content: str,
    provider: str | None = None,
    model: str | None = None,
    manage_transaction: bool = True,
) -> ProductionOutput:
    """Persist one fenced output as immutable revisions for its manuscript sections."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    with (session.begin() if manage_transaction else nullcontext()):
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
        brief = session.get(BriefRevision, run.approved_brief_id)
        structured_brief = brief.structured_brief if brief else {}
        page_target = bool(structured_brief.get("target_pages"))
        validate_production_text(content, page_target=page_target)
        parsed_sections = parse_production_sections(content, page_target=page_target)
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

        first_revision = None
        duplicate = True
        for order_no, parsed in enumerate(parsed_sections, start=1):
            section = session.scalar(
                select(Section).where(Section.project_id == project.id, Section.order_no == order_no).with_for_update()
            )
            if section is None:
                section = Section(project_id=project.id, order_no=order_no, heading=parsed.heading)
                session.add(section)
                session.flush()
            elif section.heading != parsed.heading:
                section.heading = parsed.heading
            section_hash = hashlib.sha256(parsed.content.encode()).hexdigest()
            latest = session.scalar(
                select(SectionRevision).where(SectionRevision.section_id == section.id)
                .order_by(SectionRevision.revision.desc()).with_for_update()
            )
            if latest is not None and latest.content_hash == section_hash:
                revision = latest
            else:
                revision = SectionRevision(
                    section_id=section.id, revision=(latest.revision if latest else 0) + 1,
                    content=parsed.content, summary="Pi production output",
                    parent_revision_id=latest.id if latest else None, source_refs=[], knowledge_refs=[],
                    approval_status="draft", content_hash=section_hash,
                )
                session.add(revision)
                session.flush()
                duplicate = False
            first_revision = first_revision or revision
        if not duplicate:
            append_event(session, project_id=project.id, run_id=run.id, task_id=task.id,
                         kind="production.output.accepted",
                         payload={"revision_id": str(first_revision.id), "content_hash": content_hash,
                                  "section_count": len(parsed_sections)})
        return ProductionOutput(
            project_id=project.id,
            run_id=run.id,
            task_id=task.id,
            revision_id=first_revision.id,
            content_hash=content_hash,
            duplicate=duplicate,
        )
