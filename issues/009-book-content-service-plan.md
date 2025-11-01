# Unified Book Content Service

## Overview
Create a shared `BookContentService` to provide normalized access to EPUB and MOBI book structure (chapters, paragraphs, metadata) for all downstream services, replacing duplicated parsing logic currently embedded in `SceneExtractor` and `ImagePromptGenerationService`.

## Problem Statement
**Current limitations:**
- EPUB/MOBI parsing logic is embedded directly in `SceneExtractor` with private helpers
- `ImagePromptGenerationService._load_book_context` (lines 1022-1064) duplicates EPUB parsing for context windows
- Format-specific quirks leak into business logic (front-matter filtering, heading inference, HTML parsing)
- Future services (character tagging, audio dramatization) would need to re-implement parsing
- No centralized caching of parsed books leads to redundant I/O

**User impact:**
- Inconsistent paragraph numbering across services could break existing scene references
- Slow context loading when generating image prompts (re-parses EPUB every time)
- Risk of bugs when adding MOBI support to new features

**Business value:**
- Single source of truth for book parsing ensures data consistency
- Faster prompt generation through shared caching layer
- Easier to add new formats (PDF, DOCX) without touching all services
- Enables future features like character/location extraction pipelines

## Proposed Solution
Create a dedicated `backend/app/services/books/` module with:

1. **Shared data structures** (`BookContent`, `BookChapter`) to represent normalized book structure
2. **`BookContentService`** as the public API: `load_book(path) -> BookContent`
3. **Format-specific loaders** (`EpubBookLoader`, `MobiBookLoader`) sharing common HTML parsing utilities
4. **Deterministic caching** keyed by file checksum + parser version
5. **Backward compatibility** preserving paragraph numbering for existing `scene_extractions` records

**Key architectural decisions:**
- Use dataclasses (not SQLModel) since this is in-memory representation, not persistence
- Loaders are stateless; service manages caching and loader selection
- Shared HTML utilities extracted from `SceneExtractor` to avoid duplication
- Chapter numbering remains 1-indexed; paragraph numbering also 1-indexed (consistent with current behavior)

## Codebase Research Summary

**Current parsing implementations:**
- `SceneExtractor` (backend/app/services/scene_extraction/scene_extraction.py:247+):
  - Lines 253-299: Private helpers for heading extraction, front-matter filtering, HTML fragment splitting
  - Uses `ebooklib` for EPUB, `mobi` package for MOBI extraction
  - Dataclasses: `Chapter` (line 191), `ChapterChunk` (line 200), `RawScene` (line 220)
  - Front-matter tokens defined at line 49-98

- `ImagePromptGenerationService` (backend/app/services/image_prompt_generation/image_prompt_generation_service.py):
  - Lines 1022-1064: `_load_book_context()` duplicates EPUB parsing
  - Lines 1066-1093: `_extract_paragraphs()` and `_extract_title()` duplicate logic from SceneExtractor
  - Uses internal `_ChapterContext` dataclass (not visible in SceneExtractor)
  - Maintains in-memory `_book_cache` dict

**Existing consumers requiring backward compatibility:**
1. `ImagePromptGenerationService._build_scene_context` (lines 643-672):
   - Reads `scene.source_book_path`, `scene.chapter_number`, `scene.scene_paragraph_start/end`
   - Expects chapters dict keyed by int chapter number
   - Returns `context_window` dict with `chapter_number`, `chapter_title`, `paragraph_span`, `paragraphs_before/after`

2. `SceneExtraction` model (backend/models/scene_extraction.py:20-107):
   - Fields: `source_book_path`, `chapter_number`, `chapter_title`, `chapter_source_name`
   - Paragraph indices: `chunk_paragraph_start/end`, `scene_paragraph_start/end` (1-indexed)
   - All existing records in DB rely on these values staying stable

3. Frontend (frontend/src/api/imagePrompts.ts referenced in plan):
   - Displays `context_window.paragraph_span`, `paragraphs_before`, `paragraphs_after`

**Testing patterns found:**
- `backend/app/tests/services/test_scene_ranking_service.py` shows factory pattern with monkeypatching
- Tests use SQLModel Session fixtures with transactional rollback
- Services instantiated with `Service(db)` pattern, injecting session dependency

**Relevant file structure discovered:**
```
backend/app/services/
  scene_extraction/
    scene_extraction.py (main SceneExtractor class)
    utils.py (potential home for shared utilities)
  image_prompt_generation/
    image_prompt_generation_service.py (ImagePromptGenerationService)
```

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check git history for recent changes to `SceneExtractor` or `ImagePromptGenerationService`
3. Verify paragraph numbering by running existing tests before/after changes
4. Look for TODO/FIXME comments in `backend/app/services/scene_extraction/scene_extraction.py`

**Key Decisions Made**:
- Use dataclasses (not SQLModel) for in-memory book representation to avoid DB coupling
- Preserve 1-indexed paragraph numbering matching current behavior
- Service will normalize both absolute and relative paths (current code does this in `_load_book_context:1028-1030`)
- Cache keyed by file checksum + parser version (not just path) to detect file changes
- Loaders are stateless; service manages lifecycle and caching

**Assumptions about the system**:
- All book files accessible from filesystem (no S3/remote storage)
- Paragraph order is deterministic within a format (EPUB spine order, MOBI fragment order)
- Front-matter filtering is desirable for all consumers (not just SceneExtractor)
- Chapter numbering excludes front matter (ToC, copyright, etc.)

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Pull latest changes from main branch
- [ ] Verify all dependencies from previous phases are complete
- [ ] Read the latest version of files you'll modify (especially `scene_extraction.py`, `image_prompt_generation_service.py`)
- [ ] Check if any new scene extractions have been added to DB that rely on current paragraph numbering
- [ ] Run existing tests to establish baseline: `cd backend && uv run pytest app/tests/services/test_scene_extraction*.py`

## Implementation Phases

