from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books.docx_loader import DocxBookLoader

EXAMPLE_DOCX = (
    Path(__file__).resolve().parents[5]
    / "example_docs"
    / "F_R_Stockton-The_Lady_or_the_Tiger.docx"
)


@pytest.mark.skipif(
    not EXAMPLE_DOCX.exists(), reason="Example DOCX document not available"
)
def test_load_example_docx_document() -> None:
    loader = DocxBookLoader()
    content = loader.load(EXAMPLE_DOCX)

    assert content.metadata.format == "docx"
    assert content.title
    assert content.chapters
    assert content.metadata.source_metadata["docx_paragraph_nodes"] > 0

    flattened = " ".join(
        paragraph.lower()
        for chapter in content.chapters.values()
        for paragraph in chapter.paragraphs
    )
    assert "semi-barbaric king" in flattened
    assert any("Project Gutenberg" in warning for warning in content.metadata.warnings)
