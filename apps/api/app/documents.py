"""Immutable brief and manuscript revision helpers."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BriefRevision, Section, SectionRevision, utc_now


@dataclass(frozen=True)
class BriefResult:
    brief_id: UUID
    content_hash: str


@dataclass(frozen=True)
class SectionResult:
    section_id: UUID
    revision_id: UUID
    revision: int
    content_hash: str


def create_brief_revision(
    session: Session,
    *,
    project_id: UUID,
    structured_brief: dict,
) -> BriefResult:
    """Persist a new brief revision with a deterministic content hash."""

    encoded = json.dumps(structured_brief, sort_keys=True, separators=(",", ":")).encode()
    content_hash = hashlib.sha256(encoded).hexdigest()
    with session.begin():
        revision = (session.scalar(
            select(BriefRevision.revision)
            .where(BriefRevision.project_id == project_id)
            .order_by(BriefRevision.revision.desc())
            .limit(1)
        ) or 0) + 1
        brief = BriefRevision(
            project_id=project_id,
            revision=revision,
            structured_brief=structured_brief,
            content_hash=content_hash,
        )
        session.add(brief)
        session.flush()
        return BriefResult(brief_id=brief.id, content_hash=content_hash)


def create_section(session: Session, *, project_id: UUID, order_no: int, heading: str) -> UUID:
    """Create a stable section identity before any content revisions."""

    with session.begin():
        section = Section(project_id=project_id, order_no=order_no, heading=heading)
        session.add(section)
        session.flush()
        return section.id


def save_section_revision(
    session: Session,
    *,
    section_id: UUID,
    content: str,
    summary: str,
    expected_parent_revision_id: UUID | None = None,
    source_refs: list[str] | None = None,
    knowledge_refs: list[str] | None = None,
) -> SectionResult:
    """Append an immutable section revision and reject stale editor writes."""

    content_hash = hashlib.sha256(content.encode()).hexdigest()
    with session.begin():
        section = session.scalar(select(Section).where(Section.id == section_id).with_for_update())
        if section is None:
            raise ValueError("section not found")
        latest = session.scalar(
            select(SectionRevision)
            .where(SectionRevision.section_id == section_id)
            .order_by(SectionRevision.revision.desc())
            .with_for_update()
        )
        if expected_parent_revision_id is not None and (latest is None or latest.id != expected_parent_revision_id):
            raise ValueError("section revision is stale")
        revision = (latest.revision if latest else 0) + 1
        row = SectionRevision(
            section_id=section_id,
            revision=revision,
            content=content,
            summary=summary,
            parent_revision_id=latest.id if latest else None,
            source_refs=source_refs or [],
            knowledge_refs=knowledge_refs or [],
            approval_status="draft",
            content_hash=content_hash,
        )
        session.add(row)
        session.flush()
        return SectionResult(
            section_id=section_id,
            revision_id=row.id,
            revision=revision,
            content_hash=content_hash,
        )
