from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books import BookContentService, BookContentServiceError

EXCESSION_EPUB = (
    Path(__file__).resolve().parents[5]
    / "books"
    / "Iain Banks"
    / "Excession"
    / "Excession - Iain M. Banks.epub"
)


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_load_book_epub() -> None:
    service = BookContentService()
    content = service.load_book(EXCESSION_EPUB)
    assert content is not None
    assert content.chapters
    assert content.metadata.format == "epub"


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_load_book_caching() -> None:
    service = BookContentService()
    content1 = service.load_book(EXCESSION_EPUB)
    content2 = service.load_book(EXCESSION_EPUB)
    assert content1 is content2


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_load_book_no_cache() -> None:
    service = BookContentService()
    content1 = service.load_book(EXCESSION_EPUB, cache=False)
    content2 = service.load_book(EXCESSION_EPUB, cache=False)
    assert content1 is not content2


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_load_book_relative_path() -> None:
    service = BookContentService()
    relative_path = "books/Iain Banks/Excession/Excession - Iain M. Banks.epub"
    content = service.load_book(relative_path)
    assert content.chapters


def test_load_book_not_found() -> None:
    service = BookContentService()
    with pytest.raises(BookContentServiceError, match="not found"):
        service.load_book("/nonexistent/book.epub")


def test_load_book_unsupported_format(tmp_path: Path) -> None:
    service = BookContentService()
    dummy = tmp_path / "book.pdf"
    dummy.write_text("dummy", encoding="utf-8")
    with pytest.raises(BookContentServiceError, match="Unsupported format"):
        service.load_book(dummy)
