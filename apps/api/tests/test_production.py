from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.production import parse_production_sections, validate_production_text
from app.main import BriefCreateRequest, create_app
from app.models import Base
from app.settings import Settings


def _page_sections(count: int, body: str = "prose") -> str:
    return "\n\n".join(f"## Section {index}\n\n{body}" for index in range(1, count + 1))


def test_page_manuscript_is_split_into_ordered_sections() -> None:
    text = "# The Book\n\n## Opening\n\nFirst chapter prose.\n\n## Turning Point\n\nSecond chapter prose."
    sections = parse_production_sections(text, page_target=True)
    assert [(s.heading, s.content) for s in sections] == [
        ("Opening", "First chapter prose."),
        ("Turning Point", "Second chapter prose."),
    ]


def test_page_manuscript_rejects_placeholder_or_incomplete_output() -> None:
    with pytest.raises(ValueError, match="placeholder"):
        validate_production_text("# Book\n\n## Chapter 1\n\nTODO: write this later", page_target=True)
    with pytest.raises(ValueError, match="section"):
        validate_production_text("# Book\n\nThis has no chapter headings.", page_target=True)


def test_page_manuscript_requires_eight_to_fifteen_sections() -> None:
    with pytest.raises(ValueError, match="8 to 15 sections"):
        validate_production_text(_page_sections(7), page_target=True)
    with pytest.raises(ValueError, match="8 to 15 sections"):
        validate_production_text(_page_sections(16), page_target=True)

    validate_production_text(_page_sections(8), page_target=True)
    validate_production_text(_page_sections(15), page_target=True)


def test_page_manuscript_enforces_estimated_page_word_bounds() -> None:
    short = _page_sections(8, "short text")
    with pytest.raises(ValueError, match="short for the requested page range"):
        validate_production_text(short, page_target=True, target_pages={"minimum": 50, "maximum": 150})
    enough = "word " * 2500
    validate_production_text(_page_sections(8, enough), page_target=True, target_pages={"minimum": 50, "maximum": 150})
    with pytest.raises(ValueError, match="long for the requested page range"):
        validate_production_text(_page_sections(8, 'word ' * 28000), page_target=True, target_pages={"minimum": 50, "maximum": 150})


def test_word_target_keeps_single_document_compatibility() -> None:
    sections = parse_production_sections("A short existing manuscript.", page_target=False)
    assert len(sections) == 1
    assert sections[0].heading == "Draft manuscript"


def test_word_target_enforces_requested_bounds() -> None:
    with pytest.raises(ValueError, match="short for the requested word range"):
        validate_production_text("word " * 99, page_target=False, target_length={"minimum_words": 100, "maximum_words": 200})
    validate_production_text("word " * 150, page_target=False, target_length={"minimum_words": 100, "maximum_words": 200})
    with pytest.raises(ValueError, match="long for the requested word range"):
        validate_production_text("word " * 201, page_target=False, target_length={"minimum_words": 100, "maximum_words": 200})


def test_brief_rejects_reversed_page_or_word_ranges() -> None:
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_pages": {"minimum": 150, "maximum": 50}})
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_length": {"minimum_words": 3000, "maximum_words": 1000}})


def test_brief_rejects_non_positive_or_ambiguous_length_targets() -> None:
    with pytest.raises(ValueError, match="positive"):
        BriefCreateRequest(structured_brief={"target_pages": {"minimum": 0, "maximum": 10}})
    with pytest.raises(ValueError, match="one length target"):
        BriefCreateRequest(
            structured_brief={
                "target_pages": {"minimum": 1, "maximum": 2},
                "target_length": {"minimum_words": 100, "maximum_words": 200},
            }
        )


def test_sqlite_production_result_accepts_persisted_lease(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'sqlite-production.db'}"
    Base.metadata.create_all(create_engine(database_url))
    settings = Settings(
        database_url=database_url,
        owner_token="owner",
        worker_token="worker",
        artifact_root=tmp_path / "artifacts",
    )

    with TestClient(create_app(settings), headers={"Authorization": "Bearer owner"}) as client:
        project = client.post(
            "/projects", json={"title": "SQLite Production", "profile": "fiction", "language": "en"}
        ).json()
        project_id = project["project_id"]
        brief = client.post(
            f"/projects/{project_id}/briefs",
            json={"structured_brief": {"promise_or_premise": "A bounded story"}},
        ).json()
        approval = client.post(
            f"/projects/{project_id}/briefs/{brief['brief_id']}/approve",
            json={"expected_content_hash": brief["content_hash"], "budget": {}},
        ).json()
        worker_headers = {"X-Ebook-Worker-Token": "worker"}
        outline = client.post(
            "/private/worker/claim", json={"worker_id": "sqlite-worker"}, headers=worker_headers
        ).json()
        outline_result = client.post(
            "/private/worker/task-result",
            headers=worker_headers,
            json={
                "job_id": outline["job_id"],
                "worker_id": "sqlite-worker",
                "generation": outline["generation"],
                "result": "## Opening\nA bounded story.",
                "provider": "fixture",
                "model": "fixture",
                "call_id": str(uuid4()),
            },
        )
        assert outline_result.status_code == 200, outline_result.text
        production = client.post(
            "/private/worker/claim", json={"worker_id": "sqlite-worker"}, headers=worker_headers
        ).json()
        result = client.post(
            "/private/worker/production-result",
            headers=worker_headers,
            json={
                "job_id": production["job_id"],
                "worker_id": "sqlite-worker",
                "generation": production["generation"],
                "content": "# SQLite Production\n\nA bounded story.",
                "provider": "fixture",
                "model": "fixture",
                "call_id": str(uuid4()),
            },
        )

    assert result.status_code == 200, result.text
    assert result.json()["run_id"] == approval["run_id"]
