from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books import BookContentServiceError
from app.services.books.base import BookChapter, BookContent, BookMetadata
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    SceneExtractionConfig,
    SceneExtractor,
)


@pytest.fixture
def extractor() -> SceneExtractor:
    return SceneExtractor(SceneExtractionConfig(enable_refinement=False))


def _make_book_content(book_path: Path) -> BookContent:
    metadata = BookMetadata(
        file_path=book_path,
        file_checksum="checksum",
        parser_version="1.0",
        format=book_path.suffix.lstrip(".") or "epub",
    )
    chapters = {
        1: BookChapter(
            number=1,
            title="Chapter 1",
            paragraphs=["Paragraph 1", "Paragraph 2"],
            source_name="chapter1.xhtml",
        ),
        2: BookChapter(
            number=2,
            title="Chapter 2",
            paragraphs=["Paragraph 3"],
            source_name="chapter2.xhtml",
        ),
    }
    return BookContent(
        slug="book",
        title="Book Title",
        chapters=chapters,
        metadata=metadata,
        author="Author",
    )


def test_load_chapters_uses_book_content_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extractor: SceneExtractor,
) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_text("dummy", encoding="utf-8")
    content = _make_book_content(book_path)

    def fake_load_book(path: Path, *, cache: bool = True) -> BookContent:  # noqa: ARG001
        assert path == book_path
        return content

    monkeypatch.setattr(extractor._book_service, "load_book", fake_load_book)

    chapters = extractor._load_chapters(book_path)
    assert isinstance(chapters, list)
    assert [chapter.number for chapter in chapters] == [1, 2]

    first = chapters[0]
    assert isinstance(first, Chapter)
    assert first.title == "Chapter 1"
    assert first.source_name == "chapter1.xhtml"
    assert first.paragraphs == ["Paragraph 1", "Paragraph 2"]

    # Ensure paragraph lists are copied and do not mutate cached content.
    first.paragraphs.append("New paragraph")
    assert content.chapters[1].paragraphs == ["Paragraph 1", "Paragraph 2"]


def test_load_chapters_propagates_service_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extractor: SceneExtractor,
) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_text("dummy", encoding="utf-8")

    def fake_load_book(path: Path, *, cache: bool = True) -> BookContent:  # noqa: ARG001
        raise BookContentServiceError("boom")

    monkeypatch.setattr(extractor._book_service, "load_book", fake_load_book)

    with pytest.raises(RuntimeError, match="Failed to load chapters"):
        extractor._load_chapters(book_path)
