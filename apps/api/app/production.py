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


def expand_outline_sections(session: Session, *, outline_task: Task, production_task: Task, outline_text: str) -> list[Task]:
    """Create stable section identities/jobs and gate production on every section."""
    run = session.get(ProductionRun, outline_task.run_id)
    if run is None:
        raise ValueError("production run not found")
    brief = session.get(BriefRevision, run.approved_brief_id)
    page_target = bool(brief and brief.structured_brief.get("target_pages"))
    parsed = parse_production_sections(outline_text, page_target=page_target)
    minimum, maximum = (8, 15) if page_target else (1, 15)
    if not minimum <= len(parsed) <= maximum:
        raise ValueError(f"outline must contain {minimum} to {maximum} sections")
    # Preserve the legacy single-section word-target path. Multi-section and
    # all page-target runs use durable section tasks; a one-section outline
    # remains directly producible for existing callers.
    if not page_target and len(parsed) == 1:
        production_task.dependencies = []
        return []
    existing = {task.id: task for task in session.scalars(select(Task).where(Task.run_id == run.id)).all()}
    sections: list[Task] = []
    for order_no, item in enumerate(parsed, start=1):
        section = session.scalar(select(Section).where(Section.project_id == run.project_id, Section.order_no == order_no).with_for_update())
        if section is None:
            section = Section(project_id=run.project_id, order_no=order_no, heading=item.heading)
            session.add(section)
            session.flush()
        else:
            section.heading = item.heading
        task = next((candidate for candidate in existing.values() if candidate.task_type == "section-draft" and candidate.result_refs.get("section_id") == str(section.id)), None)
        if task is None:
            task = Task(run_id=run.id, parent_task_id=outline_task.id, task_type="section-draft", dependencies=[str(outline_task.id)], input_revision_ids=outline_task.input_revision_ids, result_refs={"section_id": str(section.id), "heading": item.heading, "outline": item.content}, status="queued")
            session.add(task)
            session.flush()
            session.add(Job(task_id=task.id, job_type="section-draft.start", payload={"run_id": str(run.id), "task_id": str(task.id), "cancellation_epoch": run.cancellation_epoch}, dedupe_key=f"section:{outline_task.id}:{order_no}", state="queued"))
        else:
            task.result_refs = {**task.result_refs, "heading": item.heading, "outline": item.content}
        sections.append(task)
    production_task.dependencies = [str(task.id) for task in sections]
    return sections


def assemble_section_revisions(
    session: Session,
    *,
    project_id: UUID,
    run_id: UUID | None = None,
    section_task_ids: list[UUID] | None = None,
) -> str:
    """Assemble only the current run's successful section-task dependencies."""
    if not section_task_ids:
        raise ValueError("assembly requires section task dependencies")
    tasks = session.scalars(select(Task).where(Task.id.in_(section_task_ids))).all()
    if len(tasks) != len(set(section_task_ids)) or any(
        task.task_type != "section-draft"
        or task.status != "succeeded"
        or (run_id is not None and task.run_id != run_id)
        for task in tasks
    ):
        if run_id is not None and any(task.run_id != run_id for task in tasks):
            raise ValueError("assembly dependencies are not from the same production run")
        raise ValueError("assembly section dependencies are incomplete")
    section_ids: list[UUID] = []
    ordered: list[tuple[Section, SectionRevision]] = []
    for task in tasks:
        value = task.result_refs.get("section_id")
        if not value:
            raise ValueError("section task has no stable section")
        section_id = UUID(value)
        section = session.get(Section, section_id)
        if section is None or section.project_id != project_id:
            raise ValueError("assembly section is outside the project")
        revision_value = task.result_refs.get("revision_id")
        if revision_value:
            revision = session.get(SectionRevision, UUID(revision_value))
            if revision is None or revision.section_id != section_id:
                raise ValueError("assembly revision is not fenced to its section")
        else:
            # Legacy section tasks may not carry a revision reference; use the
            # latest immutable revision only for that compatibility path.
            revision = session.scalar(
                select(SectionRevision)
                .where(SectionRevision.section_id == section_id)
                .order_by(SectionRevision.revision.desc())
                .limit(1)
            )
            if revision is None:
                raise ValueError("assembly section revisions are incomplete")
        section_ids.append(section_id)
        ordered.append((section, revision))
    if len(ordered) != len(set(section_ids)):
        raise ValueError("assembly section revisions are incomplete")
    return "\n\n".join(f"## {section.heading}\n\n{revision.content}" for section, revision in sorted(ordered, key=lambda pair: pair[0].order_no))


def validate_production_text(content: str, *, page_target: bool, target_pages: dict | None = None) -> None:
    if not content.strip():
        raise ValueError("production output is empty")
    lowered = content.lower()
    if any(marker in lowered for marker in ("todo:", "[insert", "lorem ipsum", "tbd", "write this later")):
        raise ValueError("production output contains a placeholder")
    if page_target:
        section_count = len(parse_production_sections(content, page_target=True))
        if not 8 <= section_count <= 15:
            raise ValueError("page-target production requires 8 to 15 sections")
    if page_target and target_pages:
        word_count = len(re.findall(r"\b[\w'-]+\b", content))
        minimum_words = int(target_pages["minimum"]) * 100
        maximum_words = int(target_pages["maximum"]) * 180
        if word_count < minimum_words:
            raise ValueError("production output is too short for the requested page range")
        if word_count > maximum_words:
            raise ValueError("production output is too long for the requested page range")


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
        validate_production_text(content, page_target=page_target, target_pages=structured_brief.get("target_pages"))
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
