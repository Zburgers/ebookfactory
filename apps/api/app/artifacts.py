"""Immutable artifact writes and deterministic Markdown rendering."""

import hashlib
import os
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Section, SectionRevision


class InvalidArtifactPath(ValueError):
    """Raised when an output path escapes the private artifact root."""


def safe_artifact_path(root: Path, relative_path: str) -> Path:
    """Resolve a relative immutable path and reject traversal/symlink escapes."""

    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or "\0" in relative_path:
        raise InvalidArtifactPath("artifact path must be relative and traversal-free")
    root_path = root.resolve()
    target = (root_path / candidate).resolve(strict=False)
    if target != root_path and root_path not in target.parents:
        raise InvalidArtifactPath("artifact path escapes root")
    current = root_path
    for part in candidate.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise InvalidArtifactPath("artifact path crosses a symlink")
    return target


def write_artifact(
    session: Session,
    *,
    root: Path,
    relative_path: str,
    content: bytes,
    mime_type: str,
    run_id: UUID | None = None,
    attempt_id: UUID | None = None,
    revision_id: UUID | None = None,
    max_bytes: int = 50 * 1024 * 1024,
) -> Artifact:
    """Stage, hash and atomically register one immutable artifact."""

    if len(content) > max_bytes:
        raise ValueError("artifact exceeds size limit")
    target = safe_artifact_path(root, relative_path)
    root.resolve().mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise FileExistsError("artifact path is immutable")
    digest = hashlib.sha256(content).hexdigest()
    fd, temp_name = tempfile.mkstemp(prefix=".pending-", dir=root.resolve())
    try:
        with os.fdopen(fd, "wb") as staged:
            staged.write(content)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(temp_name, target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    with session.begin():
        artifact = Artifact(
            run_id=run_id,
            attempt_id=attempt_id,
            revision_id=revision_id,
            relative_path=relative_path,
            mime_type=mime_type,
            byte_count=len(content),
            sha256=digest,
            validation_state="generated",
        )
        session.add(artifact)
        session.flush()
        session.expunge(artifact)
        return artifact


def render_markdown(session: Session, *, project_id: UUID) -> str:
    """Render latest section revisions in order from persisted document state."""

    sections = session.scalars(select(Section).where(Section.project_id == project_id).order_by(Section.order_no)).all()
    rendered: list[str] = []
    for section in sections:
        revision = session.scalar(
            select(SectionRevision)
            .where(SectionRevision.section_id == section.id)
            .order_by(SectionRevision.revision.desc())
        )
        if revision is not None:
            rendered.append(f"# {section.heading}\n\n{revision.content.strip()}\n")
    return "\n".join(rendered)
