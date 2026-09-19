"""Immutable artifact writes and deterministic Markdown rendering."""

import hashlib
import os
import tempfile
from contextlib import nullcontext
from pathlib import Path
from uuid import UUID, UUID as UUIDType, uuid4

from sqlalchemy import event
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Section, SectionRevision, UsageCall


class InvalidArtifactPath(ValueError):
    """Raised when an output path escapes the private artifact root."""


def _pending_path(root: Path, artifact_id: UUID) -> Path:
    return root.resolve() / f".pending-{artifact_id}"


def _remove_pending(session: Session) -> None:
    for pending, _target in session.info.pop("pending_artifacts", []):
        Path(pending).unlink(missing_ok=True)


def _finalize_pending(session: Session) -> None:
    for pending, target in session.info.pop("pending_artifacts", []):
        _finalize_one(Path(pending), Path(target))


@event.listens_for(Session, "after_commit")
def _finalize_committed_artifacts(session: Session) -> None:
    _finalize_pending(session)


@event.listens_for(Session, "after_rollback")
def _remove_rolled_back_artifacts(session: Session) -> None:
    _remove_pending(session)


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


def artifact_file_status(
    root: Path,
    *,
    relative_path: str,
    byte_count: int,
    sha256: str,
) -> tuple[str, str | None]:
    """Return a bounded availability result for one immutable artifact file."""

    try:
        path = safe_artifact_path(root, relative_path)
    except InvalidArtifactPath:
        return "invalid_path", "Artifact path is invalid for the configured artifact store."
    if not path.is_file():
        return "missing", "Artifact file is not present on the configured artifact store."
    try:
        if path.stat().st_size != byte_count:
            return "integrity_failed", "Artifact size does not match the recorded immutable value."
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            return "integrity_failed", "Artifact bytes do not match the recorded immutable hash."
    except OSError:
        return "unreadable", "Artifact file could not be read from the configured artifact store."
    return "available", None


def write_artifact(
    session: Session,
    *,
    root: Path,
    relative_path: str,
    content: bytes,
    mime_type: str,
    run_id: UUID | None = None,
    attempt_id: UUID | None = None,
    usage_call_id: UUID | None = None,
    revision_id: UUID | None = None,
    max_bytes: int = 50 * 1024 * 1024,
    manage_transaction: bool = True,
) -> Artifact:
    """Stage, hash and atomically register one immutable artifact."""

    if len(content) > max_bytes:
        raise ValueError("artifact exceeds size limit")
    if usage_call_id is not None:
        usage_call = session.scalar(select(UsageCall).where(UsageCall.id == usage_call_id))
        if (
            usage_call is None
            or usage_call.purpose != "art"
            or attempt_id is None
            or usage_call.attempt_id != attempt_id
        ):
            raise ValueError("usage call binding does not match art artifact attempt")
    target = safe_artifact_path(root, relative_path)
    root.resolve().mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise FileExistsError("artifact path is immutable")
    digest = hashlib.sha256(content).hexdigest()
    artifact_id = uuid4()
    pending = _pending_path(root, artifact_id)
    fd, temp_name = tempfile.mkstemp(prefix=".stage-", dir=root.resolve())
    try:
        with os.fdopen(fd, "wb") as staged:
            staged.write(content)
            staged.flush()
            os.fsync(staged.fileno())
        os.link(temp_name, pending)
        Path(temp_name).unlink(missing_ok=True)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
        raise
    try:
        with (session.begin() if manage_transaction else nullcontext()):
            artifact = Artifact(
                id=artifact_id,
                run_id=run_id,
                attempt_id=attempt_id,
                usage_call_id=usage_call_id,
                revision_id=revision_id,
                relative_path=relative_path,
                mime_type=mime_type,
                byte_count=len(content),
                sha256=digest,
                validation_state="generated",
            )
            session.add(artifact)
            session.flush()
            session.info.setdefault("pending_artifacts", []).append((str(pending), str(target)))
            session.expunge(artifact)
            result = artifact
        return result
    except Exception:
        pending.unlink(missing_ok=True)
        raise


def _finalize_one(pending: Path, target: Path) -> None:
    if not pending.exists():
        return
    if target.exists() or target.is_symlink():
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(pending.read_bytes()).hexdigest():
            pending.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(pending, target)
    except FileExistsError:
        return
    pending.unlink(missing_ok=True)


def reconcile_pending_artifacts(session: Session, root: Path) -> None:
    """Finalize committed pending artifacts and remove unregistered leftovers."""

    root_path = root.resolve()
    if not root_path.exists():
        return
    committed = {artifact.id: artifact for artifact in session.scalars(select(Artifact)).all()}
    for pending in root_path.glob(".pending-*"):
        try:
            artifact_id = UUIDType(pending.name.removeprefix(".pending-"))
        except ValueError:
            pending.unlink(missing_ok=True)
            continue
        artifact = committed.get(artifact_id)
        if artifact is None:
            pending.unlink(missing_ok=True)
            continue
        target = safe_artifact_path(root_path, artifact.relative_path)
        if pending.stat().st_size != artifact.byte_count or hashlib.sha256(pending.read_bytes()).hexdigest() != artifact.sha256:
            continue
        _finalize_one(pending, target)


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
