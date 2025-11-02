from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Iterable
from pathlib import Path

import mobi
from bs4 import BeautifulSoup

from .base import BookChapter, BookContent, BookMetadata
from .epub_loader import EpubBookLoader
from .html_utils import (
    extract_paragraphs,
    is_front_matter,
    is_front_matter_content,
    looks_like_heading,
    normalize_whitespace,
)


class MobiExtractionError(RuntimeError):
    """Raised when a MOBI file cannot be unpacked or parsed."""


class MobiBookLoader:
    """Load MOBI/AZW book files into the normalized BookContent structure."""

    PARSER_VERSION = "1.0"
    HTML_SUFFIXES = {".html", ".htm", ".xhtml"}

    def __init__(self) -> None:
        self._epub_loader = EpubBookLoader()

    def load(self, path: Path) -> BookContent:
        """Load MOBI file and return BookContent representation."""
        if not path.exists():
            raise FileNotFoundError(f"MOBI not found: {path}")

        checksum = self._compute_checksum(path)

        try:
            temp_dir_str, primary_path_str = mobi.extract(str(path))
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise MobiExtractionError(f"Failed to extract MOBI '{path}': {exc}") from exc

        temp_dir = Path(temp_dir_str)
        primary_path = Path(primary_path_str)

        try:
            if primary_path.suffix.lower() == ".epub" and primary_path.exists():
                return self._load_from_epub(
                    original_path=path,
                    checksum=checksum,
                    extracted_epub=primary_path,
                )

            html_files = self._collect_html_files(temp_dir, primary_path)
            if not html_files:
                raise MobiExtractionError(
                    f"MOBI '{path}' did not contain any HTML content to parse."
                )

            chapters = self._extract_chapters(
                html_files,
                base_dir=temp_dir if temp_dir.exists() else primary_path.parent,
            )
            if not chapters:
                raise MobiExtractionError(
                    f"MOBI '{path}' could not be parsed into chapters."
                )

            metadata = BookMetadata(
                file_path=path,
                file_checksum=checksum,
                parser_version=self.PARSER_VERSION,
                format="mobi",
            )

            title = path.stem
            slug = self._generate_slug(title)

            return BookContent(
                slug=slug,
                title=title,
                chapters=chapters,
                metadata=metadata,
                author=None,
            )
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _load_from_epub(
        self,
        *,
        original_path: Path,
        checksum: str,
        extracted_epub: Path,
    ) -> BookContent:
        """Handle MOBI files that unpack to an EPUB."""
        content = self._epub_loader.load(extracted_epub)
        metadata = BookMetadata(
            file_path=original_path,
            file_checksum=checksum,
            parser_version=self.PARSER_VERSION,
            format="mobi",
            warnings=["Extracted as EPUB from MOBI archive"],
        )
        return BookContent(
            slug=content.slug,
            title=content.title,
            chapters=content.chapters,
            metadata=metadata,
            author=content.author,
        )

    def _collect_html_files(
        self,
        temp_dir: Path,
        primary_path: Path,
    ) -> list[Path]:
        """Collect candidate HTML files produced during extraction."""
        candidates: list[Path] = []

        if primary_path.exists() and primary_path.suffix.lower() in self.HTML_SUFFIXES:
            candidates.append(primary_path)

        if temp_dir.exists():
            candidates.extend(
                sorted(
                    path
                    for path in temp_dir.rglob("*")
                    if path.is_file() and path.suffix.lower() in self.HTML_SUFFIXES
                )
            )

        seen: set[Path] = set()
        deduped: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(candidate)

        return deduped

    def _extract_chapters(
        self,
        html_files: Iterable[Path],
        *,
        base_dir: Path,
    ) -> dict[int, BookChapter]:
        """Parse HTML files into sequential chapters."""
        chapters: dict[int, BookChapter] = {}
        chapter_number = 1
        pending_heading: str | None = None

        for html_path in html_files:
            try:
                html = html_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            fragments = self._split_mobi_fragments(html)
            total_fragments = len(fragments)

            for fragment_index, fragment_html in enumerate(fragments):
                soup = BeautifulSoup(fragment_html, "html.parser")
                paragraphs = extract_paragraphs(soup)
                if not paragraphs:
                    continue

                if is_front_matter_content(paragraphs):
                    continue

                title, body_paragraphs = self._extract_heading_from_paragraphs(paragraphs)
                if not body_paragraphs:
                    if title and looks_like_heading(title):
                        pending_heading = normalize_whitespace(title)
                    continue

                source_name = self._build_source_name(
                    html_path,
                    base_dir,
                    fragment_index,
                    total_fragments,
                    title,
                    body_paragraphs,
                )

                # Skip front matter identified by source name or title.
                if is_front_matter(source_name):
                    continue
                if title and is_front_matter(title):
                    continue
                if is_front_matter_content(body_paragraphs, heading=title):
                    continue

                final_title = pending_heading or title or f"Chapter {chapter_number}"
                pending_heading = None
                chapters[chapter_number] = BookChapter(
                    number=chapter_number,
                    title=final_title,
                    paragraphs=body_paragraphs,
                    source_name=source_name,
                    metadata={"fragment_index": fragment_index},
                )
                chapter_number += 1

        return chapters

    def _build_source_name(
        self,
        html_path: Path,
        base_dir: Path,
        fragment_index: int,
        total_fragments: int,
        title: str | None,
        paragraphs: Iterable[str],
    ) -> str:
        """Construct a descriptive source name for debugging."""
        try:
            relative = html_path.relative_to(base_dir)
            base_name = str(relative)
        except ValueError:
            base_name = html_path.name

        if total_fragments > 1:
            base_name = f"{base_name}#fragment{fragment_index:03d}"

        tokens_source = title or next(iter(paragraphs), "")
        if tokens_source:
            slug_tokens = re.findall(r"[a-z0-9]+", tokens_source.lower())
            if slug_tokens:
                base_name = f"{base_name}__{'_'.join(slug_tokens[:6])}"

        return base_name

    @staticmethod
    def _split_mobi_fragments(html: str) -> list[str]:
        """Split MOBI HTML by page break markers."""
        if "<mbp:pagebreak" not in html.lower():
            return [html]
        fragments = [
            fragment
            for fragment in re.split(r"<mbp:pagebreak\s*/?>", html, flags=re.IGNORECASE)
            if fragment.strip()
        ]
        return fragments or [html]

    def _extract_heading_from_paragraphs(
        self,
        paragraphs: Iterable[str],
    ) -> tuple[str | None, list[str]]:
        """Identify heading-like first paragraph and return body paragraphs."""
        paragraphs_list = list(paragraphs)
        if not paragraphs_list:
            return (None, [])

        first = normalize_whitespace(paragraphs_list[0])
        remaining = [normalize_whitespace(p) for p in paragraphs_list[1:] if p]

        if looks_like_heading(first):
            return (first, remaining)
        return (None, [normalize_whitespace(p) for p in paragraphs_list if p])

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        """Compute the SHA256 checksum of the MOBI file."""
        sha256 = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _generate_slug(title: str) -> str:
        """Generate a URL-safe slug from the given title."""
        slug = title.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")