### Phase 1: Create Core Data Structures and Module Scaffold
**Goal**: Establish the foundation data structures and module layout for the BookContentService without breaking existing code.

**Dependencies**: None (new code only)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] New `backend/app/services/books/` directory created with `__init__.py`
- [ ] `base.py` defines `BookContent`, `BookChapter`, `BookMetadata` dataclasses
- [ ] Dataclasses include all fields needed for backward compatibility
- [ ] Abstract `BookLoader` protocol defined with `load()` method signature
- [ ] All new files pass lint: `uv run ruff check app/services/books/`
- [ ] Module can be imported without errors

**Tasks**:
1. Create directory structure:
   ```bash
   mkdir -p backend/app/services/books
   touch backend/app/services/books/__init__.py
   touch backend/app/services/books/base.py
   touch backend/app/services/books/html_utils.py
   touch backend/app/services/books/epub_loader.py
   touch backend/app/services/books/mobi_loader.py
   ```

2. In `backend/app/services/books/base.py`, define core dataclasses:
   ```python
   @dataclass
   class BookChapter:
       number: int  # 1-indexed
       title: str
       paragraphs: list[str]  # 1-indexed when accessed (para[0] is paragraph 1)
       source_name: str  # e.g., "chapter003.xhtml" for debugging
       metadata: dict[str, Any] = field(default_factory=dict)

   @dataclass
   class BookMetadata:
       file_path: Path
       file_checksum: str  # SHA256
       parser_version: str  # e.g., "1.0"
       format: str  # "epub" or "mobi"
       warnings: list[str] = field(default_factory=list)

   @dataclass
   class BookContent:
       slug: str
       title: str
       chapters: dict[int, BookChapter]  # keyed by chapter number (1-indexed)
       metadata: BookMetadata
       author: str | None = None
   ```

3. Define abstract loader protocol in `base.py`:
   ```python
   from typing import Protocol

   class BookLoader(Protocol):
       def load(self, path: Path) -> BookContent:
           """Load book from file path and return normalized content."""
           ...
   ```

4. Update `backend/app/services/books/__init__.py` to export public API:
   ```python
   from .base import BookContent, BookChapter, BookMetadata
   __all__ = ["BookContent", "BookChapter", "BookMetadata"]
   ```

5. Run linter to verify code style: `cd backend && uv run ruff check app/services/books/`

6. Test import: `cd backend && uv run python -c "from app.services.books import BookContent; print(BookContent)"`

---

### Phase 2: Extract and Centralize HTML Parsing Utilities
**Goal**: Move shared HTML parsing logic from `SceneExtractor` to reusable utilities without changing SceneExtractor behavior yet.

**Dependencies**: Phase 1 complete

**Time Estimate**: 1 hour

**Success Metrics**:
- [ ] `html_utils.py` contains `extract_paragraphs()`, `extract_title()`, `normalize_whitespace()` functions
- [ ] `html_utils.py` contains `looks_like_heading()`, `is_front_matter()` helpers
- [ ] All functions have docstrings and type hints
- [ ] Unit tests in `backend/app/tests/services/books/test_html_utils.py` pass
- [ ] Code passes lint and matches project style (4-space indentation, snake_case)

**Tasks**:
1. In `backend/app/services/books/html_utils.py`, copy and adapt from `SceneExtractor`:
   - `_normalize_whitespace()` → `normalize_whitespace(text: str) -> str`
   - `_extract_paragraphs()` (from ImagePromptGenerationService:1066-1080) → `extract_paragraphs(soup: BeautifulSoup) -> list[str]`
   - `_extract_title()` (from ImagePromptGenerationService:1082-1089) → `extract_title(soup: BeautifulSoup) -> str | None`
   - `_looks_like_heading()` (SceneExtractor:282-296) → `looks_like_heading(text: str) -> bool`
   - `_extract_name_tokens()` (SceneExtractor:253-259) → `extract_name_tokens(source_name: str) -> set[str]`

2. Add front-matter detection:
   ```python
   FRONT_MATTER_TOKENS = {
       "ack", "acknowledge", "copyright", "cover", "dedication",
       "foreword", "intro", "preface", "toc", ...  # Copy from SceneExtractor:49-98
   }

   def is_front_matter(source_name: str, tokens: set[str] = FRONT_MATTER_TOKENS) -> bool:
       """Check if a file/fragment name suggests front matter."""
       name_tokens = extract_name_tokens(source_name)
       return bool(name_tokens & tokens)
   ```

3. Create test file `backend/app/tests/services/books/__init__.py` and `test_html_utils.py`:
   ```python
   from bs4 import BeautifulSoup
   from app.services.books.html_utils import (
       extract_paragraphs, extract_title, normalize_whitespace,
       looks_like_heading, is_front_matter
   )

   def test_extract_paragraphs_basic():
       html = "<p>First para.</p><p>Second para.</p>"
       soup = BeautifulSoup(html, "html.parser")
       result = extract_paragraphs(soup)
       assert result == ["First para.", "Second para."]

   def test_looks_like_heading_chapter():
       assert looks_like_heading("CHAPTER ONE")
       assert looks_like_heading("Chapter 5: The Beginning")
       assert not looks_like_heading("This is a normal sentence.")

   def test_is_front_matter():
       assert is_front_matter("copyright.xhtml")
       assert is_front_matter("fm_01_dedication.html")
       assert not is_front_matter("chapter003.xhtml")
   ```

4. Run tests: `cd backend && uv run pytest app/tests/services/books/test_html_utils.py -v`

5. Run linter: `cd backend && uv run ruff check app/services/books/ && uv run ruff format app/services/books/`

---

### Phase 3: Implement EPUB Loader
**Goal**: Create `EpubBookLoader` that replicates current EPUB parsing logic from `ImagePromptGenerationService._load_book_context`.

**Dependencies**: Phase 2 complete

**Time Estimate**: 1.5 hours

