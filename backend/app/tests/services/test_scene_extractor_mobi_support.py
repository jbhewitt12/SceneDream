from __future__ import annotations

from pathlib import Path

import pytest

from app.services.scene_extraction import scene_extraction
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    MobiExtractionError,
    SceneExtractionConfig,
    SceneExtractor,
)


@pytest.fixture
def extractor() -> SceneExtractor:
    return SceneExtractor(SceneExtractionConfig(enable_refinement=False))


def test_load_chapters_dispatches_to_epub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extractor: SceneExtractor) -> None:
    epub_path = tmp_path / "book.epub"
    epub_path.write_bytes(b"dummy")
    fake_book = object()

    def fake_read_epub(path: str) -> object:
        assert path == str(epub_path)
        return fake_book

    monkeypatch.setattr(scene_extraction.epub, "read_epub", fake_read_epub)

    expected = [
        Chapter(
            number=1,
            title="Chapter 1",
            paragraphs=["Example paragraph."],
            source_name="chapter1.xhtml",
        )
    ]

    def fake_from_book(self: SceneExtractor, book: object) -> list[Chapter]:
        assert book is fake_book
        return expected

    monkeypatch.setattr(SceneExtractor, "_load_chapters_from_epub_book", fake_from_book)

    chapters = extractor._load_chapters(epub_path)
    assert chapters is expected


def test_load_chapters_dispatches_to_mobi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extractor: SceneExtractor) -> None:
    mobi_path = tmp_path / "book.mobi"
    mobi_path.write_bytes(b"dummy")

    expected = [
        Chapter(
            number=1,
            title="Chapter 1",
            paragraphs=["Example paragraph."],
            source_name="chapter1.html",
        )
    ]

    def fake_from_mobi(self: SceneExtractor, path: Path) -> list[Chapter]:
        assert path == mobi_path
        return expected

    monkeypatch.setattr(SceneExtractor, "_load_chapters_from_mobi", fake_from_mobi)

    chapters = extractor._load_chapters(mobi_path)
    assert chapters is expected


def test_load_chapters_from_mobi_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extractor: SceneExtractor) -> None:
    book_path = tmp_path / "book.mobi"
    book_path.write_bytes(b"dummy")

    extracted_dir = tmp_path / "extracted"
    (extracted_dir / "mobi7").mkdir(parents=True)
    chapter_html = extracted_dir / "mobi7" / "chapter1.html"
    chapter_html.write_text(
        "<html><body><h1>Chapter 1</h1><p>Actual content.</p></body></html>",
        encoding="utf-8",
    )
    toc_html = extracted_dir / "mobi7" / "toc.html"
    toc_html.write_text(
        "<html><body><h1>Table of Contents</h1><p>Intro text.</p></body></html>",
        encoding="utf-8",
    )

    def fake_extract(path: str) -> tuple[str, str]:
        assert path == str(book_path)
        return str(extracted_dir), str(chapter_html)

    monkeypatch.setattr(scene_extraction.mobi, "extract", fake_extract)

    chapters = extractor._load_chapters_from_mobi(book_path)
    assert len(chapters) == 1
    only = chapters[0]
    assert only.number == 1
    assert only.title == "Chapter 1"
    assert only.paragraphs == ["Chapter 1 Actual content."]
    assert only.source_name == "mobi7/chapter1.html"
    assert not extracted_dir.exists()


def test_load_chapters_from_mobi_epub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extractor: SceneExtractor) -> None:
    book_path = tmp_path / "book.mobi"
    book_path.write_bytes(b"dummy")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    epub_path = extracted_dir / "converted.epub"
    epub_path.write_bytes(b"dummy")

    expected = [
        Chapter(
            number=1,
            title="Chapter 1",
            paragraphs=["Example paragraph."],
            source_name="chapter1.xhtml",
        )
    ]

    def fake_extract(path: str) -> tuple[str, str]:
        assert path == str(book_path)
        return str(extracted_dir), str(epub_path)

    fake_book = object()

    def fake_read_epub(path: str) -> object:
        assert path == str(epub_path)
        return fake_book

    def fake_load_from_epub(self: SceneExtractor, book: object) -> list[Chapter]:
        assert book is fake_book
        return expected

    monkeypatch.setattr(scene_extraction.mobi, "extract", fake_extract)
    monkeypatch.setattr(scene_extraction.epub, "read_epub", fake_read_epub)
    monkeypatch.setattr(SceneExtractor, "_load_chapters_from_epub_book", fake_load_from_epub)

    chapters = extractor._load_chapters_from_mobi(book_path)
    assert chapters is expected
    assert not extracted_dir.exists()


def test_load_chapters_from_mobi_no_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extractor: SceneExtractor) -> None:
    book_path = tmp_path / "book.mobi"
    book_path.write_bytes(b"dummy")

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    pdf_path = extracted_dir / "book.pdf"
    pdf_path.write_bytes(b"dummy")

    def fake_extract(path: str) -> tuple[str, str]:
        assert path == str(book_path)
        return str(extracted_dir), str(pdf_path)

    monkeypatch.setattr(scene_extraction.mobi, "extract", fake_extract)

    with pytest.raises(MobiExtractionError):
        extractor._load_chapters_from_mobi(book_path)
    assert not extracted_dir.exists()


def test_load_chapters_unsupported_extension(tmp_path: Path, extractor: SceneExtractor) -> None:
    invalid_path = tmp_path / "book.txt"
    invalid_path.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError):
        extractor._load_chapters(invalid_path)


def test_parse_html_chapter_files_skips_front_matter(tmp_path: Path, extractor: SceneExtractor) -> None:
    toc = tmp_path / "toc.html"
    toc.write_text(
        "<html><body><h1>Table of Contents</h1><p>Intro text.</p></body></html>",
        encoding="utf-8",
    )
    chapter = tmp_path / "chapter1.html"
    chapter.write_text(
        "<html><body><h1>Chapter 1</h1><p>Actual content.</p></body></html>",
        encoding="utf-8",
    )

    html_files = [toc, chapter]
    chapters = extractor._parse_html_chapter_files(html_files, tmp_path)

    assert len(chapters) == 1
    only = chapters[0]
    assert only.number == 1
    assert only.title == "Chapter 1"
    assert only.paragraphs == ["Chapter 1 Actual content."]
    assert only.source_name == "chapter1.html"
