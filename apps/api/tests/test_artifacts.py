from pathlib import Path
import base64
import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.artifacts import InvalidArtifactPath, reconcile_pending_artifacts, safe_artifact_path, write_artifact
from app.main import ProductionArtRequest, _decode_production_art
from app.models import Artifact
from app.main import _verify_existing_production_artifact


def test_artifact_paths_reject_traversal_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "link").symlink_to(tmp_path / "outside", target_is_directory=True)

    with pytest.raises(InvalidArtifactPath):
        safe_artifact_path(root, "../outside.txt")
    with pytest.raises(InvalidArtifactPath):
        safe_artifact_path(root, "link/escape.txt")


def test_artifact_write_is_hashed_and_immutable(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'artifact.db'}")
    Artifact.__table__.create(engine)
    session = Session(engine)
    artifact = write_artifact(
        session,
        root=tmp_path / "artifacts",
        relative_path="run-1/book.md",
        content=b"# A book\n",
        mime_type="text/markdown",
    )

    assert artifact.byte_count == 9
    assert (tmp_path / "artifacts/run-1/book.md").read_bytes() == b"# A book\n"
    with pytest.raises(FileExistsError):
        write_artifact(
            session,
            root=tmp_path / "artifacts",
            relative_path="run-1/book.md",
            content=b"changed",
            mime_type="text/markdown",
        )


def test_existing_production_artifact_tampering_is_rejected(tmp_path: Path) -> None:
    content = b"# A book\n"
    run_id, revision_id = uuid4(), uuid4()
    artifact = Artifact(run_id=run_id, revision_id=revision_id, relative_path="book.md", mime_type="text/markdown", byte_count=len(content), sha256=hashlib.sha256(content).hexdigest(), validation_state="generated")
    path = tmp_path / "book.md"
    path.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="does not match"):
        _verify_existing_production_artifact(artifact=artifact, path=path, run_id=run_id, revision_id=revision_id, content=content)


def test_existing_production_artifact_usage_binding_is_rejected(tmp_path: Path) -> None:
    content = b"# A book\n"
    run_id, revision_id = uuid4(), uuid4()
    expected_attempt_id, expected_usage_call_id = uuid4(), uuid4()
    path = tmp_path / "cover.png"
    path.write_bytes(content)
    for actual_attempt_id, actual_usage_call_id in ((uuid4(), uuid4()), (None, None)):
        artifact = Artifact(
            run_id=run_id,
            revision_id=revision_id,
            attempt_id=actual_attempt_id,
            usage_call_id=actual_usage_call_id,
            relative_path="cover.png",
            mime_type="image/png",
            byte_count=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            validation_state="generated",
        )
        with pytest.raises(ValueError, match="does not match"):
            _verify_existing_production_artifact(
                artifact=artifact,
                path=path,
                run_id=run_id,
                revision_id=revision_id,
                content=content,
                mime_type="image/png",
                attempt_id=expected_attempt_id,
                usage_call_id=expected_usage_call_id,
            )


def test_pending_artifact_commits_and_reconciles_after_crash(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'pending.db'}")
    Artifact.__table__.create(engine)
    root = tmp_path / "artifacts"
    session = Session(engine)
    artifact = write_artifact(
        session,
        root=root,
        relative_path="run-1/book.md",
        content=b"pending content",
        mime_type="text/markdown",
        manage_transaction=False,
    )
    assert list(root.rglob(".pending-*"))
    session.commit()
    assert (root / "run-1/book.md").read_bytes() == b"pending content"
    assert not list(root.rglob(".pending-*"))
    assert artifact.id is not None

    crash_id = uuid4()
    crash_content = b"crash recovery"
    session.add(Artifact(
        id=crash_id,
        relative_path="run-crash/book.md",
        mime_type="text/markdown",
        byte_count=len(crash_content),
        sha256=hashlib.sha256(crash_content).hexdigest(),
        validation_state="generated",
    ))
    session.commit()
    crash_pending = root / f".pending-{crash_id}"
    crash_pending.write_bytes(crash_content)
    reconcile_pending_artifacts(session, root)
    assert (root / "run-crash/book.md").read_bytes() == crash_content
    assert not crash_pending.exists()

    orphan = root / ".pending-orphan"
    orphan.write_bytes(b"orphan")
    reconcile_pending_artifacts(session, root)
    assert not orphan.exists()


def test_pending_artifact_rolls_back_without_final_file(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'pending-rollback.db'}")
    Artifact.__table__.create(engine)
    root = tmp_path / "artifacts"
    session = Session(engine)
    write_artifact(
        session,
        root=root,
        relative_path="run-2/book.md",
        content=b"rolled back",
        mime_type="text/markdown",
        manage_transaction=False,
    )
    session.rollback()
    assert not (root / "run-2/book.md").exists()
    assert not list(root.rglob(".pending-*"))


def test_production_art_fixture_validates_mime_filename_size_and_signature() -> None:
    content = b"\x89PNG\r\n\x1a\nfixture"
    payload = ProductionArtRequest(filename="cover.png", mime_type="image/png", byte_count=len(content), content_base64=base64.b64encode(content).decode())
    filename, decoded = _decode_production_art(payload=payload)
    assert filename == "cover.png"
    assert decoded == content