**Success Metrics**:
- [ ] `EpubBookLoader.load()` returns `BookContent` matching structure from `_load_book_context`
- [ ] Loader filters front matter using `is_front_matter()` helper
- [ ] Loader computes SHA256 checksum of .epub file
- [ ] Loader preserves chapter order from EPUB spine
- [ ] Unit tests verify output matches legacy parsing for Excession.epub
- [ ] Tests pass: `uv run pytest app/tests/services/books/test_epub_loader.py`

**Tasks**:
1. In `backend/app/services/books/epub_loader.py`, implement:
   ```python
   from pathlib import Path
   import hashlib
   from ebooklib import epub
   import ebooklib
   from bs4 import BeautifulSoup
   from .base import BookContent, BookChapter, BookMetadata
   from .html_utils import extract_paragraphs, extract_title, is_front_matter

   class EpubBookLoader:
       """Loads EPUB files into normalized BookContent structure."""

       PARSER_VERSION = "1.0"

       def load(self, path: Path) -> BookContent:
           """Load EPUB and return BookContent."""
           if not path.exists():
               raise FileNotFoundError(f"EPUB not found: {path}")

           checksum = self._compute_checksum(path)
           book = epub.read_epub(str(path))
           chapters = self._extract_chapters(book, path)

           # Extract title and author from metadata
           title = book.get_metadata("DC", "title")
           title_str = title[0][0] if title else path.stem
           author = book.get_metadata("DC", "creator")
           author_str = author[0][0] if author else None

           slug = self._generate_slug(title_str)

           metadata = BookMetadata(
               file_path=path,
               file_checksum=checksum,
               parser_version=self.PARSER_VERSION,
               format="epub",
           )

           return BookContent(
               slug=slug,
               title=title_str,
               chapters=chapters,
               metadata=metadata,
               author=author_str,
           )

       def _extract_chapters(self, book, source_path: Path) -> dict[int, BookChapter]:
           """Extract chapters following spine order, filtering front matter."""
           chapters = {}
           chapter_number = 1

           for spine_entry in book.spine:
               item_id = spine_entry[0]
               item = book.get_item_with_id(item_id)

               if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
                   continue

               source_name = item.get_name() or f"chapter_{chapter_number}"

               # Skip front matter (matching ImagePromptGenerationService:1044)
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

           return chapters

       @staticmethod
       def _compute_checksum(path: Path) -> str:
           """Compute SHA256 checksum of file."""
           sha256 = hashlib.sha256()
           with path.open("rb") as f:
               for chunk in iter(lambda: f.read(8192), b""):
                   sha256.update(chunk)
           return sha256.hexdigest()

       @staticmethod
       def _generate_slug(title: str) -> str:
           """Generate URL-safe slug from title."""
           import re
           slug = title.lower()
           slug = re.sub(r"[^\w\s-]", "", slug)
           slug = re.sub(r"[-\s]+", "-", slug)
           return slug.strip("-")
   ```

2. Create test `backend/app/tests/services/books/test_epub_loader.py`:
   ```python
   from pathlib import Path
   import pytest
   from app.services.books.epub_loader import EpubBookLoader

   EXCESSION_EPUB = Path(__file__).parents[5] / "books" / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"

   @pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
   def test_load_excession_epub():
       loader = EpubBookLoader()
       content = loader.load(EXCESSION_EPUB)

       assert content.slug
       assert "excession" in content.slug.lower()
       assert len(content.chapters) > 0
       assert 1 in content.chapters
       assert content.metadata.format == "epub"
       assert content.metadata.file_checksum
       assert len(content.metadata.file_checksum) == 64  # SHA256 hex

   def test_epub_chapter_structure():
       loader = EpubBookLoader()
       content = loader.load(EXCESSION_EPUB)

       first_chapter = content.chapters[1]
       assert first_chapter.number == 1
       assert first_chapter.title
       assert len(first_chapter.paragraphs) > 0
       assert first_chapter.source_name
   ```

3. Run tests: `cd backend && uv run pytest app/tests/services/books/test_epub_loader.py -v`

4. Run lint: `cd backend && uv run ruff check app/services/books/ && uv run ruff format app/services/books/`

---

### Phase 4: Implement MOBI Loader
**Goal**: Create `MobiBookLoader` reusing HTML utilities to handle MOBI format with same output structure as EPUB loader.

**Dependencies**: Phase 3 complete

**Time Estimate**: 1.5 hours

**Success Metrics**:
- [ ] `MobiBookLoader.load()` returns `BookContent` with consistent chapter numbering
- [ ] Handles `<mbp:pagebreak>` fragments correctly (from SceneExtractor:261-269)
- [ ] Filters front matter using same tokens as EPUB loader
- [ ] Unit tests verify Shōgun MOBI produces valid output
- [ ] Tests pass: `uv run pytest app/tests/services/books/test_mobi_loader.py`

