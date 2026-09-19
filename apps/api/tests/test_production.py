from uuid import uuid4

import pytest

from app.production import parse_production_sections, validate_production_text
from app.main import BriefCreateRequest


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


def test_word_target_keeps_single_document_compatibility() -> None:
    sections = parse_production_sections("A short existing manuscript.", page_target=False)
    assert len(sections) == 1
    assert sections[0].heading == "Draft manuscript"


def test_brief_rejects_reversed_page_or_word_ranges() -> None:
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_pages": {"minimum": 150, "maximum": 50}})
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        BriefCreateRequest(structured_brief={"target_length": {"minimum_words": 3000, "maximum_words": 1000}})
