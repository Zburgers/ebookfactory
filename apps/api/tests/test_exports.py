import io
import hashlib
import json
import zipfile
from pathlib import Path
from uuid import uuid4

from PIL import Image
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.exports import MAX_MARKETING_COVER_BYTES, PACKAGE_FILES, _make_epub, _make_pdf, export_book
from app.main import create_app
from app.models import (
    Artifact,
    Attempt,
    Base,
    BriefRevision,
    Event,
    ProductionRun,
    Project,
    ReviewFinding,
    Section,
    SectionRevision,
    Task,
    UsageCall,
    utc_now,
)
from app.settings import Settings


def test_epub_navigation_lists_manuscript_headings(tmp_path: Path) -> None:
    cover = io.BytesIO()
    Image.new("RGB", (1600, 2560), "#273b3a").save(cover, format="JPEG")

    package = _make_epub(
        "A Small Book",
        "en",
        "## First chapter\n\nFirst body.\n\n## Second chapter\n\nSecond body.",
        cover.getvalue(),
        uuid4(),
    )

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        navigation = archive.read("EPUB/nav.xhtml").decode()

    assert "chapter-1.xhtml#section-1" in navigation
    assert "First chapter" in navigation
    assert "chapter-1.xhtml#section-2" in navigation
    assert "Second chapter" in navigation


def test_pdf_embeds_package_identity() -> None:
    pdf = _make_pdf("QA Title", "## Chapter\n\nBody")

    assert b"/Title (QA Title)" in pdf
    assert b"/Author (Ebook Factory)" in pdf


def test_cover_size_gate_matches_current_kdp_ceiling() -> None:
    assert MAX_MARKETING_COVER_BYTES == 50 * 1024 * 1024


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

        with pytest.raises(ValueError, match="art artifact"):
            export_book(
                session,
                root=tmp_path / "artifacts",
                project_id=project_id,
                revision_id=revision_id,
                language="en",
                profile="fiction",
                art_artifact_id=uuid4(),
            )

        epub_path = tmp_path / "artifacts" / f"exports/{revision_id}/book.epub"
        original_epub = epub_path.read_bytes()
        epub_path.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="export artifact integrity"):
            export_book(
                session,
                root=tmp_path / "artifacts",
                project_id=project_id,
                revision_id=revision_id,
                language="en",
                profile="fiction",
            )
        epub_path.write_bytes(original_epub)

        markdown_artifact = session.scalar(
            select(Artifact).where(Artifact.relative_path == f"exports/{revision_id}/book.md")
        )
        assert markdown_artifact is not None
        nested_path = tmp_path / "artifacts" / f"exports/{revision_id}/nested/book.md"
        nested_path.parent.mkdir(parents=True)
        nested_path.write_bytes((tmp_path / "artifacts" / markdown_artifact.relative_path).read_bytes())
        markdown_artifact.relative_path = f"exports/{revision_id}/nested/book.md"
        session.commit()
        with pytest.raises(ValueError, match="canonical export"):
            export_book(
                session,
                root=tmp_path / "artifacts",
                project_id=project_id,
                revision_id=revision_id,
                language="en",
                profile="fiction",
            )

    root = tmp_path / "artifacts" / f"exports/{revision_id}"
    assert (root / "book.md").read_text().startswith("# The Morning Book")
    assert (root / "book.pdf").read_bytes().startswith(b"%PDF-")
    with zipfile.ZipFile(root / "book.epub") as epub_file:
        assert any(name.endswith("nav.xhtml") for name in epub_file.namelist())
    with Image.open(io.BytesIO((root / "cover.jpg").read_bytes())) as cover:
        assert cover.mode == "RGB"
        assert cover.size == (1600, 2560)
        assert cover.info["dpi"] == (300, 300)
    validation = json.loads((root / "validation.json").read_text())
    assert validation["checks"]["cover_file_size"] is True
    assert validation["checks"]["pdf_metadata"] is True
    assert validation["checks"]["epub_toc_headings"] is True
    fallback_metadata = json.loads((root / "metadata.json").read_text())
    assert fallback_metadata["ai_content_provenance"]["text"] == {
        "source": "revisioned-manuscript",
        "revision_id": str(revision_id),
        "owner_review_required": True,
    }
    assert fallback_metadata["ai_content_provenance"]["image"]["source_artifact_id"] is None
    assert fallback_metadata["ai_content_provenance"]["image"]["source_sha256"] is None
    assert fallback_metadata["ai_content_provenance"]["image"]["layout"] == "deterministic-local-cover-1600x2560-title-overlay"
    assert fallback_metadata["ai_content_provenance"]["image"]["source"] == "deterministic-fallback"
    assert fallback_metadata["ai_content_provenance"]["image"]["final_cover_filename"] == "cover.jpg"
    assert fallback_metadata["ai_content_provenance"]["image"]["final_cover_sha256"] == hashlib.sha256(
        (root / "cover.jpg").read_bytes()
    ).hexdigest()


