from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(slots=True)
class BookChapter:
    number: int  # 1-indexed
    title: str
    paragraphs: list[str]  # 1-indexed when accessed (para[0] is paragraph 1)
    source_name: str  # e.g., "chapter003.xhtml" for debugging
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BookMetadata:
    file_path: Path
    file_checksum: str  # SHA256
    parser_version: str  # e.g., "1.0"
    format: str  # "epub" or "mobi"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BookContent:
    slug: str
    title: str
    chapters: dict[int, BookChapter]  # keyed by chapter number (1-indexed)
    metadata: BookMetadata
    author: str | None = None


class BookLoader(Protocol):
    def load(self, path: Path) -> BookContent:
        """Load book from file path and return normalized content."""
        ...
