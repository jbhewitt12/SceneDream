from __future__ import annotations

from pathlib import Path

import pytest

from app.services.books.mobi_loader import MobiBookLoader

DOCUMENTS_DIR = Path(__file__).resolve().parents[5] / "documents"
LEGACY_BOOKS_DIR = Path(__file__).resolve().parents[5] / "books"
CONTENT_DIR = DOCUMENTS_DIR if DOCUMENTS_DIR.exists() else LEGACY_BOOKS_DIR

SHOGUN_MOBI = CONTENT_DIR / "James Clavell" / "Shogun" / "Shogun - James Clavell.mobi"


@pytest.mark.skipif(not SHOGUN_MOBI.exists(), reason="Test MOBI not available")
def test_load_shogun_mobi() -> None:
    loader = MobiBookLoader()
    content = loader.load(SHOGUN_MOBI)

    assert content.slug
    assert len(content.chapters) > 0
    assert content.metadata.format == "mobi"
    assert len(content.metadata.file_checksum) == 64
    assert content.metadata.parser_version == loader.PARSER_VERSION


@pytest.mark.skipif(not SHOGUN_MOBI.exists(), reason="Test MOBI not available")
def test_mobi_chapter_structure() -> None:
    loader = MobiBookLoader()
    content = loader.load(SHOGUN_MOBI)

    first_chapter = content.chapters[1]
    assert first_chapter.number == 1
    assert first_chapter.title
    assert first_chapter.paragraphs