def test_export_scope_includes_all_production_section_revisions(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'multi-section-export.db'}")
    Base.metadata.create_all(engine)
    project_id = uuid4()
    run_id = uuid4()
    root = tmp_path / "artifacts"
    production_path = root / str(run_id) / "book.md"
    production_path.parent.mkdir(parents=True)
    production_content = b"assembled production manuscript"
    production_path.write_bytes(production_content)

    with Session(engine) as session:
        project = Project(id=project_id, title="Scope Book", profile="fiction", language="en")
        brief = BriefRevision(
            id=uuid4(), project_id=project_id, revision=1, structured_brief={}, content_hash="a" * 64
        )
        run = ProductionRun(id=run_id, project_id=project_id, approved_brief_id=brief.id)
        session.add_all([project, brief, run])
        session.flush()
        sections = [
            Section(project_id=project_id, order_no=index, heading=f"Chapter {index}")
            for index in range(1, 4)
        ]
        session.add_all(sections)
        session.flush()
        revisions = [
            SectionRevision(
                section_id=section.id,
                revision=1,
                content=f"Body for chapter {index}.",
                content_hash=str(index) * 64,
            )
            for index, section in enumerate(sections, start=1)
        ]
        session.add_all(revisions)
        session.flush()
        section_tasks = [
            Task(
                run_id=run_id,
                task_type="section-draft",
                status="succeeded",
                result_refs={"section_id": str(section.id), "revision_id": str(revision.id)},
            )
            for section, revision in zip(sections, revisions)
        ]
        session.add_all(section_tasks)
        session.flush()
        session.add(
            Task(
                run_id=run_id,
                task_type="production",
                status="succeeded",
                dependencies=[str(task.id) for task in section_tasks],
                result_refs={"revision_id": str(revisions[0].id)},
            )
        )
        session.add(
            Artifact(
                run_id=run_id,
                revision_id=revisions[0].id,
                relative_path=f"{run_id}/book.md",
                mime_type="text/markdown",
                byte_count=len(production_content),
                sha256=hashlib.sha256(production_content).hexdigest(),
            )
        )
        revision_ids = [revision.id for revision in revisions]
        session.commit()
        result = export_book(
            session,
            root=root,
            project_id=project_id,
            revision_id=revisions[0].id,
            language="en",
            profile="fiction",
        )

    export_root = root / f"exports/{revision_ids[0]}"
    markdown = (export_root / "book.md").read_text()
    metadata = json.loads((export_root / "metadata.json").read_text())
    assert result.package_state == "structurally_validated"
    assert all(f"## Chapter {index}" in markdown for index in range(1, 4))
    assert all(f"Body for chapter {index}." in markdown for index in range(1, 4))
    assert metadata["source_revision_ids"] == [str(revision_id) for revision_id in revision_ids]


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
    with Session(engine) as session:
        event_kinds = session.scalars(
            select(Event.kind).where(Event.project_id == project_ids[0]).order_by(Event.id)
        ).all()
    assert "review.finding.created" in event_kinds
    assert "review.finding.resolved" in event_kinds


