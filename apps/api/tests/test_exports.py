import io
import hashlib
import zipfile
from pathlib import Path
from uuid import uuid4

from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.exports import PACKAGE_FILES, export_book
from app.main import create_app
from app.models import Artifact, Base, BriefRevision, ProductionRun, Project, Section, SectionRevision
from app.settings import Settings


def test_export_package_generates_all_formats_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'exports.db'}")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    revision_id = uuid4()
    with Session(engine) as session:
        project = Project(id=project_id, title="Export Fixture", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        session.add_all([project, section])
        session.flush()
        revision = SectionRevision(
            id=revision_id,
            section_id=section.id,
            revision=1,
            content="# The Morning Book\n\n## Chapter One\n\nA complete short story.",
            summary="fixture",
            source_refs=[],
            knowledge_refs=[],
            approval_status="draft",
            content_hash="a" * 64,
        )
        session.add(revision)
        session.commit()

        first = export_book(
            session,
            root=tmp_path / "artifacts",
            project_id=project_id,
            revision_id=revision_id,
            language="en",
            profile="fiction",
        )
        second = export_book(
            session,
            root=tmp_path / "artifacts",
            project_id=project_id,
            revision_id=revision_id,
            language="en",
            profile="fiction",
        )
        assert first.package_state == "structurally_validated"
        assert {artifact.filename for artifact in first.artifacts} == set(PACKAGE_FILES)
        assert {
            artifact.filename: artifact.artifact_id for artifact in first.artifacts
        } == {
            artifact.filename: artifact.artifact_id for artifact in second.artifacts
        }
        assert len(session.scalars(select(Artifact)).all()) == len(PACKAGE_FILES)

    root = tmp_path / "artifacts" / f"exports/{revision_id}"
    assert (root / "book.md").read_text().startswith("# The Morning Book")
    assert (root / "book.pdf").read_bytes().startswith(b"%PDF-")
    with zipfile.ZipFile(root / "book.epub") as epub_file:
        assert any(name.endswith("nav.xhtml") for name in epub_file.namelist())
    with Image.open(io.BytesIO((root / "cover.jpg").read_bytes())) as cover:
        assert cover.mode == "RGB"
        assert cover.size == (1600, 2560)


def test_review_artifacts_are_project_scoped_and_resolvable(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'reviews.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_ids = [uuid4(), uuid4()]
    with Session(engine) as session:
        projects = [Project(id=project_id, title=f"Review {index}", profile="fiction", language="en") for index, project_id in enumerate(project_ids)]
        sections = [Section(project_id=project_id, order_no=1, heading="Opening") for project_id in project_ids]
        session.add_all([*projects, *sections])
        session.flush()
        revisions = [
            SectionRevision(
                section_id=section.id,
                revision=1,
                content=f"Draft {index}",
                content_hash=str(index) * 64,
            )
            for index, section in enumerate(sections)
        ]
        session.add_all(revisions)
        session.flush()
        artifact = Artifact(
            revision_id=revisions[0].id,
            relative_path="review-artifact/book.md",
            mime_type="text/markdown",
            byte_count=5,
            sha256="a" * 64,
        )
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id
        resolution_revision_id = revisions[0].id

    with TestClient(create_app(Settings(database_url=database_url, owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
        rejected = client.post(
            f"/projects/{project_ids[1]}/reviews",
            json={"artifact_id": str(artifact_id), "severity": "medium", "criterion": "scope", "evidence": "wrong project"},
        )
        accepted = client.post(
            f"/projects/{project_ids[0]}/reviews",
            json={"artifact_id": str(artifact_id), "severity": "medium", "criterion": "scope", "evidence": "same project"},
        )
        findings = client.get(f"/projects/{project_ids[0]}/reviews")
        finding_id = accepted.json()["finding_id"]
        resolved = client.post(
            f"/projects/{project_ids[0]}/reviews/{finding_id}/resolve",
            json={"resolution_revision_id": str(resolution_revision_id)},
        )

    assert rejected.status_code == 404
    assert accepted.status_code == 201
    assert findings.status_code == 200
    assert len(findings.json()) == 1
    assert resolved.status_code == 200


def test_project_artifacts_includes_production_run_outputs(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'production-artifacts.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_id, brief_id, run_id = uuid4(), uuid4(), uuid4()
    artifact_root = tmp_path / "artifacts"
    artifact_root.joinpath(str(run_id)).mkdir(parents=True)
    content = b"\x89PNG\r\n\x1a\n"
    artifact_root.joinpath(str(run_id), "cover.png").write_bytes(content)
    with Session(engine) as session:
        session.add(Project(id=project_id, title="Production Artifacts", profile="fiction", language="en"))
        session.add(BriefRevision(id=brief_id, project_id=project_id, revision=1, structured_brief={}, content_hash="b" * 64))
        session.add(ProductionRun(id=run_id, project_id=project_id, approved_brief_id=brief_id))
        session.add(Artifact(run_id=run_id, relative_path=f"{run_id}/cover.png", mime_type="image/png", byte_count=8, sha256=hashlib.sha256(content).hexdigest()))
        session.commit()

    with TestClient(create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=artifact_root)), headers={"Authorization": "Bearer owner"}) as client:
        response = client.get(f"/projects/{project_id}/artifacts")
        download = client.get(response.json()[0]["download_path"])

    assert response.status_code == 200
    assert response.json()[0]["relative_path"] == f"{run_id}/cover.png"
    assert download.status_code == 200
    assert download.content == content
