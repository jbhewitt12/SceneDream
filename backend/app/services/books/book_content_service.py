from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .base import BookContent
from .docx_loader import DocxBookLoader
from .epub_loader import EpubBookLoader
from .markdown_loader import MarkdownBookLoader
from .mobi_loader import MobiBookLoader, MobiExtractionError
from .text_loader import TextBookLoader


class BookContentServiceError(RuntimeError):
    """Raised when book content cannot be loaded."""


def _default_project_root_from_path(source_file: Path) -> Path:
    """Resolve the repository root across local and containerized layouts."""
    try:
        candidate = source_file.resolve().parents[4]
    except IndexError:
        return source_file.resolve().parent

    # In container images files live at /app/app/services/books/..., where
    # parents[4] resolves to / and /app is the intended project root.
    if candidate == Path("/"):
        try:
            return source_file.resolve().parents[3]
        except IndexError:
            return source_file.resolve().parent
    return candidate


@dataclass(slots=True)
class _CacheEntry:
    checksum: str
    parser_version: str
    content: BookContent


class BookContentService:
    """
    BookContentService provides normalized access to source documents.

    Usage:
        service = BookContentService()
        content = service.load_book("documents/my-book.docx")

        for chapter in content.chapters.values():
            print(f"Chapter {chapter.number}: {chapter.title}")
            print(f"  Paragraphs: {len(chapter.paragraphs)}")

    Features:
        - Auto-detects format (EPUB, MOBI, AZW, TXT, MD, DOCX) by extension
        - In-memory caching keyed by file path and checksum to avoid repeated I/O
        - Filters common front matter while preserving chapter numbering
        - Provides deterministic chapter and paragraph ordering (1-indexed)

    Backward Compatibility:
        Paragraph numbering matches the legacy SceneExtractor behavior so existing
        `scene_extractions` records remain valid. Chapters are numbered from 1 and the
        paragraph list for each chapter maps directly to the 1-indexed paragraph spans
        used throughout downstream services.

    Content path behavior:
        - `documents/` is the canonical content directory for new paths.
        - `books/` remains a legacy fallback so existing persisted paths still resolve.
    """

    DOCUMENTS_DIRNAME = "documents"
    LEGACY_BOOKS_DIRNAME = "books"

    def __init__(self, *, project_root: Path | None = None) -> None:
        self._epub_loader = EpubBookLoader()
        self._mobi_loader = MobiBookLoader()
        self._text_loader = TextBookLoader()
        self._markdown_loader = MarkdownBookLoader()
        self._docx_loader = DocxBookLoader()
        self._cache: dict[str, _CacheEntry] = {}
        self._project_root = project_root or _default_project_root_from_path(
            Path(__file__)
        )

    def load_book(self, path: str | Path, *, cache: bool = True) -> BookContent:
        """
        Load a book from the supplied path.

        Args:
            path: Absolute or relative path to a supported source document.
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
            elif suffix == ".txt":
                content = self._text_loader.load(resolved_path)
            elif suffix == ".md":
                content = self._markdown_loader.load(resolved_path)
            elif suffix == ".docx":
                content = self._docx_loader.load(resolved_path)
            else:
                raise BookContentServiceError(f"Unsupported format: {suffix}")
        except MobiExtractionError as exc:
            raise BookContentServiceError(str(exc)) from exc
        except ValueError as exc:
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

    def resolve_book_path(self, path: str | Path) -> Path:
        """Resolve a supplied source path with `documents/` + legacy fallback rules."""
        return self._resolve_path(path)

    def normalize_source_path(self, path: str | Path) -> str:
        """
        Normalize a source path for persistence.

        - Project-local paths are persisted relative to the repository root.
        - `books/...` is canonicalized to `documents/...` for new writes.
        - Non-project absolute paths are preserved as absolute.
        """
        candidate = Path(path).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else candidate
        relative_path: Path | None
        try:
            relative_path = resolved.relative_to(self._project_root)
        except ValueError:
            relative_path = None

        if relative_path is None and not candidate.is_absolute():
            relative_path = candidate

        if relative_path is None:
            return str(resolved)

        canonical_relative = self._canonicalize_relative_path(relative_path)
        return canonical_relative.as_posix()

    def _resolve_path(self, path: str | Path) -> Path:
        """Resolve paths against CWD/project root with documents/books compatibility."""
        p = Path(path).expanduser()
        candidates: list[Path] = []

        if p.is_absolute():
            candidates.append(p.resolve())
            try:
                relative_to_root = p.resolve().relative_to(self._project_root)
            except ValueError:
                relative_to_root = None
            if relative_to_root is not None:
                for relative_candidate in self._relative_path_candidates(
                    relative_to_root
                ):
                    candidate = (self._project_root / relative_candidate).resolve()
                    if candidate not in candidates:
                        candidates.append(candidate)
        else:
            cwd_candidate = (Path.cwd() / p).resolve()
            candidates.append(cwd_candidate)
            for relative_candidate in self._relative_path_candidates(p):
                candidate = (self._project_root / relative_candidate).resolve()
                if candidate not in candidates:
                    candidates.append(candidate)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    def _relative_path_candidates(self, relative_path: Path) -> list[Path]:
        normalized = self._normalize_relative_path(relative_path)
        if not normalized.parts:
            return [normalized]

        candidates: list[Path] = [normalized]
        head, tail = normalized.parts[0], normalized.parts[1:]
        tail_path = Path(*tail) if tail else Path()
        if head == self.DOCUMENTS_DIRNAME:
            candidates.append(Path(self.LEGACY_BOOKS_DIRNAME) / tail_path)
        elif head == self.LEGACY_BOOKS_DIRNAME:
            candidates.append(Path(self.DOCUMENTS_DIRNAME) / tail_path)
        else:
            candidates.append(Path(self.DOCUMENTS_DIRNAME) / normalized)
            candidates.append(Path(self.LEGACY_BOOKS_DIRNAME) / normalized)

        deduped: list[Path] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def _canonicalize_relative_path(self, relative_path: Path) -> Path:
        normalized = self._normalize_relative_path(relative_path)
        if not normalized.parts:
            return normalized

        head = normalized.parts[0]
        if head == self.LEGACY_BOOKS_DIRNAME:
            remainder = normalized.parts[1:]
            return Path(self.DOCUMENTS_DIRNAME, *remainder)
        return normalized

    @staticmethod
    def _normalize_relative_path(path: Path) -> Path:
        parts = [part for part in path.parts if part not in {"", "."}]
        return Path(*parts) if parts else Path()

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        """Compute the SHA256 checksum for the supplied file path."""
        sha256 = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
