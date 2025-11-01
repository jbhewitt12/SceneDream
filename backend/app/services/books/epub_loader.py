from __future__ import annotations

import hashlib
import re
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from .base import BookChapter, BookContent, BookMetadata
from .html_utils import extract_paragraphs, extract_title, is_front_matter


class EpubBookLoader:
    """Loads EPUB files into the normalized BookContent structure."""

    PARSER_VERSION = "1.0"
    _SKIP_NAME_TOKENS = ("nav", "cover", "titlepage", "toc")

    def load(self, path: Path) -> BookContent:
        """Load the provided EPUB file and return BookContent."""
        if not path.exists():
            raise FileNotFoundError(f"EPUB not found: {path}")

        checksum = self._compute_checksum(path)
        book = epub.read_epub(str(path))
        chapters = self._extract_chapters(book)

        title_entries = book.get_metadata("DC", "title")
        title = title_entries[0][0] if title_entries else path.stem

        author_entries = book.get_metadata("DC", "creator")
        author = author_entries[0][0] if author_entries else None

        metadata = BookMetadata(
            file_path=path,
            file_checksum=checksum,
            parser_version=self.PARSER_VERSION,
            format="epub",
        )

        return BookContent(
            slug=self._generate_slug(title),
            title=title,
            chapters=chapters,
            metadata=metadata,
            author=author,
        )

    def _extract_chapters(self, book: epub.EpubBook) -> dict[int, BookChapter]:
        """Extract chapters from the EPUB spine order."""
        chapters: dict[int, BookChapter] = {}
        chapter_number = 1

        for spine_entry in book.spine:
            item_id = spine_entry[0]
            item = book.get_item_with_id(item_id)
            if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            source_name = item.get_name() or f"chapter_{chapter_number}"
            normalized_name = source_name.lower()

            if any(token in normalized_name for token in self._SKIP_NAME_TOKENS):
                continue

            if is_front_matter(source_name):
                continue

            html = item.get_content().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = extract_paragraphs(soup)
            if not paragraphs:
                continue

            title = extract_title(soup) or f"Chapter {chapter_number}"

            chapters[chapter_number] = BookChapter(
                number=chapter_number,
                title=title,
                paragraphs=paragraphs,
                source_name=source_name,
            )
            chapter_number += 1

        if not chapters:
            raise ValueError("No chapters extracted from EPUB")

        return chapters

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        """Compute the SHA256 checksum for the provided file path."""
        sha256 = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _generate_slug(title: str) -> str:
        """Generate a deterministic slug from the provided title."""
        slug = title.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")