def test_review_findings_reject_inconsistent_artifact_relationships(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'review-scope.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_a_id, project_b_id = uuid4(), uuid4()
    with Session(engine) as session:
        project_a = Project(id=project_a_id, title="A", profile="fiction", language="en")
        project_b = Project(id=project_b_id, title="B", profile="fiction", language="en")
        section_a = Section(project_id=project_a_id, order_no=1, heading="A")
        section_b = Section(project_id=project_b_id, order_no=1, heading="B")
        brief_a = BriefRevision(id=uuid4(), project_id=project_a_id, revision=1, structured_brief={}, content_hash="d" * 64)
        session.add_all([project_a, project_b, section_a, section_b, brief_a])
        session.flush()
        revision_a = SectionRevision(section_id=section_a.id, revision=1, content="# A", content_hash="a" * 64)
        revision_b = SectionRevision(section_id=section_b.id, revision=1, content="# B", content_hash="b" * 64)
        run_a = ProductionRun(project_id=project_a_id, approved_brief_id=brief_a.id)
        session.add_all([revision_a, revision_b, run_a])
        session.flush()
        artifact = Artifact(run_id=run_a.id, revision_id=revision_b.id, relative_path="leaked.md", mime_type="text/markdown", byte_count=1, sha256="c" * 64)
        session.add(artifact)
        session.flush()
        finding = ReviewFinding(artifact_id=artifact.id, severity="high", criterion="scope", evidence="inconsistent")
        session.add(finding)
        session.commit()
        finding_id = finding.id
        artifact_id = artifact.id
        revision_a_id = revision_a.id

    with TestClient(create_app(Settings(database_url=database_url, owner_token="owner")), headers={"Authorization": "Bearer owner"}) as client:
        listed_a = client.get(f"/projects/{project_a_id}/reviews")
        listed_b = client.get(f"/projects/{project_b_id}/reviews")
        created_a = client.post(f"/projects/{project_a_id}/reviews", json={"artifact_id": str(artifact_id), "severity": "high", "criterion": "scope", "evidence": "wrong"})
        created_b = client.post(f"/projects/{project_b_id}/reviews", json={"artifact_id": str(artifact_id), "severity": "high", "criterion": "scope", "evidence": "wrong"})
        resolved_a = client.post(f"/projects/{project_a_id}/reviews/{finding_id}/resolve", json={"resolution_revision_id": str(revision_a_id)})
        resolved_b = client.post(f"/projects/{project_b_id}/reviews/{finding_id}/resolve", json={"resolution_revision_id": str(revision_a_id)})

    assert listed_a.status_code == listed_b.status_code == 200
    assert listed_a.json() == listed_b.json() == []
    assert created_a.status_code == created_b.status_code == 404
    assert resolved_a.status_code == resolved_b.status_code == 404


def test_export_uses_persisted_codex_art_and_records_layout_provenance(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'art-export.db'}")
    Base.metadata.create_all(engine)
    project_id, revision_id = uuid4(), uuid4()
    source_root = tmp_path / "artifacts"
    source_relative_path = f"{uuid4()}/generated.png"
    source_path = source_root / source_relative_path
    source_path.parent.mkdir(parents=True)
    source_bytes = io.BytesIO()
    Image.new("RGB", (900, 1400), "#ad3d65").save(source_bytes, format="PNG")
    source_content = source_bytes.getvalue()
    source_path.write_bytes(source_content)
    second_relative_path = f"{uuid4()}/alternate.png"
    second_path = source_root / second_relative_path
    second_path.parent.mkdir(parents=True)
    second_bytes = io.BytesIO()
    Image.new("RGB", (1000, 1000), "#2c78ad").save(second_bytes, format="PNG")
    second_content = second_bytes.getvalue()
    second_path.write_bytes(second_content)

    with Session(engine) as session:
        project = Project(id=project_id, title="Art Export Fixture", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        session.add_all([project, section])
        session.flush()
        brief = BriefRevision(id=uuid4(), project_id=project_id, revision=1, structured_brief={}, content_hash="b" * 64)
        run_id, task_id = uuid4(), uuid4()
        selected_attempt_id, other_attempt_id = uuid4(), uuid4()
        run = ProductionRun(id=run_id, project_id=project_id, approved_brief_id=brief.id)
        task = Task(id=task_id, run_id=run_id, task_type="production", input_revision_ids=[str(revision_id)])
        selected_attempt = Attempt(
            id=selected_attempt_id, task_id=task_id, attempt_no=1, input_revision_ids=[str(revision_id)], status="succeeded"
        )
        other_attempt = Attempt(
            id=other_attempt_id, task_id=task_id, attempt_no=2, input_revision_ids=[str(revision_id)], status="succeeded"
        )
        selected_usage_id = uuid4()
        revision = SectionRevision(
            id=revision_id,
            section_id=section.id,
            revision=1,
            content="# The Art Book\n\n## Chapter One\n\nA story with a cover.",
            summary="fixture",
            source_refs=[],
            knowledge_refs=[],
            approval_status="draft",
            content_hash="c" * 64,
        )
        source_artifact = Artifact(
            revision_id=revision_id,
            relative_path=source_relative_path,
            mime_type="image/png",
            byte_count=len(source_content),
            sha256=hashlib.sha256(source_content).hexdigest(),
            validation_state="generated",
        )
        second_artifact = Artifact(
            run_id=run_id,
            attempt_id=selected_attempt_id,
            usage_call_id=selected_usage_id,
            revision_id=revision_id,
            relative_path=second_relative_path,
            mime_type="image/png",
            byte_count=len(second_content),
            sha256=hashlib.sha256(second_content).hexdigest(),
            validation_state="generated",
        )
        session.add_all([
            brief,
            run,
            task,
            selected_attempt,
            other_attempt,
            revision,
            source_artifact,
            second_artifact,
            UsageCall(
                id=uuid4(),
                run_id=run_id,
                attempt_id=other_attempt_id,
                purpose="art",
                provider="wrong-provider",
                model="wrong-model",
                started_at=utc_now(),
                ended_at=utc_now(),
                outcome="succeeded",
                normalization_version="v1",
            ),
            UsageCall(
                id=selected_usage_id,
                run_id=run_id,
                attempt_id=selected_attempt_id,
                purpose="art",
                provider="selected-provider",
                model="selected-model",
                started_at=utc_now(),
                ended_at=utc_now(),
                outcome="succeeded",
                normalization_version="v1",
            ),
            UsageCall(
                id=uuid4(),
                run_id=run_id,
                attempt_id=selected_attempt_id,
                purpose="art",
                provider="later-wrong-provider",
                model="later-wrong-model",
                started_at=utc_now(),
                ended_at=utc_now(),
                outcome="succeeded",
                normalization_version="v1",
            ),
        ])
        session.commit()
        second_artifact_id = second_artifact.id

        result = export_book(
            session,
            root=source_root,
            project_id=project_id,
            revision_id=revision_id,
            language="en",
            profile="fiction",
            art_artifact_id=second_artifact_id,
        )
        with pytest.raises(ValueError, match="immutable export art selection"):
            export_book(
                session,
                root=source_root,
                project_id=project_id,
                revision_id=revision_id,
                language="en",
                profile="fiction",
                art_artifact_id=source_artifact.id,
            )
        second_artifact.owner_review_state = "revision_requested"
        with pytest.raises(ValueError, match="requires owner revision"):
            export_book(
                session,
                root=source_root,
                project_id=project_id,
                revision_id=revision_id,
                language="en",
                profile="fiction",
            )
        session.commit()

    metadata = json.loads((source_root / f"exports/{revision_id}/metadata.json").read_text())
    provenance = metadata["ai_content_provenance"]["image"]
    assert result.package_state == "structurally_validated"
    assert provenance["source_artifact_id"] == str(second_artifact_id)
    assert provenance["source_sha256"] == hashlib.sha256(second_content).hexdigest()
    assert provenance["source_mime_type"] == "image/png"
    assert provenance["source_dimensions"] == [1000, 1000]
    assert provenance["layout"] == "fit-1600x2560-title-overlay"
    assert provenance["final_cover_filename"] == "cover.jpg"
    assert provenance["final_cover_sha256"] == hashlib.sha256(
        (source_root / f"exports/{revision_id}/cover.jpg").read_bytes()
    ).hexdigest()
    assert provenance["source_generation"] == {
        "call_id": str(selected_usage_id),
        "provider": "selected-provider",
        "model": "selected-model",
        "provider_request_id": None,
        "input_tokens": None,
        "output_tokens": None,
    }
    assert (source_root / source_relative_path).read_bytes() == source_content
    assert (source_root / second_relative_path).read_bytes() == second_content
    with Image.open(io.BytesIO((source_root / f"exports/{revision_id}/cover.jpg").read_bytes())) as cover:
        assert cover.getpixel((0, 0))[0] < 100
        assert cover.getpixel((0, 0))[1] > 80
        assert cover.getpixel((0, 0))[2] > 120

    with TestClient(
        create_app(Settings(database_url=f"sqlite:///{tmp_path / 'art-export.db'}", owner_token="owner", artifact_root=source_root)),
        headers={"Authorization": "Bearer owner"},
    ) as client:
        cover_download = client.get(f"/projects/{project_id}/exports/{revision_id}/cover.jpg")
        metadata_download = client.get(f"/projects/{project_id}/exports/{revision_id}/metadata.json")
    assert cover_download.status_code == 409
    assert metadata_download.status_code == 409


def test_export_fails_closed_for_corrupt_persisted_image(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'corrupt-art.db'}")
    Base.metadata.create_all(engine)
    project_id, revision_id = uuid4(), uuid4()
    root = tmp_path / "artifacts"
    relative_path = f"{uuid4()}/generated.png"
    path = root / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not-the-recorded-image")

    with Session(engine) as session:
        project = Project(id=project_id, title="Corrupt Art", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        revision = SectionRevision(
            id=revision_id,
            section_id=section.id,
            revision=1,
            content="# Corrupt Art\n\nA story.",
            content_hash="d" * 64,
        )
        session.add_all([project, section])
        session.flush()
        revision.section_id = section.id
        session.add(revision)
        session.add(
            Artifact(
                revision_id=revision_id,
                relative_path=relative_path,
                mime_type="image/png",
                byte_count=10,
                sha256=hashlib.sha256(b"recorded-image").hexdigest(),
            )
        )
        session.commit()

        try:
            export_book(session, root=root, project_id=project_id, revision_id=revision_id, language="en", profile="fiction")
        except ValueError as exc:
            assert "immutable hash verification" in str(exc)
        else:
            raise AssertionError("corrupt persisted art must block export")


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
    artifact_root.joinpath(str(run_id), "cover.png").write_bytes(b"tampered!")
    tampered = client.get(response.json()[0]["download_path"])
    assert tampered.status_code == 409


def test_export_api_enforces_art_selection_and_member_integrity(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'export-api.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_id, revision_id = uuid4(), uuid4()
    root = tmp_path / "artifacts"
    source_relative_path = f"{uuid4()}/generated.png"
    source_path = root / source_relative_path
    source_path.parent.mkdir(parents=True)
    source_bytes = io.BytesIO()
    Image.new("RGB", (500, 700), "#8b4d2e").save(source_bytes, format="PNG")
    source_content = source_bytes.getvalue()
    source_path.write_bytes(source_content)

    with Session(engine) as session:
        project = Project(id=project_id, title="API Export", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        session.add_all([project, section])
        session.flush()
        revision = SectionRevision(
            id=revision_id,
            section_id=section.id,
            revision=1,
            content="# API Export\n\nA durable export.",
            content_hash="e" * 64,
        )
        source_artifact = Artifact(
            revision_id=revision_id,
            relative_path=source_relative_path,
            mime_type="image/png",
            byte_count=len(source_content),
            sha256=hashlib.sha256(source_content).hexdigest(),
        )
        session.add_all([revision, source_artifact])
        session.commit()
        source_artifact_id = source_artifact.id

    with TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=root)),
        headers={"Authorization": "Bearer owner"},
    ) as client:
        created = client.post(
            f"/projects/{project_id}/exports/{revision_id}",
            json={"art_artifact_id": str(source_artifact_id)},
        )
        assert created.status_code == 200
        assert len(created.json()["artifacts"]) == len(PACKAGE_FILES)
        rejected = client.post(
            f"/projects/{project_id}/exports/{revision_id}",
            json={"art_artifact_id": str(uuid4())},
        )
        assert rejected.status_code == 409
        download_path = f"/projects/{project_id}/exports/{revision_id}/book.md"
        downloaded = client.get(download_path)
        assert downloaded.status_code == 200
        (root / f"exports/{revision_id}/book.md").write_bytes(b"tampered")
        tampered = client.get(download_path)
        assert tampered.status_code == 409


def test_existing_legacy_placeholder_provenance_fails_closed(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-export.db'}")
    Base.metadata.create_all(engine)
    project_id, revision_id = uuid4(), uuid4()
    root = tmp_path / "artifacts"
    with Session(engine) as session:
        project = Project(id=project_id, title="Legacy Export", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        session.add_all([project, section])
        session.flush()
        session.add(
            SectionRevision(
                id=revision_id,
                section_id=section.id,
                revision=1,
                content="# Legacy Export\n\nA story.",
                content_hash="f" * 64,
            )
        )
        session.commit()
        export_book(session, root=root, project_id=project_id, revision_id=revision_id, language="en", profile="fiction")
        metadata_artifact = session.scalar(
            select(Artifact).where(Artifact.relative_path == f"exports/{revision_id}/metadata.json")
        )
        assert metadata_artifact is not None
        legacy_content = json.dumps(
            {
                "revision_id": str(revision_id),
                "ai_content_provenance": {
                    "text": "Pi provider output",
                    "image": "deterministic local cover; Codex image route pending",
                },
            }
        ).encode()
        metadata_path = root / metadata_artifact.relative_path
        metadata_path.write_bytes(legacy_content)
        metadata_artifact.byte_count = len(legacy_content)
        metadata_artifact.sha256 = hashlib.sha256(legacy_content).hexdigest()
        session.commit()
        with pytest.raises(ValueError, match="legacy export provenance"):
            export_book(session, root=root, project_id=project_id, revision_id=revision_id, language="en", profile="fiction")
        with TestClient(
            create_app(Settings(database_url=f"sqlite:///{tmp_path / 'legacy-export.db'}", owner_token="owner", artifact_root=root)),
            headers={"Authorization": "Bearer owner"},
        ) as client:
            response = client.get(f"/projects/{project_id}/exports/{revision_id}/metadata.json")
        assert response.status_code == 409


def test_artifact_owner_review_is_project_scoped_and_durable(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'artifact-review.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_id, revision_id = uuid4(), uuid4()
    root = tmp_path / "artifacts"
    image_path = root / f"{uuid4()}/cover.png"
    image_path.parent.mkdir(parents=True)
    image_content = b"\x89PNG\r\n\x1a\nowner-review"
    image_path.write_bytes(image_content)
    with Session(engine) as session:
        project = Project(id=project_id, title="Art Review", profile="fiction", language="en")
        section = Section(project_id=project_id, order_no=1, heading="Opening")
        session.add_all([project, section])
        session.flush()
        session.add(
            SectionRevision(
                id=revision_id,
                section_id=section.id,
                revision=1,
                content="# Art Review\n\nA story.",
                content_hash="a" * 64,
            )
        )
        artifact = Artifact(
            revision_id=revision_id,
            relative_path=str(image_path.relative_to(root)),
            mime_type="image/png",
            byte_count=len(image_content),
            sha256=hashlib.sha256(image_content).hexdigest(),
        )
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id

    with TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=root)),
        headers={"Authorization": "Bearer owner"},
    ) as client:
        approved = client.post(
            f"/projects/{project_id}/artifacts/{artifact_id}/review",
            json={"decision": "approve", "note": "Cover composition is readable.", "expected_owner_review_state": "pending"},
        )
        listed = client.get(f"/projects/{project_id}/artifacts")
        listed_after_approval = client.get(f"/projects/{project_id}/artifacts")
        revision_requested = client.post(
            f"/projects/{project_id}/artifacts/{artifact_id}/review",
            json={"decision": "request_revision", "note": "Increase title contrast.", "expected_owner_review_state": "approved"},
        )
        stale_decision = client.post(
            f"/projects/{project_id}/artifacts/{artifact_id}/review",
            json={"decision": "approve", "note": "Stale approval.", "expected_owner_review_state": "pending"},
        )

    assert approved.status_code == 200
    assert approved.json()["owner_review_state"] == "approved"
    assert approved.json()["owner_review_note"] == "Cover composition is readable."
    assert listed.status_code == 200
    assert listed.json()[0]["owner_review_state"] == "approved"
    assert listed_after_approval.status_code == 200
    assert listed_after_approval.json()[0]["owner_review_state"] == "approved"
    assert revision_requested.status_code == 200
    assert revision_requested.json()["owner_review_state"] == "revision_requested"
    assert stale_decision.status_code == 409

    with Session(engine) as session:
        artifact = session.get(Artifact, artifact_id)
        assert artifact is not None
        export_cover = Artifact(
            revision_id=revision_id,
            relative_path=f"exports/{revision_id}/cover.jpg",
            mime_type="image/jpeg",
            byte_count=1,
            sha256="b" * 64,
        )
        session.add(export_cover)
        session.commit()
        export_cover_id = export_cover.id
    with TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=root)),
        headers={"Authorization": "Bearer owner"},
    ) as client:
        derived_review = client.post(
            f"/projects/{project_id}/artifacts/{export_cover_id}/review",
            json={"decision": "approve", "expected_owner_review_state": "pending"},
        )
        wrong_project = client.post(
            f"/projects/{uuid4()}/artifacts/{artifact_id}/review",
            json={"decision": "approve", "expected_owner_review_state": "revision_requested"},
        )
    assert derived_review.status_code == 422
    assert wrong_project.status_code == 404