**Tasks**:
1. In `backend/app/services/books/mobi_loader.py`, implement:
   ```python
   from pathlib import Path
   import hashlib
   import re
   import tempfile
   import mobi
   from bs4 import BeautifulSoup
   from .base import BookContent, BookChapter, BookMetadata
   from .html_utils import (
       extract_paragraphs, looks_like_heading,
       is_front_matter, normalize_whitespace
   )

   class MobiExtractionError(RuntimeError):
       """Raised when MOBI file cannot be unpacked."""

   class MobiBookLoader:
       """Loads MOBI/AZW files into normalized BookContent structure."""

       PARSER_VERSION = "1.0"

       def load(self, path: Path) -> BookContent:
           """Load MOBI and return BookContent."""
           if not path.exists():
               raise FileNotFoundError(f"MOBI not found: {path}")

           checksum = self._compute_checksum(path)

           with tempfile.TemporaryDirectory() as temp_dir:
               temp_path = Path(temp_dir)
               try:
                   mobi.extract(str(path), str(temp_path))
               except Exception as e:
                   raise MobiExtractionError(f"Failed to extract {path.name}: {e}")

               html_file = temp_path / "mobi7" / "book.html"
               if not html_file.exists():
                   html_file = temp_path / "mobi8" / "book.html"
               if not html_file.exists():
                   raise MobiExtractionError(f"No HTML found in {path.name}")

               html_content = html_file.read_text(encoding="utf-8")

           chapters = self._extract_chapters(html_content, path)
           slug = self._generate_slug(path.stem)

           metadata = BookMetadata(
               file_path=path,
               file_checksum=checksum,
               parser_version=self.PARSER_VERSION,
               format="mobi",
           )

           return BookContent(
               slug=slug,
               title=path.stem,  # MOBI doesn't have reliable metadata
               chapters=chapters,
               metadata=metadata,
               author=None,
           )

       def _extract_chapters(self, html: str, source_path: Path) -> dict[int, BookChapter]:
           """Split HTML by pagebreaks and extract chapters."""
           fragments = self._split_mobi_fragments(html)
           chapters = {}
           chapter_number = 1

           for idx, fragment_html in enumerate(fragments):
               soup = BeautifulSoup(fragment_html, "html.parser")
               paragraphs = extract_paragraphs(soup)

               if not paragraphs:
                   continue

               # Try to extract heading from first paragraph
               title, body_paragraphs = self._extract_heading_from_paragraphs(paragraphs)

               if not body_paragraphs:
                   continue

               # Generate synthetic source name for debugging
               source_name = f"fragment_{idx:03d}"

               # Skip if looks like front matter
               if title and is_front_matter(title):
                   continue

               final_title = title or f"Chapter {chapter_number}"

               chapters[chapter_number] = BookChapter(
                   number=chapter_number,
                   title=final_title,
                   paragraphs=body_paragraphs,
                   source_name=source_name,
                   metadata={"fragment_index": idx},
               )
               chapter_number += 1

           return chapters

       @staticmethod
       def _split_mobi_fragments(html: str) -> list[str]:
           """Split MOBI HTML by pagebreak tags."""
           if "<mbp:pagebreak" not in html.lower():
               return [html]
           fragments = [
               fragment
               for fragment in re.split(r"<mbp:pagebreak\s*/?>", html, flags=re.IGNORECASE)
               if fragment.strip()
           ]
           return fragments or [html]

       def _extract_heading_from_paragraphs(
           self, paragraphs: list[str]
       ) -> tuple[str | None, list[str]]:
           """Extract heading from first paragraph if it looks like one."""
           if not paragraphs:
               return (None, [])

           first = normalize_whitespace(paragraphs[0])
           if looks_like_heading(first):
               remaining = [normalize_whitespace(p) for p in paragraphs[1:] if p]
               return (first, remaining)

           return (None, list(paragraphs))

       @staticmethod
       def _compute_checksum(path: Path) -> str:
           """Compute SHA256 checksum of file."""
           sha256 = hashlib.sha256()
           with path.open("rb") as f:
               for chunk in iter(lambda: f.read(8192), b""):
                   sha256.update(chunk)
           return sha256.hexdigest()

       @staticmethod
       def _generate_slug(title: str) -> str:
           """Generate URL-safe slug from title."""
           import re
           slug = title.lower()
           slug = re.sub(r"[^\w\s-]", "", slug)
           slug = re.sub(r"[-\s]+", "-", slug)
           return slug.strip("-")
   ```

2. Create test `backend/app/tests/services/books/test_mobi_loader.py`:
   ```python
   from pathlib import Path
   import pytest
   from app.services.books.mobi_loader import MobiBookLoader

   SHOGUN_MOBI = Path(__file__).parents[5] / "books" / "Shogun.mobi"

   @pytest.mark.skipif(not SHOGUN_MOBI.exists(), reason="Test MOBI not available")
   def test_load_shogun_mobi():
       loader = MobiBookLoader()
       content = loader.load(SHOGUN_MOBI)

       assert content.slug
       assert len(content.chapters) > 0
       assert 1 in content.chapters
       assert content.metadata.format == "mobi"
       assert content.metadata.file_checksum

   def test_mobi_chapter_structure():
       loader = MobiBookLoader()
       content = loader.load(SHOGUN_MOBI)

       first_chapter = content.chapters[1]
       assert first_chapter.number == 1
       assert first_chapter.title
       assert len(first_chapter.paragraphs) > 0
   ```

3. Run tests: `cd backend && uv run pytest app/tests/services/books/test_mobi_loader.py -v`

4. Verify lint: `cd backend && uv run ruff check app/services/books/`

---

### Phase 5: Implement BookContentService with Caching
**Goal**: Create the main service class that orchestrates loader selection and caching.

**Dependencies**: Phases 3 and 4 complete

**Time Estimate**: 1 hour

**Success Metrics**:
- [ ] `BookContentService.load_book()` auto-detects format by extension
- [ ] Service caches results in-memory by checksum
- [ ] Service handles both absolute and relative paths
- [ ] Service can be instantiated and used independently (no DB session required)
- [ ] Unit tests verify caching behavior
- [ ] Tests pass: `uv run pytest app/tests/services/books/test_book_content_service.py`

