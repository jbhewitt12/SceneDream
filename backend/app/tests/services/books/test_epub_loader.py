from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books.epub_loader import EpubBookLoader

DOCUMENTS_DIR = Path(__file__).resolve().parents[5] / "documents"
LEGACY_BOOKS_DIR = Path(__file__).resolve().parents[5] / "books"
CONTENT_DIR = DOCUMENTS_DIR if DOCUMENTS_DIR.exists() else LEGACY_BOOKS_DIR

EXCESSION_EPUB = (
    CONTENT_DIR / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"
)


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_load_excession_epub() -> None:
    loader = EpubBookLoader()
    content = loader.load(EXCESSION_EPUB)

    assert content.slug
    assert "excession" in content.slug.lower()
    assert content.metadata.format == "epub"
    assert len(content.metadata.file_checksum) == 64
    assert content.chapters
    assert 1 in content.chapters


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_epub_chapter_structure() -> None:
    loader = EpubBookLoader()
    content = loader.load(EXCESSION_EPUB)

    first_chapter = content.chapters[1]
    assert first_chapter.number == 1
    assert first_chapter.title
    assert first_chapter.paragraphs
    assert first_chapter.source_name
