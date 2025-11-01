from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .base import BookContent
from .epub_loader import EpubBookLoader
from .mobi_loader import MobiBookLoader, MobiExtractionError


class BookContentServiceError(RuntimeError):
    """Raised when book content cannot be loaded."""


@dataclass(slots=True)
class _CacheEntry:
    checksum: str
    parser_version: str
    content: BookContent


class BookContentService:
    """Service for loading and caching book content from EPUB and MOBI files."""

    def __init__(self, *, project_root: Path | None = None) -> None:
        self._epub_loader = EpubBookLoader()
        self._mobi_loader = MobiBookLoader()
        self._cache: dict[str, _CacheEntry] = {}
        self._project_root = project_root or Path(__file__).resolve().parents[4]

    def load_book(self, path: str | Path, *, cache: bool = True) -> BookContent:
        """
        Load a book from the supplied path.

        Args:
            path: Absolute or relative path to an EPUB/MOBI file.
            cache: When True (default), reuse cached content when file checksum matches.
        """
        resolved_path = self._resolve_path(path)

        if not resolved_path.exists():
            raise BookContentServiceError(f"Book file not found: {path}")

        cache_key = str(resolved_path)
        if cache and cache_key in self._cache:
            cached_entry = self._cache[cache_key]
            current_checksum = self._compute_checksum(resolved_path)
            if current_checksum == cached_entry.checksum:
                return cached_entry.content

        suffix = resolved_path.suffix.lower()
        try:
            if suffix == ".epub":
                content = self._epub_loader.load(resolved_path)
            elif suffix in {".mobi", ".azw", ".azw3"}:
                content = self._mobi_loader.load(resolved_path)
            else:
                raise BookContentServiceError(f"Unsupported format: {suffix}")
        except MobiExtractionError as exc:
            raise BookContentServiceError(str(exc)) from exc
        except FileNotFoundError as exc:
            raise BookContentServiceError(str(exc)) from exc

        if cache:
            self._cache[cache_key] = _CacheEntry(
                checksum=content.metadata.file_checksum,
                parser_version=content.metadata.parser_version,
                content=content,
            )

        return content

    def clear_cache(self) -> None:
        """Clear any cached book content."""
        self._cache.clear()

    def _resolve_path(self, path: str | Path) -> Path:
        """Resolve relative paths against the configured project root."""
        p = Path(path)
        if p.is_absolute():
            return p
        return (self._project_root / p).resolve()

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        """Compute the SHA256 checksum for the supplied file path."""
        sha256 = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