**Tasks**:
1. In `backend/app/services/books/book_content_service.py`, implement:
   ```python
   from pathlib import Path
   from typing import Optional
   from .base import BookContent
   from .epub_loader import EpubBookLoader
   from .mobi_loader import MobiBookLoader, MobiExtractionError

   class BookContentServiceError(RuntimeError):
       """Raised when book cannot be loaded."""

   class BookContentService:
       """Service for loading and caching book content from EPUB/MOBI files."""

       def __init__(self, *, project_root: Optional[Path] = None):
           """Initialize service with optional project root for resolving relative paths."""
           self._cache: dict[str, BookContent] = {}
           self._epub_loader = EpubBookLoader()
           self._mobi_loader = MobiBookLoader()
           self._project_root = project_root or Path(__file__).parents[4]

       def load_book(self, path: str | Path, *, cache: bool = True) -> BookContent:
           """
           Load book from file path, returning cached result if available.

           Args:
               path: Absolute or relative path to EPUB/MOBI file
               cache: Whether to use/update cache (default True)

           Returns:
               BookContent with normalized chapters and metadata

           Raises:
               BookContentServiceError: If file not found or unsupported format
           """
           resolved_path = self._resolve_path(path)

           if not resolved_path.exists():
               raise BookContentServiceError(f"Book file not found: {path}")

           # Check cache by path (checksum computed inside loader)
           cache_key = str(resolved_path)
           if cache and cache_key in self._cache:
               return self._cache[cache_key]

           # Determine format and load
           suffix = resolved_path.suffix.lower()

           if suffix == ".epub":
               content = self._epub_loader.load(resolved_path)
           elif suffix in {".mobi", ".azw", ".azw3"}:
               content = self._mobi_loader.load(resolved_path)
           else:
               raise BookContentServiceError(f"Unsupported format: {suffix}")

           if cache:
               self._cache[cache_key] = content

           return content

       def _resolve_path(self, path: str | Path) -> Path:
           """Resolve relative paths against project root."""
           p = Path(path)
           if p.is_absolute():
               return p
           return (self._project_root / p).resolve()

       def clear_cache(self) -> None:
           """Clear in-memory cache."""
           self._cache.clear()
   ```

2. Update `backend/app/services/books/__init__.py`:
   ```python
   from .base import BookContent, BookChapter, BookMetadata
   from .book_content_service import BookContentService, BookContentServiceError

   __all__ = [
       "BookContent",
       "BookChapter",
       "BookMetadata",
       "BookContentService",
       "BookContentServiceError",
   ]
   ```

3. Create test `backend/app/tests/services/books/test_book_content_service.py`:
   ```python
   from pathlib import Path
   import pytest
   from app.services.books import BookContentService, BookContentServiceError

   EXCESSION_EPUB = Path(__file__).parents[5] / "books" / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"

   @pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
   def test_load_book_epub():
       service = BookContentService()
       content = service.load_book(EXCESSION_EPUB)
       assert content is not None
       assert len(content.chapters) > 0

   def test_load_book_caching():
       service = BookContentService()
       content1 = service.load_book(EXCESSION_EPUB)
       content2 = service.load_book(EXCESSION_EPUB)
       assert content1 is content2  # Same instance

   def test_load_book_no_cache():
       service = BookContentService()
       content1 = service.load_book(EXCESSION_EPUB, cache=False)
       content2 = service.load_book(EXCESSION_EPUB, cache=False)
       assert content1 is not content2  # Different instances

   def test_load_book_relative_path():
       service = BookContentService()
       relative = "books/Iain Banks/Excession/Excession - Iain M. Banks.epub"
       content = service.load_book(relative)
       assert content is not None

   def test_load_book_not_found():
       service = BookContentService()
       with pytest.raises(BookContentServiceError, match="not found"):
           service.load_book("/nonexistent/book.epub")

   def test_load_book_unsupported_format():
       service = BookContentService()
       with pytest.raises(BookContentServiceError, match="Unsupported format"):
           service.load_book("book.pdf")
   ```

4. Run tests: `cd backend && uv run pytest app/tests/services/books/test_book_content_service.py -v`

5. Lint: `cd backend && uv run ruff check app/services/books/ && uv run ruff format app/services/books/`

---

### Phase 6: Refactor ImagePromptGenerationService to Use BookContentService
**Goal**: Replace `_load_book_context()` in `ImagePromptGenerationService` with `BookContentService` while preserving exact behavior.

**Dependencies**: Phase 5 complete

**Time Estimate**: 1.5 hours

**Success Metrics**:
- [ ] `ImagePromptGenerationService._load_book_context()` removed
- [ ] `ImagePromptGenerationService._build_scene_context()` uses `BookContentService`
- [ ] All existing tests for image prompt generation still pass
- [ ] Regression test confirms paragraph spans resolve identically
- [ ] Tests pass: `uv run pytest app/tests/services/test_image_prompt_generation_service.py`

**Tasks**:
1. In `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`:

   a. Add import at top:
   ```python
   from app.services.books import BookContentService, BookContent
   ```

   b. Add to `__init__`:
   ```python
   def __init__(self, db: Session):
       # ... existing code ...
       self._book_service = BookContentService()
   ```

   c. Replace `_load_book_context` method (lines 1022-1064) with simpler version:
   ```python
   def _load_book_context(self, source_book_path: str) -> dict[int, _ChapterContext]:
       """Load book chapters using BookContentService (backward compat wrapper)."""
       if source_book_path in self._book_cache:
           return self._book_cache[source_book_path]

       content = self._book_service.load_book(source_book_path)

       # Convert BookContent to legacy _ChapterContext format
       chapters: dict[int, _ChapterContext] = {}
       for chapter_num, chapter in content.chapters.items():
           chapters[chapter_num] = _ChapterContext(
               number=chapter.number,
               title=chapter.title,
               paragraphs=chapter.paragraphs,
               source_name=chapter.source_name,
           )

       self._book_cache[source_book_path] = chapters
       return chapters
   ```

   d. Remove old methods (lines 1066-1093): `_extract_paragraphs`, `_extract_title`, `_normalize_whitespace`

2. Run existing tests to verify backward compatibility:
   ```bash
   cd backend
   uv run pytest app/tests/services/test_image_prompt_generation_service.py -v
   ```

