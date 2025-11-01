# Unified Book Content Service Plan

## Context
- EPUB and MOBI ingestion logic now live inside `SceneExtractor`, which exposes private helpers and format-specific quirks.
- Upcoming pipelines (scene refinement, character tagging, audio dramatization) will need consistent read-only access to book structure and text.
- Re-implementing parsing per service risks format drift, duplicate code paths, and inconsistent filtering of front/back matter.
- Existing data model stores paragraph indices (`scene_paragraph_start`, `scene_paragraph_end`, `chunk_paragraph_start`, `chunk_paragraph_end`) in `scene_extractions` to link prompts/refinements back to source text.
- Downstream services (e.g. `backend/app/services/image_prompt_generation/image_prompt_generation_service.py:643-704`) rely on those indices plus the original `source_book_path` to rebuild context windows, so numbering must stay stable for already persisted scenes.

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
   - Preserve 1-based chapter numbering and relative paragraph ordering so that existing references in `scene_extractions` remain valid when other services fetch context.

## Existing Consumers & Compatibility
- `ImagePromptGenerationService._build_scene_context` (`backend/app/services/image_prompt_generation/image_prompt_generation_service.py:643-704`) loads chapters via `_load_book_context` and uses stored paragraph spans to assemble context windows for DALLE prompts. The new service must provide equivalent chapter lookups for both legacy EPUB entries and new MOBI-backed scenes.
- `ImagePromptGenerationService._load_book_context` (`backend/app/services/image_prompt_generation/image_prompt_generation_service.py:1022-1107`) currently re-parses the EPUB directly. Refactor will replace this with calls to `BookContentService`, but functional output (chapter numbers, titles, paragraph arrays) must remain unchanged.
- `SceneRankingService._build_prompt` (`backend/app/services/scene_ranking/scene_ranking_service.py:565-611`) embeds `scene_paragraph_span` and `chunk_paragraph_span` in the LLM prompt. Those spans are persisted in `scene_extractions` (`backend/models/scene_extraction.py:39-84`) and must stay correct when rehydrating context from the new service.
- Frontend prompt detail views (`frontend/src/api/imagePrompts.ts:1-86`) surface `context_window.paragraph_span`, `paragraphs_before`, and `paragraphs_after`. Any changes to data shape or numbering would ripple into the UI, so backwards compatibility is mandatory.
- `SceneExtractor._persist_chapter_scenes` (`backend/app/services/scene_extraction/scene_extraction.py:952-1041`) saves chunk/scene paragraph bounds and `chapter_source_name`. Migrating to `BookContentService` must preserve these values for previously extracted records, or provide a compatibility shim that maps old indices to the new representation.
- Stored `source_book_path` values are reused verbatim when building prompts (`SceneExtractor._persist_chapter_scenes` sets the string; `_build_scene_context` reads it). The new service must accept both absolute and repo-relative paths and handle legacy `.epub` entries alongside new `.mobi` ones without requiring data migration.

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
7. Verify backwards compatibility by re-running `_build_scene_context` against existing `scene_extractions` fixtures to ensure paragraph spans resolve identically (add regression tests that compare legacy `_load_book_context` output to the new service for a sample EPUB/MOBI pair).
