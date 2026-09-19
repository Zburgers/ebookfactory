from uuid import uuid4

import pytest

from app.production import parse_production_sections, validate_production_text
from app.main import BriefCreateRequest


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


def test_brief_rejects_reversed_page_or_word_ranges() -> None:
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_pages": {"minimum": 150, "maximum": 50}})
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_length": {"minimum_words": 3000, "maximum_words": 1000}})
