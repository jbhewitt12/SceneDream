# Add Missing Test Coverage

## Overview
Add unit tests for all untested routes, services, and repositories identified in the coding standards audit. Also fix a duplicated fixture in `test_image_prompt_repository.py`.

## Problem Statement
The CONTRIBUTING.md coding standards require tests for every behavior change, with services tested in `backend/app/tests/services/`, routes in `backend/app/tests/api/routes/`, and repositories in `backend/app/tests/repositories/`. The audit found 3 route files, 2 service files, and 3 repository files with no dedicated tests. This creates regression risk and makes refactoring unsafe.

## Proposed Solution
Create test files for each untested module following the established patterns: `test_scene_ranking_service.py` for services, `test_pipeline_runs.py` for routes, and `test_core_domain_repositories.py` for repositories. All external API calls mocked with `monkeypatch`. Test all endpoints/methods, not just critical paths.

## Codebase Research Summary

### Reference test patterns:
- **Service tests** (`test_scene_ranking_service.py`): Use `scene_factory`, mock LLM APIs via `monkeypatch.setattr(gemini_api, "json_output", fake_fn)`, call async methods with `asyncio.run()`, verify DB persistence
- **Route tests** (`test_pipeline_runs.py`): Use `TestClient(app)`, monkeypatch route-level helpers, verify HTTP status codes and response structure, use `AsyncMock` for background tasks
- **Repository tests** (`test_core_domain_repositories.py`): Create records via repository, test CRUD + filtering + querying, explicit cleanup via `db.delete()` + `db.commit()`
- **Shared fixtures** (`conftest.py`): `scene_factory()` with `**overrides` and FK-safe cleanup, `prompt_factory()` linked to scene, `db` session fixture

### Untested modules:
- **Routes**: `image_prompts.py` (6 endpoints), `scene_extractions.py` (3 endpoints), `scene_rankings.py` (3 endpoints)
- **Services**: `scene_extraction.py` (extract_book, extract_preview), `scene_refinement.py` (refine)
- **Repositories**: `SceneExtractionRepository` (11 methods), `SceneRankingRepository` (8 methods), `ImageGenerationBatchRepository` (5 methods)

### Duplicated fixture:
- `test_image_prompt_repository.py` lines 11-45 define a `scene` fixture that duplicates `scene_factory` from conftest

## Key Decisions
- **Service tests for scene_extraction.py are blocked by issue 020** (boundary refactor). Tests will be written against the refactored constructor-injection API, not the current code.
- **All endpoints tested**: Even simple list/get routes get tests to catch regressions in query params, filters, pagination, and error handling.
- **Mocking strategy**: `monkeypatch.setattr` for all external calls (LLM APIs, file I/O). No live service calls in unit tests.

## Implementation Plan

### Phase 1: Route tests — scene_extractions
**Goal**: Full test coverage for all 3 scene extraction endpoints.

**Tasks**:
- Create `backend/app/tests/api/routes/test_scene_extractions.py`
- Test `GET /scene-extractions/` — pagination, filtering by book_slug, chapter_number, decision, has_refined, search, date range, ordering
- Test `GET /scene-extractions/filters` — returns valid filter options
- Test `GET /scene-extractions/{scene_id}` — happy path and 404
- Use `scene_factory` to seed test data

**Verification**:
- [ ] All 3 endpoints have at least one happy-path test
- [ ] 404 error case tested for get-by-id
- [ ] Filter parameters tested

### Phase 2: Route tests — scene_rankings
**Goal**: Full test coverage for all 3 scene ranking endpoints.

**Tasks**:
- Create `backend/app/tests/api/routes/test_scene_rankings.py`
- Test `GET /scene-rankings/top` — global listing, book_slug filter, limit, include_scene
- Test `GET /scene-rankings/scene/{scene_id}` — history listing, 404 for unknown scene
- Test `GET /scene-rankings/{ranking_id}` — happy path and 404
- Seed test rankings via `SceneRankingRepository.create()` linked to `scene_factory` scenes

**Verification**:
- [ ] All 3 endpoints have at least one happy-path test
- [ ] 404 error cases tested
- [ ] Query parameter filtering tested

### Phase 3: Route tests — image_prompts
**Goal**: Full test coverage for all 6 image prompt endpoints.

**Tasks**:
- Create `backend/app/tests/api/routes/test_image_prompts.py`
- Test `GET /image-prompts/scene/{scene_id}` — list with filters
- Test `GET /image-prompts/list` — global list with book_slug, chapter, model, style filters
- Test `GET /image-prompts/book/{book_slug}` — book-scoped list
- Test `GET /image-prompts/{prompt_id}` — happy path and 404
- Test `POST /image-prompts/{prompt_id}/metadata/generate` — mock `PromptMetadataGenerationService.generate_metadata_variants()`, test success and 404/500 errors
- Test `PATCH /image-prompts/{prompt_id}/metadata` — update title/flavour_text, test 404 and 422 (both fields None)
- Use `prompt_factory` to seed test prompts

**Verification**:
- [ ] All 6 endpoints have tests
- [ ] Async metadata generation endpoint properly mocked
- [ ] Error cases tested (404, 422, 500)

### Phase 4: Repository tests — SceneExtractionRepository
**Goal**: Dedicated test file for the scene extraction repository.

