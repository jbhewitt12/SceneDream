# Unified Book Content Service Plan

## Context
- EPUB and MOBI ingestion logic now live inside `SceneExtractor`, which exposes private helpers and format-specific quirks.
- Upcoming pipelines (scene refinement, character tagging, audio dramatization) will need consistent read-only access to book structure and text.
- Re-implementing parsing per service risks format drift, duplicate code paths, and inconsistent filtering of front/back matter.

## Objectives
- Provide a single, well-tested API to retrieve normalized book content (metadata, chapters, paragraphs) regardless of original container.
- Decouple file parsing from downstream services so they consume data via a shared abstraction rather than poking at filesystem assets.
- Enable caching and memoization of parsed books to avoid repeated MOBI extraction and HTML parsing.
- Preserve existing scene extraction behaviour while paving the way for additional consumers.

## Proposed Solution
1. **Introduce shared data structures**
   - `BookContent` (`slug`, `title`, optional `author`, checksum/hash, `chapters`).
   - `BookChapter` (sequence-preserving number, title, source identifier, paragraphs, optional metadata like `start_file`, `raw_fragment_id`).
   - `Paragraph` wrapper if we later need offsets; start simple with plain strings plus derived indices.
2. **Create `BookContentService`**
   - Public entry point `load_book(path | slug, *, cache=True) -> BookContent`.
   - Internally delegates to format-specific loaders (`EpubBookLoader`, `MobiBookLoader`) that share helpers for HTML parsing, front-matter filtering, heading inference, etc.
   - Uses deterministic caching (in-memory + optional on-disk JSON) keyed by file checksum + parser version to speed up re-reads.
3. **Refactor existing code**
   - Update `SceneExtractor` to request a `BookContent` instance instead of walking EPUB/MOBI files directly.
   - Keep chunking/LLM prompting logic unchanged; only replace chapter acquisition + paragraph lists with the shared structures.
   - Provide transitional APIs so other services (e.g., future `CharacterTaggingService`) can hydrate scenes from the same `BookContent`.
4. **Surface diagnostics & metadata**
   - Capture parsing warnings (skipped fragments, empty chapters) in `BookContent.metadata` for observability.
   - Expose helper utilities to compute stable chapter hashes for deduplication and integration tests.

## Architecture Outline
- `backend/app/services/books/base.py`: shared dataclasses, abstract loader contract, cache utilities.
- `backend/app/services/books/epub_loader.py` + `mobi_loader.py`: format-specific readers invoking shared HTML parsers.
- `backend/app/services/books/html_utils.py`: normalized soup parsing (`_split_fragments`, `_extract_paragraphs`, heading heuristics) migrated from `SceneExtractor`.
- `BookContentService` orchestrates loader selection, caching, and metadata hydration.
- `SceneExtractor` injects the service (constructor dependency or lazy singleton) and iterates over returned chapters.

## Data & Caching Considerations
- File checksum: SHA256 of source file (or zipped contents) stored alongside parser version to bust stale cache entries.
- Optional JSON cache stored under `backend/.cache/books/<slug>/<checksum>.json` for quick reloads during dev.
- Serialization ensures paragraph ordering preserved; allow toggling caches via env/config to simplify automated tests.

## Operational Safeguards
- Unit tests for loaders covering representative EPUB + MOBI fixtures (including Shōgun MOBI regression).
- Golden-file snapshots for first chapter paragraphs to detect parser regressions.
- Logging hooks to record skipped fragments/front matter for monitoring.
- Backwards compatibility: flag to fall back to legacy parsing if new service raises.

## Next Actions
1. Scaffold `BookContent` dataclasses and loader interfaces.
2. Extract shared HTML parsing helpers from `SceneExtractor` into the new module.
3. Implement EPUB loader, reusing existing logic and ensuring parity via regression tests.
4. Port MOBI loader to use shared helpers; add tests verifying Shōgun MOBI output matches EPUB structure.
5. Wire `SceneExtractor` through `BookContentService` and remove private format-specific readers.
6. Add CLI script updates (e.g., `mobi_preview.py`) to consume `BookContentService` for validation.