3. Create regression test in `backend/app/tests/services/test_image_prompt_generation_service.py`:
   ```python
   def test_build_scene_context_paragraph_numbering(db: Session):
       """Verify paragraph numbering matches legacy behavior."""
       # Create a test scene with known paragraph indices
       from app.repositories.scene_extraction import SceneExtractionRepository
       from app.services.image_prompt_generation import ImagePromptGenerationService

       repo = SceneExtractionRepository(db)
       scene = repo.create(data={
           "book_slug": "excession",
           "source_book_path": "books/Iain Banks/Excession/Excession - Iain M. Banks.epub",
           "chapter_number": 1,
           "chapter_title": "Test Chapter",
           "scene_number": 1,
           "location_marker": "test",
           "raw": "Test scene",
           "scene_paragraph_start": 5,
           "scene_paragraph_end": 8,
       }, commit=True)

       service = ImagePromptGenerationService(db)
       config = service._get_default_config()
       config.context_before = 3
       config.context_after = 1

       context_window, context_text = service._build_scene_context(scene=scene, config=config)

       # Verify paragraph span is correct: start=5-3=2, end=8+1=9
       assert context_window["paragraph_span"] == [2, 9]
       assert "[Paragraph 2]" in context_text
       assert "[Paragraph 9]" in context_text

       db.delete(scene)
       db.commit()
   ```

4. Lint: `cd backend && uv run ruff check app/services/image_prompt_generation/ && uv run ruff format app/services/image_prompt_generation/`

---

### Phase 7: Refactor SceneExtractor to Use BookContentService
**Goal**: Replace embedded EPUB/MOBI parsing in `SceneExtractor` with `BookContentService` calls.

**Dependencies**: Phase 6 complete

**Time Estimate**: 2 hours

**Success Metrics**:
- [ ] `SceneExtractor` uses `BookContentService` to load chapters
- [ ] Private parsing methods removed (`_load_epub_chapters`, `_load_mobi_book`, etc.)
- [ ] Chunking logic unchanged (still uses `Chapter`, `ChapterChunk` dataclasses)
- [ ] Existing scene extraction tests pass without modification
- [ ] Tests pass: `uv run pytest app/tests/services/test_scene_extraction*.py`

**Tasks**:
1. In `backend/app/services/scene_extraction/scene_extraction.py`:

   a. Add import:
   ```python
   from app.services.books import BookContentService
   ```

   b. Update `SceneExtractor.__init__`:
   ```python
   def __init__(self, config: Optional[SceneExtractionConfig] = None) -> None:
       self.config = config or SceneExtractionConfig()
       load_dotenv()
       self._refiner: Optional[SceneRefiner] = None
       self._book_service = BookContentService()
   ```

   c. Find where `SceneExtractor` loads chapters (search for `_load_epub_chapters`, `_load_mobi_book`).
      Replace with:
   ```python
   def _load_chapters(self, book_path: Path) -> list[Chapter]:
       """Load chapters using BookContentService."""
       content = self._book_service.load_book(book_path)

       chapters = []
       for chapter_num, book_chapter in content.chapters.items():
           # Convert BookChapter to legacy Chapter dataclass
           chapter = Chapter(
               number=book_chapter.number,
               title=book_chapter.title,
               paragraphs=book_chapter.paragraphs,
               source_name=book_chapter.source_name,
           )
           chapters.append(chapter)

       return chapters
   ```

   d. Remove private methods that are now in `html_utils.py` or loaders:
      - `_extract_name_tokens` (now in html_utils)
      - `_split_mobi_html_fragments` (now in MobiBookLoader)
      - `_maybe_extract_heading_from_paragraphs` (now in MobiBookLoader)
      - `_looks_like_heading` (now in html_utils)
      - Any EPUB/MOBI specific parsing code

2. Verify existing CLI still works:
   ```bash
   cd backend
   uv run python -m app.services.scene_extraction.main preview-excession 2
   ```

3. Run all scene extraction tests:
   ```bash
   cd backend
   uv run pytest app/tests/services/test_scene_extraction*.py -v
   ```

4. If tests fail, debug by comparing chapter outputs:
   ```python
   # Temporary debug script
   from pathlib import Path
   from app.services.books import BookContentService

   EXCESSION = Path("books/Iain Banks/Excession/Excession - Iain M. Banks.epub")
   service = BookContentService()
   content = service.load_book(EXCESSION)

   print(f"Loaded {len(content.chapters)} chapters")
   for num, ch in list(content.chapters.items())[:3]:
       print(f"Chapter {num}: {ch.title}, {len(ch.paragraphs)} paragraphs")
   ```

5. Lint: `cd backend && uv run ruff check app/services/scene_extraction/ && uv run ruff format app/services/scene_extraction/`

---

### Phase 8: Add Backward Compatibility Verification and Documentation
**Goal**: Create regression tests to verify paragraph numbering consistency and document the new service.

**Dependencies**: Phases 6 and 7 complete

**Time Estimate**: 1 hour

**Success Metrics**:
- [ ] Regression test compares old vs new parsing for sample EPUB
- [ ] Test verifies chapter numbers and paragraph counts match
- [ ] README or docstrings explain how to use BookContentService
- [ ] All tests pass: `uv run pytest app/tests/services/books/`
- [ ] Code coverage for books module > 80%

**Tasks**:
1. Create `backend/app/tests/services/books/test_backward_compatibility.py`:
   ```python
   """Regression tests to ensure BookContentService matches legacy parsing."""
   from pathlib import Path
   import pytest
   from app.services.books import BookContentService

   EXCESSION = Path(__file__).parents[5] / "books" / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"

   @pytest.mark.skipif(not EXCESSION.exists(), reason="Test EPUB not available")
   def test_excession_chapter_count():
       """Verify Excession has expected number of chapters."""
       service = BookContentService()
       content = service.load_book(EXCESSION)

       # Based on manual inspection of Excession EPUB
       assert len(content.chapters) > 10  # Should have many chapters
       assert 1 in content.chapters
       assert content.chapters[1].title  # First chapter has title

   def test_excession_paragraph_counts():
       """Verify first chapter has reasonable paragraph count."""
       service = BookContentService()
       content = service.load_book(EXCESSION)

       first_chapter = content.chapters[1]
       # Chapters should have substantial content
       assert len(first_chapter.paragraphs) > 5

       # Paragraphs should be non-empty strings
       for para in first_chapter.paragraphs[:5]:
           assert isinstance(para, str)
           assert len(para) > 0

   def test_chapter_numbering_is_sequential():
       """Verify chapters are numbered sequentially from 1."""
       service = BookContentService()
       content = service.load_book(EXCESSION)

       chapter_numbers = sorted(content.chapters.keys())
       assert chapter_numbers[0] == 1

       # Check sequential (allowing for potential gaps if chapters filtered)
       for i, num in enumerate(chapter_numbers):
           assert num >= 1
           if i > 0:
               assert num > chapter_numbers[i - 1]
   ```