**Tasks**:
- Create `backend/app/tests/repositories/test_scene_extraction_repository.py`
- Test `create()`, `get()`, `get_by_identity()` — basic CRUD
- Test `list_for_book()` — with and without chapter filter
- Test `list_unrefined()` — filter by refinement state
- Test `search()` — pagination, filters (book_slug, chapter, decision, has_refined, search_term, date range), ordering
- Test `chunk_indexes_for_chapter()` — returns distinct chunk indices
- Test `filter_options()` — returns correct books, chapters, decisions
- Test `upsert_by_identity()` — creates new record, updates existing record
- Test `update()` and `delete()` — basic operations
- Cleanup all created records in teardown

**Verification**:
- [ ] All 11 public methods have at least one test
- [ ] Complex query methods (search, filter_options) test multiple parameter combinations

### Phase 5: Repository tests — SceneRankingRepository
**Goal**: Dedicated test file for the scene ranking repository.

**Tasks**:
- Create `backend/app/tests/repositories/test_scene_ranking_repository.py`
- Test `create()`, `get()` — basic CRUD
- Test `get_unique_run()` — lookup by composite key
- Test `get_latest_for_scene()` — returns most recent ranking
- Test `list_for_scene()` — history with limit and ordering
- Test `list_top_rankings_for_book()` — filtered top rankings
- Test `list_ranked_scene_ids_for_book()` — returns scene IDs
- Test `list_top_rankings()` — global top rankings
- Create test rankings linked to `scene_factory` scenes

**Verification**:
- [ ] All 8 public methods have at least one test
- [ ] Ordering and filtering verified

### Phase 6: Repository tests — ImageGenerationBatchRepository
**Goal**: Dedicated test file for the batch repository.

**Tasks**:
- Create `backend/app/tests/repositories/test_image_generation_batch_repository.py`
- Test `create()`, `get()` — basic CRUD
- Test `get_by_openai_batch_id()` — lookup by OpenAI batch ID
- Test `list_pending()` — only returns batches with status in ["submitted", "validating", "in_progress"]
- Test `update_status()` — status transitions and optional fields

**Verification**:
- [ ] All 5 public methods have at least one test
- [ ] `list_pending()` correctly filters by status

### Phase 7: Service tests — scene_refinement
**Goal**: Unit tests for the refinement service.

**Tasks**:
- Create `backend/app/tests/services/test_scene_refinement_service.py`
- Test `refine()` happy path — mock `gemini_api.structured_output()` to return a `_RefinementResponse` with keep/discard decisions, verify returned dict maps scene numbers to `RefinedScene` objects
- Test `refine()` with fallback — mock Gemini to fail, mock `openai_api.structured_output()` as fallback
- Test `refine()` error handling — mock both APIs to fail, verify empty dict returned (fail_on_error=False) or `SceneRefinementError` raised (fail_on_error=True)
- Use `monkeypatch.setattr` for all LLM API mocking

**Verification**:
- [ ] Happy path, fallback, and error cases all tested
- [ ] No live API calls

### Phase 8: Service tests — scene_extraction (blocked by 020)
**Goal**: Unit tests for the refactored scene extraction service.

**Tasks**:
- Create `backend/app/tests/services/test_scene_extraction_service.py`
- Test `extract_book()` — mock `BookContentService.load_book()`, mock LLM APIs, verify repository calls for persistence
- Test `extract_preview()` — mock same dependencies, verify limited extraction (max_chapters, max_chunks)
- Test `_persist_chapter_scenes()` — mock repository methods, verify correct create/update decisions
- Test `_existing_processed_chunks()` — mock repository, verify chunk index queries
- Use constructor-injection pattern from issue 020 refactor
- **Note**: This phase is blocked by issue 020 landing first

**Verification**:
- [ ] Core extraction pipeline tested end-to-end (with mocks)
- [ ] Persistence delegation verified
- [ ] No live API calls

### Phase 9: Fix duplicated fixture
**Goal**: Remove duplicated scene fixture from test_image_prompt_repository.py.

**Tasks**:
- Modify `backend/app/tests/repositories/test_image_prompt_repository.py`:
  - Remove the `scene` fixture (lines 11-45)
  - Update test functions to use `scene_factory` parameter instead
  - Replace `scene` fixture parameter with `scene_factory` and call `scene = scene_factory()` inside tests
- Verify existing tests still pass

**Verification**:
- [ ] No `scene` fixture defined in the file
- [ ] All tests use `scene_factory` from conftest
- [ ] Tests pass

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/tests/api/routes/test_scene_extractions.py` | Create |
| `backend/app/tests/api/routes/test_scene_rankings.py` | Create |
| `backend/app/tests/api/routes/test_image_prompts.py` | Create |
| `backend/app/tests/repositories/test_scene_extraction_repository.py` | Create |
| `backend/app/tests/repositories/test_scene_ranking_repository.py` | Create |
| `backend/app/tests/repositories/test_image_generation_batch_repository.py` | Create |
| `backend/app/tests/services/test_scene_refinement_service.py` | Create |
| `backend/app/tests/services/test_scene_extraction_service.py` | Create (blocked by 020) |
| `backend/app/tests/repositories/test_image_prompt_repository.py` | Modify — remove duplicated fixture |

## Testing Strategy
- **Unit Tests**: All new test files. External API calls mocked with `monkeypatch`. No live service calls.
- **Manual Verification**: `cd backend && uv run pytest` passes with all new and existing tests

## Acceptance Criteria
- [ ] All 3 untested route files have dedicated test files with all endpoints covered
- [ ] All 3 untested repository files have dedicated test files
- [ ] `scene_refinement.py` has service-level unit tests
- [ ] `scene_extraction.py` has service-level unit tests (after 020 lands)
- [ ] Duplicated fixture in `test_image_prompt_repository.py` replaced with `scene_factory`
- [ ] All external API calls mocked — no live calls in unit tests
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
