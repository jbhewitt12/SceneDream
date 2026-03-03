from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books.text_loader import TextBookLoader

EXAMPLE_TXT = (
    Path(__file__).resolve().parents[5] / "example_docs" / "H_G_Wells-The_Star.txt"
)


@pytest.mark.skipif(not EXAMPLE_TXT.exists(), reason="Example TXT document not available")
def test_load_example_txt_document() -> None:
    loader = TextBookLoader()
    content = loader.load(EXAMPLE_TXT)

    assert content.metadata.format == "txt"
    assert content.title
    assert content.chapters
    assert content.metadata.source_metadata["paragraph_count"] > 0

    flattened = " ".join(
        paragraph.lower()
        for chapter in content.chapters.values()
        for paragraph in chapter.paragraphs
    )
    assert "announcement was made" in flattened
    assert any("Project Gutenberg" in warning for warning in content.metadata.warnings)
