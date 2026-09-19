"""Deterministic publishing package generation from one frozen revision."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from docx import Document
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts import safe_artifact_path, write_artifact
from app.models import Artifact, Project, Section, SectionRevision, Task, UsageCall


PACKAGE_FILES = (
    "book.epub",
    "book.pdf",
    "book.docx",
    "book.md",
    "cover.jpg",
    "metadata.json",
    "metadata.csv",
    "sources.json",
    "manifest.json",
    "validation.json",
)

MIME_TYPES = {
    "md": "text/markdown",
    "jpg": "image/jpeg",
    "epub": "application/epub+zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "json": "application/json",
    "csv": "text/csv",
}
MAX_MARKETING_COVER_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ExportArtifact:
    """A generated immutable package member."""

    artifact_id: UUID
    filename: str
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class ExportResult:
    """The idempotent package result returned to API callers."""

    revision_id: UUID
    title: str
    package_state: str
    artifacts: tuple[ExportArtifact, ...]


@dataclass(frozen=True)
class ManuscriptScope:
    """The frozen section revisions that make up one export package."""

    title: str
    body: str
    revision_ids: tuple[UUID, ...]


def _title_and_body(content: str, fallback: str) -> tuple[str, str]:
    match = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
    title = match.group(1).strip() if match else fallback.strip() or "Untitled manuscript"
    body = content.strip()
    if match and match.start() == 0:
        body = content[match.end() :].strip()
    return title, body


def _section_body(content: str) -> str:
    """Strip an accidental document title before nesting a section in a book."""

    return _title_and_body(content, "")[1]


def _revision_is_descendant(session: Session, *, candidate: SectionRevision, ancestor_id: UUID) -> bool:
    """Follow immutable parent links without allowing a malformed cycle to loop forever."""

    seen: set[UUID] = set()
    current: SectionRevision | None = candidate
    while current is not None and current.id not in seen:
        if current.id == ancestor_id:
            return True
        seen.add(current.id)
        current = session.get(SectionRevision, current.parent_revision_id) if current.parent_revision_id else None
    return False


def _production_scope_entries(
    session: Session,
    *,
    project_id: UUID,
    production_task: Task,
) -> list[tuple[Section, SectionRevision]]:
    """Resolve one production task's dependency-fenced section revisions."""

    entries: list[tuple[Section, SectionRevision]] = []
    for dependency_value in production_task.dependencies or []:
        try:
            dependency_id = UUID(dependency_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("production manuscript scope contains an invalid dependency") from exc
        section_task = session.get(Task, dependency_id)
        if (
            section_task is None
            or section_task.run_id != production_task.run_id
            or section_task.task_type != "section-draft"
            or section_task.status != "succeeded"
        ):
            raise ValueError("production manuscript scope is incomplete")
        section_id = section_task.result_refs.get("section_id")
        revision_id = section_task.result_refs.get("revision_id")
        section = session.get(Section, UUID(section_id)) if section_id else None
        section_revision = session.get(SectionRevision, UUID(revision_id)) if revision_id else None
        if (
            section is None
            or section.project_id != project_id
            or section_revision is None
            or section_revision.section_id != section.id
        ):
            raise ValueError("production manuscript scope is outside the project")
        if not any(existing_section.id == section.id for existing_section, _ in entries):
            entries.append((section, section_revision))
    return sorted(entries, key=lambda item: item[0].order_no)


def _production_scope_for_revision(
    session: Session,
    *,
    project_id: UUID,
    revision: SectionRevision,
) -> list[tuple[Section, SectionRevision]] | None:
    """Find the completed production run that owns an anchor or owner revision."""

    production_artifacts = session.execute(
        select(Artifact, Task)
        .join(Task, Task.run_id == Artifact.run_id)
        .join(SectionRevision, SectionRevision.id == Artifact.revision_id)
        .join(Section, Section.id == SectionRevision.section_id)
        .where(
            Artifact.run_id.is_not(None),
            Artifact.mime_type == "text/markdown",
            Artifact.relative_path.like("%/book.md"),
            Section.project_id == project_id,
            Task.task_type == "production",
        )
    ).all()
    for _, production_task in production_artifacts:
        entries = _production_scope_entries(
            session, project_id=project_id, production_task=production_task
        )
        if not entries:
            continue
        for index, (section, section_revision) in enumerate(entries):
            if section.id == revision.section_id and _revision_is_descendant(
                session, candidate=revision, ancestor_id=section_revision.id
            ):
                entries[index] = (section, revision)
                return entries
    return None


def _resolve_manuscript_scope(
    session: Session,
    *,
    project_id: UUID,
    revision_id: UUID,
) -> ManuscriptScope:
    """Resolve one revision into a complete production manuscript when possible."""

    row = session.execute(
        select(Project, SectionRevision)
        .join(Section, Section.project_id == Project.id)
        .join(SectionRevision, SectionRevision.section_id == Section.id)
        .where(Project.id == project_id, SectionRevision.id == revision_id)
    ).first()
    if row is None:
        raise ValueError("revision does not belong to project")
    project, revision = row
    production_scope = _production_scope_for_revision(
        session, project_id=project_id, revision=revision
    )
    if production_scope is None:
        title, body = _title_and_body(revision.content, project.title)
        return ManuscriptScope(title=title, body=body, revision_ids=(revision.id,))
    entries = production_scope
    title, _ = _title_and_body(revision.content, project.title)
    body = "\n\n".join(
        f"## {section.heading}\n\n{_section_body(section_revision.content)}"
        for section, section_revision in entries
    )
    return ManuscriptScope(
        title=title,
        body=body,
        revision_ids=tuple(section_revision.id for _, section_revision in entries),
    )


def _markdown_blocks(content: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            if paragraph:
                blocks.append(("p", " ".join(paragraph)))
                paragraph = []
            blocks.append((f"h{len(heading.group(1))}", heading.group(2).strip()))
        elif line:
            paragraph.append(line)
        elif paragraph:
            blocks.append(("p", " ".join(paragraph)))
            paragraph = []
    if paragraph:
        blocks.append(("p", " ".join(paragraph)))
    return blocks


def _inline_html(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def _canonical_markdown(title: str, content: str) -> str:
    if re.match(r"^#\s+", content.strip()):
        return f"{content.strip()}\n"
    return f"# {title}\n\n{content.strip()}\n"


def _make_cover(title: str, source: bytes | None = None) -> bytes:
    if source is None:
        image = Image.new("RGB", (1600, 2560), "#273b3a")
    else:
        with Image.open(io.BytesIO(source)) as source_image:
            image = ImageOps.fit(source_image.convert("RGB"), (1600, 2560), method=Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    try:
        font = ImageFont.truetype(font_path, 112)
        small = ImageFont.truetype(font_path, 42)
    except OSError:
        font = ImageFont.load_default()
        small = font
    draw.rectangle((110, 110, 1490, 2450), outline="#dca38d", width=5)
    lines = textwrap.wrap(title, width=18) or ["Untitled manuscript"]
    y = 900 - (len(lines) - 1) * 70
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((1600 - (box[2] - box[0])) / 2, y), line, fill="#fffdf9", font=font)
        y += 150
    label = "EBOOK FACTORY · READING COPY"
    box = draw.textbbox((0, 0), label, font=small)
    draw.text(((1600 - (box[2] - box[0])) / 2, 2180), label, fill="#b8d1ca", font=small)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def _cover_source(
    session: Session,
    *,
    root: Path,
    revision_id: UUID,
    project_id: UUID,
    art_artifact_id: UUID | None = None,
) -> tuple[bytes | None, dict[str, object]]:
    """Resolve and verify the immutable image for this exact revision."""

    candidates = session.scalars(
        select(Artifact)
        .join(SectionRevision, SectionRevision.id == Artifact.revision_id)
        .join(Section, Section.id == SectionRevision.section_id)
        .where(
            Artifact.revision_id == revision_id,
            Section.project_id == project_id,
            Artifact.mime_type.like("image/%"),
            ~Artifact.relative_path.startswith("exports/"),
            Artifact.owner_review_state != "revision_requested",
        )
        .order_by(Artifact.created_at.desc(), Artifact.id.desc())
    ).all()
    if art_artifact_id is not None:
        candidates = [artifact for artifact in candidates if artifact.id == art_artifact_id]
        if not candidates:
            raise ValueError("requested art artifact is not an eligible image for this revision")
    for artifact in candidates:
        recorded_path = root / artifact.relative_path
        if recorded_path.is_symlink():
            raise ValueError("source image artifact path must not be a symlink")
        path = safe_artifact_path(root, artifact.relative_path)
        if not path.is_file():
            raise ValueError("source image artifact is missing")
        content = path.read_bytes()
        if len(content) != artifact.byte_count or hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise ValueError("source image artifact failed immutable hash verification")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                dimensions = list(image.size)
        except Exception as exc:
            raise ValueError("source image artifact is not a valid image") from exc
        provenance: dict[str, object] = {
            "source_artifact_id": str(artifact.id),
            "source_sha256": artifact.sha256,
            "source_mime_type": artifact.mime_type,
            "source_dimensions": dimensions,
            "layout": "fit-1600x2560-title-overlay",
        }
        usage = None
        if artifact.attempt_id is not None:
            usage = session.scalar(
                select(UsageCall)
                .where(
                    UsageCall.id == artifact.usage_call_id,
                    UsageCall.attempt_id == artifact.attempt_id,
                    UsageCall.purpose == "art",
                )
            )
        if usage is not None:
            provenance["source_generation"] = {
                "call_id": str(usage.id),
                "provider": usage.provider,
                "model": usage.model,
                "provider_request_id": usage.provider_request_id,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
        return content, provenance
    return None, {
        "source_artifact_id": None,
        "source_sha256": None,
        "layout": "deterministic-local-cover-1600x2560-title-overlay",
        "source": "deterministic-fallback",
    }


def _make_epub(title: str, language: str, markdown: str, cover: bytes, revision_id: UUID) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{revision_id}")
    book.set_title(title)
    book.set_language(language)
    book.add_author("Ebook Factory")
    book.add_metadata("DC", "description", "AI-assisted manuscript; owner review required.")
    book.set_cover("cover.jpg", cover)
    chapter = epub.EpubHtml(title=title, file_name="chapter-1.xhtml", lang=language)
    body = [f"<h1>{html.escape(title)}</h1>"]
    body.extend(f"<{kind}>{_inline_html(value)}</{kind}>" for kind, value in _markdown_blocks(markdown))
    chapter.content = (
        "<!DOCTYPE html><html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
        f"<title>{html.escape(title)}</title><style>body{{font-family:serif;line-height:1.5}}"
        "h1,h2{page-break-after:avoid}</style></head><body>"
        + "".join(body)
        + "</body></html>"
    )
    book.add_item(chapter)
    book.toc = (epub.Link("chapter-1.xhtml", title, "chapter-1"),)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    with tempfile.TemporaryDirectory(prefix="ebook-export-") as directory:
        path = Path(directory) / "book.epub"
        epub.write_epub(str(path), book)
        return path.read_bytes()


def _make_docx(title: str, markdown: str) -> bytes:
    document = Document()
    document.add_heading(title, 0)
    for kind, value in _markdown_blocks(markdown):
        if kind.startswith("h"):
            document.add_heading(value, level=min(int(kind[1:]), 3))
        else:
            document.add_paragraph(value)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _make_pdf(title: str, markdown: str) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("BookTitle", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=24)
    heading_style = ParagraphStyle("BookHeading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle("BookBody", parent=styles["BodyText"], leading=15, spaceAfter=9)
    story = [Paragraph(html.escape(title), title_style)]
    for kind, value in _markdown_blocks(markdown):
        if kind.startswith("h"):
            story.append(Paragraph(_inline_html(value), heading_style))
        else:
            story.append(Paragraph(_inline_html(value), body_style))
    document = SimpleDocTemplate(output, pagesize=LETTER, rightMargin=0.8 * inch, leftMargin=0.8 * inch)
    document.build(story)
    return output.getvalue()


def _metadata(
    title: str,
    language: str,
    profile: str,
    revision_id: UUID,
    source_revision_ids: tuple[UUID, ...],
    image_provenance: dict[str, object],
) -> dict[str, object]:
    return {
        "title": title,
        "subtitle": None,
        "author": "Ebook Factory",
        "language": language,
        "profile": profile,
        "description": "AI-assisted manuscript; owner review required.",
        "keywords": [],
        "categories": [],
        "revision_id": str(revision_id),
        "source_revision_ids": [str(source_revision_id) for source_revision_id in source_revision_ids],
        "ai_content_provenance": {
            "text": {
                "source": "revisioned-manuscript",
                "revision_id": str(revision_id),
                "owner_review_required": True,
            },
            "image": image_provenance,
        },
        "kindle_preview": "pending",
    }


def _metadata_csv(metadata: dict[str, object]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("field", "value"))
    for key, value in metadata.items():
        writer.writerow((key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value))
    return output.getvalue().encode()


def _validate_files(files: dict[str, bytes], *, source_revision_count: int) -> dict[str, object]:
    checks: dict[str, bool] = {}
    checks["markdown_nonempty"] = bool(files["book.md"].strip())
    checks["pdf_signature"] = files["book.pdf"].startswith(b"%PDF-")
    checks["docx_structure"] = all(marker in files["book.docx"] for marker in (b"word/document.xml", b"[Content_Types].xml"))
    with zipfile.ZipFile(io.BytesIO(files["book.epub"])) as archive:
        checks["epub_archive"] = archive.testzip() is None
        names = set(archive.namelist())
        checks["epub_navigation"] = any(name.endswith("nav.xhtml") for name in names) and any(
            name.endswith("chapter-1.xhtml") for name in names
        )
    with Image.open(io.BytesIO(files["cover.jpg"])) as cover:
        checks["cover_rgb"] = cover.mode == "RGB"
        checks["cover_dimensions"] = cover.size == (1600, 2560)
    checks["cover_file_size"] = len(files["cover.jpg"]) <= MAX_MARKETING_COVER_BYTES
    checks["manuscript_scope_complete"] = source_revision_count >= 1
    checks["all_structural_checks_pass"] = all(checks.values())
    return {"package_state": "structurally_validated" if checks["all_structural_checks_pass"] else "generated", "checks": checks, "kindle_preview": "pending"}


def verify_export_members(
    session: Session,
    *,
    root: Path,
    revision_id: UUID,
) -> list[Artifact]:
    """Verify every registered member before exposing an immutable export."""
    prefix = f"exports/{revision_id}/"
    expected_paths = {f"{prefix}{filename}" for filename in PACKAGE_FILES}
    members = session.scalars(select(Artifact).where(Artifact.relative_path.like(f"{prefix}%"))).all()
    if (
        len(members) != len(PACKAGE_FILES)
        or {item.relative_path for item in members} != expected_paths
        or any(item.revision_id != revision_id for item in members)
    ):
        raise ValueError("canonical export package paths or revision ownership are invalid")
    for artifact in members:
        path = safe_artifact_path(root, artifact.relative_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("export artifact integrity verification failed")
        content = path.read_bytes()
        if len(content) != artifact.byte_count or hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise ValueError("export artifact integrity verification failed")
    return members


def _verify_export_provenance(
    metadata_path: Path,
    revision_id: UUID,
    expected_revision_ids: tuple[UUID, ...] | None = None,
) -> None:
    """Reject historical packages whose provenance is not machine-readable."""
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        provenance = metadata["ai_content_provenance"]
        text = provenance["text"]
        image = provenance["image"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("legacy export provenance is invalid") from exc

    if not isinstance(text, dict) or text != {
        "source": "revisioned-manuscript",
        "revision_id": str(revision_id),
        "owner_review_required": True,
    }:
        raise ValueError("legacy export provenance is invalid")
    if expected_revision_ids:
        expected = [str(source_revision_id) for source_revision_id in expected_revision_ids]
        recorded = metadata.get("source_revision_ids")
        if recorded is not None and recorded != expected:
            raise ValueError("export manuscript scope does not match the requested revision")
        if len(expected) > 1 and recorded != expected:
            raise ValueError("export manuscript scope is incomplete")
    if not isinstance(image, dict):
        raise ValueError("legacy export provenance is invalid")
    source_artifact_id = image.get("source_artifact_id")
    if source_artifact_id is None:
        if image.get("source") != "deterministic-fallback":
            raise ValueError("legacy export provenance is invalid")
    elif not isinstance(source_artifact_id, str) or image.get("source") == "deterministic-fallback":
        raise ValueError("legacy export provenance is invalid")
    if not isinstance(image.get("layout"), str) or not isinstance(image.get("final_cover_filename"), str):
        raise ValueError("legacy export provenance is invalid")


def _verify_source_artifact_review(session: Session, metadata_path: Path) -> None:
    """Prevent replay of a package whose selected source image needs revision."""
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_artifact_id = metadata["ai_content_provenance"]["image"].get("source_artifact_id")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("immutable export art selection cannot be verified") from exc
    if source_artifact_id is None:
        return
    try:
        artifact_id = UUID(source_artifact_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("immutable export art selection cannot be verified") from exc
    artifact = session.get(Artifact, artifact_id)
    if artifact is None or artifact.owner_review_state == "revision_requested":
        raise ValueError("export source image requires owner revision")


def export_book(
    session: Session,
    *,
    root: Path,
    project_id: UUID,
    revision_id: UUID,
    language: str,
    profile: str,
    art_artifact_id: UUID | None = None,
) -> ExportResult:
    """Generate or replay one immutable package for an exact section revision."""

    scope = _resolve_manuscript_scope(
        session, project_id=project_id, revision_id=revision_id
    )
    title, body = scope.title, scope.body
    existing = session.scalars(
        select(Artifact).where(Artifact.relative_path.like(f"exports/{revision_id}/%"))
    ).all()
    if existing:
        if art_artifact_id is not None:
            requested_art = session.scalar(
                select(Artifact)
                .join(SectionRevision, SectionRevision.id == Artifact.revision_id)
                .join(Section, Section.id == SectionRevision.section_id)
                .where(
                    Artifact.id == art_artifact_id,
                    Artifact.revision_id == revision_id,
                    Section.project_id == project_id,
                    Artifact.mime_type.like("image/%"),
                    ~Artifact.relative_path.startswith("exports/"),
                    Artifact.owner_review_state != "revision_requested",
                )
            )
            if requested_art is None:
                raise ValueError("requested art artifact is not an eligible image for this revision")
        verified = verify_export_members(session, root=root, revision_id=revision_id)
        metadata_artifact = next(item for item in verified if Path(item.relative_path).name == "metadata.json")
        metadata_path = safe_artifact_path(root, metadata_artifact.relative_path)
        _verify_export_provenance(
            metadata_path, revision_id, expected_revision_ids=scope.revision_ids
        )
        _verify_source_artifact_review(session, metadata_path)
        if art_artifact_id is not None:
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                recorded_artifact_id = metadata["ai_content_provenance"]["image"]["source_artifact_id"]
            except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("immutable export art selection cannot be verified") from exc
            if recorded_artifact_id != str(art_artifact_id):
                raise ValueError("immutable export art selection is bound to a different artifact")
        return ExportResult(
            revision_id=revision_id,
            title=title,
            package_state="structurally_validated",
            artifacts=tuple(
                ExportArtifact(a.id, Path(a.relative_path).name, a.sha256, a.byte_count)
                for a in sorted(verified, key=lambda item: item.relative_path)
            ),
        )
    markdown = _canonical_markdown(title, body)
    cover_source, image_provenance = _cover_source(
        session, root=root, revision_id=revision_id, project_id=project_id, art_artifact_id=art_artifact_id
    )
    image_provenance["final_cover_filename"] = "cover.jpg"
    cover = _make_cover(title, cover_source)
    image_provenance["final_cover_sha256"] = hashlib.sha256(cover).hexdigest()
    metadata = _metadata(
        title,
        language,
        profile,
        revision_id,
        scope.revision_ids,
        image_provenance,
    )
    files = {
        "book.md": markdown.encode(),
        "cover.jpg": cover,
        "book.epub": _make_epub(title, language, body, cover, revision_id),
        "book.docx": _make_docx(title, body),
        "book.pdf": _make_pdf(title, body),
        "metadata.json": json.dumps(metadata, indent=2, ensure_ascii=False).encode(),
        "metadata.csv": _metadata_csv(metadata),
        "sources.json": b"[]\n",
    }
    validation = _validate_files(files, source_revision_count=len(scope.revision_ids))
    manifest_files = [
        {"filename": name, "byte_count": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        for name, content in files.items()
    ]
    manifest = {
        "project_id": str(project_id),
        "revision_id": str(revision_id),
        "source_revision_ids": [str(source_revision_id) for source_revision_id in scope.revision_ids],
        "title": title,
        "files": manifest_files,
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    files["validation.json"] = (json.dumps(validation, indent=2) + "\n").encode()
    package_prefix = f"exports/{revision_id}"
    session.rollback()
    artifacts: list[ExportArtifact] = []
    for filename, content in files.items():
        artifact = write_artifact(
            session,
            root=root,
            relative_path=f"{package_prefix}/{filename}",
            content=content,
            mime_type=MIME_TYPES[filename.rsplit(".", 1)[-1]],
            run_id=None,
            revision_id=revision_id,
        )
        artifacts.append(ExportArtifact(artifact.id, filename, artifact.sha256, artifact.byte_count))
    return ExportResult(revision_id, title, validation["package_state"], tuple(artifacts))
