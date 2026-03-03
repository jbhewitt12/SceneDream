from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from .base import BookChapter
from .html_utils import (
    is_front_matter_content,
    looks_like_heading,
    normalize_whitespace,
)

PROJECT_GUTENBERG_START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK"
PROJECT_GUTENBERG_END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK"


def compute_file_checksum(path: Path) -> str:
    """Compute SHA256 checksum for a document file."""
    sha256 = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def generate_slug(title: str) -> str:
    """Generate a deterministic slug from title text."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


def split_wrapped_paragraphs(lines: Sequence[str]) -> list[str]:
    """Collapse wrapped lines into paragraph blocks separated by blank lines."""
    paragraphs: list[str] = []
    buffer: list[str] = []

    for line in lines:
        normalized_line = normalize_whitespace(line)
        if not normalized_line:
            if buffer:
                paragraphs.append(normalize_whitespace(" ".join(buffer)))
                buffer.clear()
            continue
        buffer.append(normalized_line)

    if buffer:
        paragraphs.append(normalize_whitespace(" ".join(buffer)))

    return [paragraph for paragraph in paragraphs if paragraph]


def trim_project_gutenberg_boilerplate(
    paragraphs: Sequence[str],
) -> tuple[list[str], list[str]]:
    """Trim common Project Gutenberg header/footer markers when present."""
    if not paragraphs:
        return ([], [])

    warnings: list[str] = []
    cleaned = list(paragraphs)
    upper_values = [paragraph.upper() for paragraph in cleaned]

    start_index: int | None = None
    for index, value in enumerate(upper_values):
        if PROJECT_GUTENBERG_START_MARKER in value:
            start_index = index + 1
            break

    if start_index is not None and start_index < len(cleaned):
        cleaned = cleaned[start_index:]
        warnings.append("Trimmed Project Gutenberg header marker.")

    upper_values = [paragraph.upper() for paragraph in cleaned]
    end_index: int | None = None
    for index, value in enumerate(upper_values):
        if PROJECT_GUTENBERG_END_MARKER in value:
            end_index = index
            break

    if end_index is not None and end_index > 0:
        cleaned = cleaned[:end_index]
        warnings.append("Trimmed Project Gutenberg footer marker.")

    return (cleaned, warnings)


def extract_declared_title(paragraphs: Sequence[str]) -> str | None:
    """Return title from 'Title: ...' metadata line when available."""
    for paragraph in paragraphs[:30]:
        if ":" not in paragraph:
            continue
        key, value = paragraph.split(":", 1)
        if key.strip().lower() == "title":
            normalized_value = normalize_whitespace(value)
            if normalized_value:
                return normalized_value
    return None


def build_chapters_from_paragraphs(
    *,
    paragraphs: Sequence[str],
    default_title: str,
    source_name_prefix: str,
) -> dict[int, BookChapter]:
    """Build sequential chapter records from normalized paragraph content."""
    if not paragraphs:
        raise ValueError("No paragraphs were available for chapter construction.")

    chapters: dict[int, BookChapter] = {}
    chapter_number = 1
    current_title = default_title
    pending_heading: str | None = None
    current_body: list[str] = []

    def flush_current_chapter(title: str, body: Sequence[str]) -> None:
        nonlocal chapter_number
        normalized_body = [
            normalize_whitespace(paragraph)
            for paragraph in body
            if normalize_whitespace(paragraph)
        ]
        if not normalized_body:
            return

        chapter_title = normalize_whitespace(title) or f"Chapter {chapter_number}"
        if is_front_matter_content(normalized_body, heading=chapter_title):
            return

        chapters[chapter_number] = BookChapter(
            number=chapter_number,
            title=chapter_title,
            paragraphs=normalized_body,
            source_name=f"{source_name_prefix}_{chapter_number:03d}",
        )
        chapter_number += 1

    for paragraph in paragraphs:
        normalized = normalize_whitespace(paragraph)
        if not normalized:
            continue

        if _is_heading_candidate(normalized):
            if current_body:
                flush_current_chapter(current_title, current_body)
                current_body = []
            pending_heading = normalized
            current_title = pending_heading
            continue

        if pending_heading and not current_body:
            current_title = pending_heading
        current_body.append(normalized)

    if current_body:
        flush_current_chapter(current_title, current_body)

    if chapters:
        return chapters

    normalized_paragraphs = [
        normalize_whitespace(paragraph)
        for paragraph in paragraphs
        if normalize_whitespace(paragraph)
    ]
    if not normalized_paragraphs:
        raise ValueError("No non-empty paragraphs found after normalization.")
    if is_front_matter_content(normalized_paragraphs):
        raise ValueError("Document contained only front/back matter content.")

    return {
        1: BookChapter(
            number=1,
            title=normalize_whitespace(default_title) or "Chapter 1",
            paragraphs=normalized_paragraphs,
            source_name=f"{source_name_prefix}_001",
        )
    }


def _is_heading_candidate(value: str) -> bool:
    if len(value) > 100:
        return False

    lowered = value.lower()
    if lowered.startswith(
        (
            "title:",
            "author:",
            "release date:",
            "language:",
            "credits:",
            "produced by",
            "project gutenberg",
        )
    ):
        return False

    if len(value.split()) > 12:
        return False

    if value.endswith((".", "!", "?", ";")) and not value.isupper():
        return False

    return looks_like_heading(value)