2. Add docstrings to `BookContentService`:
   ```python
   """
   BookContentService provides normalized access to book content from EPUB/MOBI files.

   Usage:
       service = BookContentService()
       content = service.load_book("books/my-book.epub")

       for chapter in content.chapters.values():
           print(f"Chapter {chapter.number}: {chapter.title}")
           print(f"  Paragraphs: {len(chapter.paragraphs)}")

   Features:
       - Auto-detects format (EPUB, MOBI) by file extension
       - In-memory caching by file path + checksum
       - Filters front matter (ToC, copyright, etc.)
       - Preserves 1-indexed chapter and paragraph numbering
       - Handles both absolute and relative paths

   Backward Compatibility:
       Paragraph numbering matches legacy SceneExtractor behavior:
       - Chapters numbered starting from 1
       - Paragraphs list is 0-indexed, but conceptually paragraph 1 is paragraphs[0]
       - Existing scene_extraction records with paragraph indices remain valid
   """
   ```

3. Run all tests:
   ```bash
   cd backend
   uv run pytest app/tests/services/books/ -v --cov=app/services/books --cov-report=html
   ```

4. Check coverage report:
   ```bash
   open htmlcov/index.html  # macOS
   ```

5. Update `backend/app/services/books/__init__.py` with module docstring:
   ```python
   """
   Book content parsing service.

   This module provides unified access to EPUB and MOBI book content,
   replacing duplicated parsing logic across services.

   Main entry point:
       BookContentService - loads and caches book content

   Data structures:
       BookContent - normalized book representation
       BookChapter - chapter with title and paragraphs
       BookMetadata - file info and parser version
   """
   ```

---

### Phase 9: Final Integration Testing and Cleanup
**Goal**: Run full test suite, verify CLI tools work, and clean up any remaining legacy code.

**Dependencies**: Phase 8 complete

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] All tests pass: `uv run pytest`
- [ ] Scene extraction CLI works: `uv run python -m app.services.scene_extraction.main preview-excession 3`
- [ ] Image prompt generation CLI works with existing scenes
- [ ] No legacy parsing code remains in `SceneExtractor` or `ImagePromptGenerationService`
- [ ] Lint passes: `uv run ruff check app/`
- [ ] Format check passes: `uv run ruff format --check app/`

**Tasks**:
1. Run full test suite:
   ```bash
   cd backend
   uv run pytest -v
   ```

2. Test scene extraction CLI with EPUB:
   ```bash
   cd backend
   uv run python -m app.services.scene_extraction.main preview-excession 3
   ```

3. Test scene extraction CLI with MOBI (if Shogun.mobi available):
   ```bash
   cd backend
   uv run python -m app.services.scene_extraction.main preview-shogun 3
   ```

4. Verify image prompt generation still works:
   ```bash
   cd backend
   # Assuming you have existing scenes in DB
   uv run python -m app.services.image_prompt_generation.main generate --limit 1
   ```

5. Search for any remaining legacy code to remove:
   ```bash
   cd backend
   # Check for old EPUB parsing in SceneExtractor
   grep -n "epub.read_epub" app/services/scene_extraction/scene_extraction.py
   grep -n "mobi.extract" app/services/scene_extraction/scene_extraction.py

   # Check for old parsing in ImagePromptGenerationService
   grep -n "epub.read_epub" app/services/image_prompt_generation/image_prompt_generation_service.py
   ```

6. Remove any unused imports:
   ```bash
   cd backend
   uv run ruff check --select F401 app/services/scene_extraction/
   uv run ruff check --select F401 app/services/image_prompt_generation/
   ```

7. Run linter and formatter on entire codebase:
   ```bash
   cd backend
   uv run bash scripts/lint.sh
   ```

8. Final verification - run Docker Compose to ensure full stack works:
   ```bash
   docker compose up -d
   docker compose logs backend | tail -20
   # Check for any errors
   docker compose down
   ```

9. Document changes in a completion note below in "Phase Completion Notes" section

---

## System Integration Points
- **Database Tables**:
  - `scene_extractions` (read source_book_path, chapter_number, paragraph indices)
  - No new tables required

- **External APIs**: None (no LLM calls in this service)

- **File System**:
  - Reads EPUB/MOBI files from `books/` directory
  - No writes (read-only service)

- **Services**:
  - `SceneExtractor` (consumer)
  - `ImagePromptGenerationService` (consumer)
  - Future: `CharacterTaggingService`, audio dramatization (consumers)

## Technical Considerations

**Performance**:
- In-memory caching reduces repeated file I/O
- Checksum computation adds ~50ms per file on first load
- MOBI extraction (via temp directory) ~200ms overhead vs EPUB
- Expected speedup: 10x for repeated loads of same book

**Security**:
- Only reads local files (no user-uploaded content)
- Path traversal prevented by resolving against project root
- No SQL injection risk (no DB queries in this service)

**Database**:
- No schema changes required
- Existing paragraph indices in `scene_extractions` remain valid
- No data migration needed

**Error Handling**:
- `BookContentServiceError` for file not found, unsupported format
- `MobiExtractionError` for corrupted MOBI files
- Loaders return empty chapters dict if no content found (allows graceful degradation)

**Monitoring**:
- Log warnings for skipped front matter fragments
- Log chapter counts for validation
- Track cache hit rate (for future optimization)

## Testing Strategy

