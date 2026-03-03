from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books import BookContentService

DOCUMENTS_DIR = Path(__file__).resolve().parents[5] / "documents"
LEGACY_BOOKS_DIR = Path(__file__).resolve().parents[5] / "books"
CONTENT_DIR = DOCUMENTS_DIR if DOCUMENTS_DIR.exists() else LEGACY_BOOKS_DIR

EXCESSION = CONTENT_DIR / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"


@pytest.mark.skipif(not EXCESSION.exists(), reason="Test EPUB not available")
def test_excession_chapter_count() -> None:
    """Verify Excession has an expected number of chapters."""
    service = BookContentService()
    content = service.load_book(EXCESSION)

    assert len(content.chapters) > 10
    assert 1 in content.chapters
    assert content.chapters[1].title


@pytest.mark.skipif(not EXCESSION.exists(), reason="Test EPUB not available")
def test_excession_paragraph_counts() -> None:
    """Verify first chapter paragraphs are non-empty strings."""
    service = BookContentService()
    content = service.load_book(EXCESSION)

    first_chapter = content.chapters[1]
    assert len(first_chapter.paragraphs) > 5

    for paragraph in first_chapter.paragraphs[:5]:
        assert isinstance(paragraph, str)
        assert paragraph


@pytest.mark.skipif(not EXCESSION.exists(), reason="Test EPUB not available")
def test_chapter_numbering_is_sequential() -> None:
    """Verify chapters are numbered sequentially from 1."""
    service = BookContentService()
    content = service.load_book(EXCESSION)

    chapter_numbers = sorted(content.chapters.keys())
    assert chapter_numbers[0] == 1
    for index, number in enumerate(chapter_numbers):
        assert number >= 1
        if index > 0:
            assert number > chapter_numbers[index - 1]
