from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from .base import BookChapter, BookContent, BookMetadata
from .html_utils import is_front_matter_content, normalize_whitespace
from .plain_text_utils import (
    build_chapters_from_paragraphs,
    compute_file_checksum,
    generate_slug,
)

HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
LIST_ITEM_PATTERN = re.compile(r"^\s*[-*+]\s+")
INLINE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")


class MarkdownBookLoader:
    """Load Markdown files into the normalized BookContent structure."""

    PARSER_VERSION = "1.0"

    def load(self, path: Path) -> BookContent:
        """Load an MD file and return BookContent."""
        if not path.exists():
            raise FileNotFoundError(f"Markdown document not found: {path}")

        warnings: list[str] = []
        parse_errors: list[str] = []
        checksum = compute_file_checksum(path)

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
            warnings.append(
                "Markdown file contained undecodable UTF-8 bytes; replaced invalid sequences."
            )
            parse_errors.append("utf8_decode_replacement")

        sections = self._parse_sections(text)
        chapter_title = self._resolve_title(sections, fallback=path.stem)
        chapters = self._build_chapters(sections, fallback_title=chapter_title)
        if not chapters:
            all_paragraphs = [
                paragraph
                for _heading, paragraphs in sections
                for paragraph in paragraphs
                if paragraph
            ]
            chapters = build_chapters_from_paragraphs(
                paragraphs=all_paragraphs,
                default_title=chapter_title,
                source_name_prefix=f"{path.stem}_md",
            )
            warnings.append(
                "Markdown headings were not usable for chapter boundaries; used paragraph fallback."
            )

        metadata = BookMetadata(
            file_path=path,
            file_checksum=checksum,
            parser_version=self.PARSER_VERSION,
            format="md",
            warnings=warnings,
            parse_errors=parse_errors,
            source_metadata={
                "section_count": len(sections),
                "chapter_count": len(chapters),
            },
        )

        return BookContent(
            slug=generate_slug(chapter_title),
            title=chapter_title,
            chapters=chapters,
            metadata=metadata,
            author=None,
        )

    def _parse_sections(self, text: str) -> list[tuple[str | None, list[str]]]:
        sections: list[tuple[str | None, list[str]]] = []
        current_heading: str | None = None
        current_section_paragraphs: list[str] = []
        paragraph_buffer: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph_buffer:
                return
            current_section_paragraphs.append(
                normalize_whitespace(" ".join(paragraph_buffer))
            )
            paragraph_buffer.clear()

        def flush_section() -> None:
            flush_paragraph()
            if current_heading is None and not current_section_paragraphs:
                return
            sections.append((current_heading, list(current_section_paragraphs)))
            current_section_paragraphs.clear()

        for raw_line in text.splitlines():
            heading_match = HEADING_PATTERN.match(raw_line)
            if heading_match:
                flush_section()
                current_heading = self._strip_markdown_inline(heading_match.group(2))
                continue

            stripped = raw_line.strip()
            if not stripped:
                flush_paragraph()
                continue

            without_list_marker = LIST_ITEM_PATTERN.sub("", stripped)
            cleaned = self._strip_markdown_inline(without_list_marker)
            if cleaned:
                paragraph_buffer.append(cleaned)

        flush_section()
        return sections

    def _build_chapters(
        self,
        sections: Sequence[tuple[str | None, list[str]]],
        *,
        fallback_title: str,
    ) -> dict[int, BookChapter]:
        chapters: dict[int, BookChapter] = {}
        chapter_number = 1

        for heading, paragraphs in sections:
            normalized_paragraphs = [
                normalize_whitespace(paragraph)
                for paragraph in paragraphs
                if normalize_whitespace(paragraph)
            ]
            if not normalized_paragraphs:
                continue

            title = normalize_whitespace(heading or f"Chapter {chapter_number}")
            if is_front_matter_content(normalized_paragraphs, heading=title):
                continue

            chapters[chapter_number] = BookChapter(
                number=chapter_number,
                title=title,
                paragraphs=normalized_paragraphs,
                source_name=f"markdown_section_{chapter_number:03d}",
            )
            chapter_number += 1

        return chapters

    def _resolve_title(
        self, sections: Sequence[tuple[str | None, list[str]]], *, fallback: str
    ) -> str:
        for heading, _paragraphs in sections:
            if heading:
                return heading
        return fallback

    def _strip_markdown_inline(self, text: str) -> str:
        stripped = INLINE_LINK_PATTERN.sub(r"\1", text)
        stripped = INLINE_CODE_PATTERN.sub(r"\1", stripped)
        stripped = stripped.replace("**", "").replace("__", "")
        stripped = stripped.replace("*", "").replace("_", "")
        return normalize_whitespace(stripped)