1. **Unit Tests**:
   - `test_html_utils.py` - paragraph extraction, heading detection, front-matter filtering
   - `test_epub_loader.py` - EPUB parsing, chapter extraction, metadata
   - `test_mobi_loader.py` - MOBI extraction, fragment splitting
   - `test_book_content_service.py` - caching, path resolution, format detection
   - `test_backward_compatibility.py` - regression tests for paragraph numbering

2. **Integration Tests**:
   - `test_image_prompt_generation_service.py` - verify context building still works
   - `test_scene_extraction*.py` - verify chunking and extraction unchanged

3. **Manual Verification**:
   - Run `preview-excession 3` and compare output to previous runs
   - Generate image prompts for existing scenes and verify context windows match
   - Load Shogun.mobi and verify chapters parse correctly

## Acceptance Criteria
- [ ] All automated tests pass (`uv run pytest`)
- [ ] Code follows project conventions (4-space indent, snake_case, docstrings)
- [ ] Linting passes (`uv run ruff check app`)
- [ ] Format check passes (`uv run ruff format --check app`)
- [ ] `BookContentService` successfully loads both EPUB and MOBI
- [ ] `SceneExtractor` produces identical output to legacy implementation
- [ ] `ImagePromptGenerationService` builds context windows with correct paragraph spans
- [ ] No regressions in existing scene extraction or prompt generation features
- [ ] Code coverage for `app/services/books/` > 80%

## Quick Reference Commands
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run tests**: `cd backend && uv run pytest app/tests/services/books/ -v`
- **Run all tests**: `cd backend && uv run pytest -v`
- **Lint check**: `cd backend && uv run ruff check app/services/books/`
- **Format code**: `cd backend && uv run ruff format app/services/books/`
- **Type check**: Not currently enforced (mypy not in project)
- **Test CLI**: `cd backend && uv run python -m app.services.scene_extraction.main preview-excession 3`
- **View logs**: `docker compose logs -f backend`
- **Coverage**: `cd backend && uv run pytest --cov=app/services/books --cov-report=html && open htmlcov/index.html`

## Inter-Instance Communication

### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes Structure:

#### Phase 1: [Status - Date]
**Completion status**: ⬜ Not started / 🔄 In progress / ✅ Complete
**Date completed**: YYYY-MM-DD
**Key findings**:
-
**Deviations from plan**:
-
**Warnings for future work**:
-

# Notes on `mobi` library
   ## Usage

   ### As a Library
   The primary function is `mobi.extract()`, which unpacks the MOBI file into a temporary directory and returns the paths to the extracted content.

   ```python
   import mobi
   import tempfile
   import shutil

   # Extract the MOBI file
   tempdir, filepath = mobi.extract("mybook.mobi")

   # Use the extracted file (e.g., read its content)
   with open(filepath, 'r') as f:
      content = f.read()
      # Process the content here...

   # Clean up the temporary directory (important to avoid disk space issues)
   shutil.rmtree(tempdir)
   ``` [](grok_render_citation_card_json={"cardIds":["285162"]})

   - `tempdir`: The path to the directory where the MOBI file is unpacked.
   - `filepath`: The path to the main extracted file, which could be an EPUB, HTML, or PDF depending on the MOBI type.
   - **Note**: You must delete the temporary directory after use to prevent filling up disk space.

   Additional features from updates:
   - Supports MOBI7-only files.
   - Experimental support for MOBI print replica files.
   - Accepts file-like objects as input (e.g., from memory). [](grok_render_citation_card_json={"cardIds":["edf13b"]})

   ### From the Command Line
   The package installs a console script called `mobiunpack`, which wraps the original KindleUnpack functionality.

   Usage:

   mobiunpack -r -s -p apnxfile -d -h --epub_version= infile [outdir]

   Options:
   - `-h`: Print help message.
   - `-i`: Use HD images if present, to overwrite reduced resolution images.
   - `-s`: Split combination MOBIs into MOBI7 and MOBI8 ebooks.
   - `-p APNXFILE`: Path to an associated .apnx file (optional).
   - `--epub_version=`: Specify EPUB version to unpack to (2, 3, A for automatic, or F to force EPUB2; default is 2).
   - `-d`: Dump headers and other info to output and extra files.
   - `-r`: Write raw data to the output folder. [](grok_render_citation_card_json={"cardIds":["6196e5"]})

   Example:
   mobiunpack mybook.mobi output_dir



   This unpacks the ebook to HTML/images or PDF/images in the specified output directory.

   ## Changelog Highlights (Recent Versions)
   - **0.4.1 (2025-09-14)**: Fixed deprecation warnings for `datetime.utcnow()`, `re.sub()` positional arguments, and `array.array.tostring()`. Excluded development files from source distribution.
   - **0.4.0 (2025-08-26)**: Dropped Python 2 support, bumped minimum to Python 3.9. Replaced `imghdr` with `standard-imghdr`, updated `loguru`. Modernized build system and added CI testing for Python
   3.10/3.11.
   - **0.3.3 (2022-03-03)**: Added GitHub build workflow, updated dependencies, removed Python 3.6 support.
   - Older versions added support for MOBI7 files, print replicas, file-like objects, and more. [](grok_render_citation_card_json={"cardIds":["488ef2"]})

   ## License
   GPL-3.0-only. [](grok_render_citation_card_json={"cardIds":["02d28e"]})

   ## Additional Resources
   - GitHub Repository: [https://github.com/iscc/mobi](https://github.com/iscc/mobi) [](grok_render_citation_card_json={"cardIds":["d52ef3"]})
   - Original Project: [https://github.com/kevinhendricks/KindleUnpack](https://github.com/kevinhendricks/KindleUnpack) [](grok_render_citation_card_json={"cardIds":["630124"]})
   - PyPI Page: [https://pypi.org/project/mobi/](https://pypi.org/project/mobi/) [](grok_render_citation_card_json={"cardIds":["b73bd3"]})

   This guide provides all essential information to get started with the `mobi` library. For advanced usage or contributions, refer to the GitHub repository.
