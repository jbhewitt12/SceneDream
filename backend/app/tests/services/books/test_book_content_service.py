from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books import BookContentService, BookContentServiceError

DOCUMENTS_DIR = Path(__file__).resolve().parents[5] / "documents"
LEGACY_BOOKS_DIR = Path(__file__).resolve().parents[5] / "books"
CONTENT_DIR = DOCUMENTS_DIR if DOCUMENTS_DIR.exists() else LEGACY_BOOKS_DIR

EXCESSION_EPUB = (
    CONTENT_DIR / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"
)
EXAMPLE_DOCS_DIR = Path(__file__).resolve().parents[5] / "example_docs"
EXAMPLE_TXT = EXAMPLE_DOCS_DIR / "H_G_Wells-The_Star.txt"
EXAMPLE_MD = EXAMPLE_DOCS_DIR / "E_A_Poe-The_Cask_of_Amontillado.md"
EXAMPLE_DOCX = EXAMPLE_DOCS_DIR / "F_R_Stockton-The_Lady_or_the_Tiger.docx"


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
    relative_root = "documents" if DOCUMENTS_DIR.exists() else "books"
    relative_path = (
        f"{relative_root}/Iain Banks/Excession/Excession - Iain M. Banks.epub"
    )
    content = service.load_book(relative_path)
    assert content.chapters


@pytest.mark.skipif(
    not EXAMPLE_TXT.exists(), reason="Example TXT document not available"
)
def test_load_book_example_txt() -> None:
    service = BookContentService()
    content = service.load_book(EXAMPLE_TXT)

    assert content.chapters
    assert content.metadata.format == "txt"
    assert content.metadata.source_metadata["paragraph_count"] > 0


@pytest.mark.skipif(
    not EXAMPLE_MD.exists(), reason="Example Markdown document not available"
)
def test_load_book_example_markdown() -> None:
    service = BookContentService()
    content = service.load_book(EXAMPLE_MD)

    assert content.chapters
    assert content.metadata.format == "md"
    assert content.metadata.source_metadata["chapter_count"] >= 1


@pytest.mark.skipif(
    not EXAMPLE_DOCX.exists(), reason="Example DOCX document not available"
)
def test_load_book_example_docx() -> None:
    service = BookContentService()
    content = service.load_book(EXAMPLE_DOCX)

    assert content.chapters
    assert content.metadata.format == "docx"
    assert content.metadata.source_metadata["paragraph_count"] > 0


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


def test_resolve_book_path_documents_falls_back_to_legacy_books(tmp_path: Path) -> None:
    service = BookContentService(project_root=tmp_path)
    legacy_path = tmp_path / "books" / "author" / "book.txt"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("Chapter 1\n\nLegacy paragraph.", encoding="utf-8")

    resolved = service.resolve_book_path("documents/author/book.txt")
    assert resolved == legacy_path.resolve()


def test_load_book_legacy_books_path_resolves_documents(tmp_path: Path) -> None:
    service = BookContentService(project_root=tmp_path)
    documents_path = tmp_path / "documents" / "author" / "book.txt"
    documents_path.parent.mkdir(parents=True, exist_ok=True)
    documents_path.write_text("Chapter 1\n\nPrimary paragraph.", encoding="utf-8")

    content = service.load_book("books/author/book.txt")
    assert content.metadata.file_path == documents_path.resolve()


def test_normalize_source_path_rewrites_books_to_documents(tmp_path: Path) -> None:
    service = BookContentService(project_root=tmp_path)
    file_path = tmp_path / "books" / "author" / "book.epub"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("stub", encoding="utf-8")

    normalized = service.normalize_source_path(file_path.resolve())
    assert normalized == "documents/author/book.epub"


def test_normalize_source_path_keeps_external_absolute_paths(tmp_path: Path) -> None:
    service = BookContentService(project_root=tmp_path / "repo")
    external_path = tmp_path / "outside" / "book.epub"
    external_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.write_text("stub", encoding="utf-8")

    normalized = service.normalize_source_path(external_path.resolve())
    assert normalized == str(external_path.resolve())