def test_inconsistent_artifact_relationships_are_not_exposed_across_projects(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'artifact-scope.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    project_a_id, project_b_id = uuid4(), uuid4()
    brief_a_id, brief_b_id = uuid4(), uuid4()
    revision_a_id, revision_b_id = uuid4(), uuid4()
    root = tmp_path / "artifacts"
    artifact_path = root / "leaked.txt"
    artifact_path.parent.mkdir(parents=True)
    artifact_content = b"must not cross project boundaries"
    artifact_path.write_bytes(artifact_content)

    with Session(engine) as session:
        project_a = Project(id=project_a_id, title="Project A", profile="fiction", language="en")
        project_b = Project(id=project_b_id, title="Project B", profile="fiction", language="en")
        brief_a = BriefRevision(
            id=brief_a_id,
            project_id=project_a_id,
            revision=1,
            structured_brief={"promise": "A"},
            content_hash="a" * 64,
        )
        brief_b = BriefRevision(
            id=brief_b_id,
            project_id=project_b_id,
            revision=1,
            structured_brief={"promise": "B"},
            content_hash="b" * 64,
        )
        section_a = Section(project_id=project_a_id, order_no=1, heading="A")
        section_b = Section(project_id=project_b_id, order_no=1, heading="B")
        session.add_all([project_a, project_b, brief_a, brief_b, section_a, section_b])
        session.flush()
        revision_a = SectionRevision(
            id=revision_a_id,
            section_id=section_a.id,
            revision=1,
            content="# A",
            content_hash="c" * 64,
        )
        revision_b = SectionRevision(
            id=revision_b_id,
            section_id=section_b.id,
            revision=1,
            content="# B",
            content_hash="d" * 64,
        )
        run_a = ProductionRun(id=uuid4(), project_id=project_a_id, approved_brief_id=brief_a_id)
        run_b = ProductionRun(id=uuid4(), project_id=project_b_id, approved_brief_id=brief_b_id)
        session.add_all([revision_a, revision_b, run_a, run_b])
        session.flush()
        leaked_artifact = Artifact(
            run_id=run_a.id,
            revision_id=revision_b_id,
            relative_path=str(artifact_path.relative_to(root)),
            mime_type="text/plain",
            byte_count=len(artifact_content),
            sha256=hashlib.sha256(artifact_content).hexdigest(),
        )
        session.add(leaked_artifact)
        session.commit()
        artifact_id = leaked_artifact.id

    with TestClient(
        create_app(Settings(database_url=database_url, owner_token="owner", artifact_root=root)),
        headers={"Authorization": "Bearer owner"},
    ) as client:
        list_a = client.get(f"/projects/{project_a_id}/artifacts")
        list_b = client.get(f"/projects/{project_b_id}/artifacts")
        download_a = client.get(f"/projects/{project_a_id}/artifacts/{artifact_id}/download")
        download_b = client.get(f"/projects/{project_b_id}/artifacts/{artifact_id}/download")

    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert list_a.json() == []
    assert list_b.json() == []
    assert download_a.status_code == 404
    assert download_b.status_code == 404
