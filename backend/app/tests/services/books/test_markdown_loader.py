from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books.markdown_loader import MarkdownBookLoader

EXAMPLE_MD = (
    Path(__file__).resolve().parents[5]
    / "example_docs"
    / "O_Wilde-The_Selfish_Giant.md"
)


@pytest.mark.skipif(
    not EXAMPLE_MD.exists(), reason="Example Markdown document not available"
)
def test_load_example_markdown_document() -> None:
    loader = MarkdownBookLoader()
    content = loader.load(EXAMPLE_MD)

    assert content.metadata.format == "md"
    assert content.title
    assert content.chapters
    assert content.metadata.source_metadata["section_count"] > 0

    flattened = " ".join(
        paragraph.lower()
        for chapter in content.chapters.values()
        for paragraph in chapter.paragraphs
    )
    assert "every afternoon, as they were coming from school" in flattened
