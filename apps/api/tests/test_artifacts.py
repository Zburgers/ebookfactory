from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.artifacts import InvalidArtifactPath, safe_artifact_path, write_artifact
from app.models import Artifact


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
