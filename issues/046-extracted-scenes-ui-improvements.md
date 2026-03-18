# Extracted Scenes UI Improvements

## Overview

Streamline the Extracted Scenes page by removing low-value filters, surfacing ranking scores on scene cards, adding a sort-by dropdown, debouncing the search input, and replacing pagination with infinite scroll.

## Problem Statement

The current Extracted Scenes page has six filter controls (Book, Chapter, Decision, Refinement, Start Date, End Date) that clutter the UI. Chapter, Refinement, Start Date, and End Date are rarely used and add visual noise. Ranking scores are not visible on scene cards despite being the most actionable signal for scene quality. The search input updates the URL on every keystroke, triggering a network request per character typed. Numbered pagination breaks flow when browsing large scene sets.

## Proposed Solution

- Remove the Chapter, Refinement, Start Date, and End Date filters. Keep Decision and rename "Book" to "Document".
- Add a sort-by dropdown with options: Extracted (Newest), Extracted (Oldest), Ranking Score (Highest).
- Extend the backend to JOIN the most recent `SceneRanking.overall_priority` per scene and return it on `SceneExtractionRead`; support ordering by it.
- Display the ranking score as a badge on each scene card accordion trigger when a score exists.
- Debounce the search input with a local state buffer (400 ms) so the URL and query are only updated after the user stops typing.
- Replace the `PaginationRoot` controls with `useInfiniteQuery` + IntersectionObserver, following the pattern already established in `generated-images.tsx`.

## Codebase Research Summary

**Affected files:**
- `frontend/src/routes/_layout/extracted-scenes.tsx` — main page; contains `SceneExtractionFilters`, `SceneExtractionItem`, and `ExtractedScenesPage`. Currently uses `useQuery` + `PaginationRoot`.
- `frontend/src/api/sceneExtractions.ts` — hand-written API client (not generated); defines `SceneExtraction`, `SceneExtractionListParams`, and `SceneExtractionService`.
- `backend/app/api/routes/scene_extractions.py` — route handler; passes `order: Literal["asc","desc"]` to the repository.
- `backend/app/repositories/scene_extraction.py` — `search()` method orders by `SceneExtraction.extracted_at`; no JOIN to rankings.
- `backend/app/schemas/scene_extraction.py` — `SceneExtractionRead` has no ranking field; `SceneExtractionListResponse` wraps it.
- `backend/models/scene_ranking.py` — `SceneRanking.overall_priority: float` is the score field. Multiple rankings per scene are possible; we use the most recent by `created_at`.

**Infinite scroll pattern:** `generated-images.tsx` uses `useInfiniteQuery` with `getNextPageParam` based on page count and `IntersectionObserver` on a sentinel `<Box ref={loadMoreRef}>`. Replicate this exactly.

**Debounce pattern:** The codebase does not currently debounce search inputs anywhere. Use local `useState` for the input value and a `useRef`-held `setTimeout` to flush to URL after 400 ms (clear on each keystroke).

## Key Decisions

- **Ranking score source:** most recent `SceneRanking` by `created_at` for each scene (not max or average).
- **Pagination:** removed entirely; infinite scroll replaces it.
- **Filter removals:** Chapter, Refinement, Start Date, End Date are removed. URL search schema fields `chapter_number`, `has_refined`, `start_date`, `end_date` are also removed.
- **Sort options:** `extracted_desc` (default), `extracted_asc`, `ranking_desc`. The `order` field in the URL schema becomes `sort_by`.
- **"Book" → "Document":** label only; the underlying `book_slug` field name is unchanged throughout.

## Implementation Plan

### Phase 1: Backend — expose ranking score and sort-by

**Goal**: Return `ranking_score` on scene extraction records and accept `sort_by` as a query parameter.

**Tasks**:
- In `backend/app/repositories/scene_extraction.py`, update `search()` to:
  - Accept a new `sort_by: str = "extracted_desc"` parameter (valid values: `extracted_desc`, `extracted_asc`, `ranking_desc`).
  - When `sort_by` is `ranking_desc`, LEFT JOIN `SceneRanking` on a subquery that selects the most recent `overall_priority` per `scene_extraction_id` (using `DISTINCT ON` or a correlated subquery), then ORDER BY that value DESC (NULLs last).
  - Return the joined `overall_priority` value alongside each `SceneExtraction` record. Since `search()` currently returns `list[SceneExtraction]`, change the return type to `list[tuple[SceneExtraction, float | None]]` (or a lightweight dataclass) so the score travels with the scene.
- In `backend/app/schemas/scene_extraction.py`, add `ranking_score: float | None = None` to `SceneExtractionRead`. Remove unused schema fields if any.
- In `backend/app/api/routes/scene_extractions.py`:
  - Replace `order: Literal["asc", "desc"]` query parameter with `sort_by: Literal["extracted_desc", "extracted_asc", "ranking_desc"] = "extracted_desc"`.
  - Unpack the new repository return type and populate `SceneExtractionRead.ranking_score` before building the response.
  - Remove `start_date`, `end_date`, `chapter_number`, `has_refined` query parameters from the list endpoint (they are no longer exposed).

**Verification**:
- [ ] `GET /api/v1/scene-extractions/?sort_by=ranking_desc` returns scenes ordered by score descending, nulls last.
- [ ] Each record includes `ranking_score` (null when not yet ranked).
- [ ] `uv run bash scripts/lint.sh` passes.

### Phase 2: Backend tests

**Goal**: Ensure the new repository and route behaviour is covered.

**Tasks**:
- In `backend/app/tests/repositories/test_scene_extraction_repository.py` (create if absent), add tests for:
  - `search(sort_by="ranking_desc")` returns scenes ordered by `overall_priority` desc with unranked scenes last.
  - `search(sort_by="extracted_desc")` still works unchanged.
- In `backend/app/tests/api/routes/test_scene_extractions.py` (create if absent), add tests for:
  - `GET /api/v1/scene-extractions/?sort_by=ranking_desc` returns 200 with `ranking_score` field.
  - Removed params (`chapter_number`, `has_refined`, `start_date`, `end_date`) are silently ignored or return 422 — document whichever behaviour is simpler.
- Use `scene_factory` and `prompt_factory` fixtures from `backend/app/tests/conftest.py` where applicable.

**Verification**:
- [ ] `uv run pytest` passes with no regressions.

### Phase 3: Frontend API client update

**Goal**: Align the frontend API types with the updated backend contract.

**Tasks**:
- In `frontend/src/api/sceneExtractions.ts`:
  - Add `ranking_score: number | null` to `SceneExtraction` type.
  - Replace `order?: "asc" | "desc"` in `SceneExtractionListParams` with `sort_by?: "extracted_desc" | "extracted_asc" | "ranking_desc"`.
  - Remove `chapter_number`, `has_refined`, `start_date`, `end_date` from `SceneExtractionListParams`.
  - Update `SceneExtractionService.list()` to pass `sort_by` in the query object instead of `order`.

**Verification**:
- [ ] `cd frontend && npm run build` passes (type-checks the client).

### Phase 4: Frontend page — filter cleanup, sort-by, ranking badge, debounced search, infinite scroll

**Goal**: Ship all visible UI changes.

**Tasks**:

**Search schema (`extractedScenesSearchSchema` in `extracted-scenes.tsx`)**:
- Remove `chapter_number`, `has_refined`, `start_date`, `end_date`, `page`, `page_size` fields.
- Replace `order: z.enum(["asc","desc"]).catch("desc")` with `sort_by: z.enum(["extracted_desc","extracted_asc","ranking_desc"]).catch("extracted_desc")`.

**Filter component (`SceneExtractionFilters`)**:
- Remove `chaptersForBook` memo and the Chapter `<Box>` block.
- Remove the second `<SimpleGrid>` row (Refinement, Start Date, End Date).
- Rename the label above the book dropdown from `Book` to `Document`. Keep the `book_slug` field name.
- Add a `sort_by` dropdown (`NativeSelectRoot`) in the first `<SimpleGrid>` row (alongside Document and Decision), with options:
  - `extracted_desc` → "Newest first"
  - `extracted_asc` → "Oldest first"
  - `ranking_desc` → "Ranking score"
- Remove `start_date` and `end_date` from `resetFilters`.
- **Debounce search input**: introduce a `searchDraft` local state initialised from `search.search`. Replace the `<Input>` `onChange` handler so it updates `searchDraft` immediately (for visual feedback) and schedules a `setTimeout` (400 ms) that calls `handleChange({ search: value || undefined })`. Cancel the previous timer on each keystroke via `useRef<ReturnType<typeof setTimeout>>`. On unmount clear the timer.

**Scene card (`SceneExtractionItem`)**:
- Add `ranking_score: number | null | undefined` to the component props.
- In the accordion trigger badge row, after the existing badges, render a ranking badge when `ranking_score != null`:
  ```
  <Badge colorScheme="orange" ...>
    Score {ranking_score.toFixed(2)}
  </Badge>
  ```

**Page component (`ExtractedScenesPage`)**:
- Replace `useQuery` for the list with `useInfiniteQuery`:
  - `queryKey: ["scene-extractions", cleanSearch]`
  - `queryFn: ({ pageParam = 1 }) => SceneExtractionService.list({ ...cleanSearch, page: pageParam })`
  - `initialPageParam: 1`
  - `getNextPageParam`: if `lastPage.data.length < PAGE_SIZE` return `undefined`, else return `allPages.length + 1`.
- Keep `PAGE_SIZE = 20` as a constant; remove `page` and `page_size` from URL state.
- Flatten pages: `const scenes = (listQuery.data?.pages ?? []).flatMap(p => p.data)`.
- Add `const loadMoreRef = useRef<HTMLDivElement>(null)` and an `IntersectionObserver` effect matching the pattern in `generated-images.tsx` (observe sentinel, call `fetchNextPage` on intersect, disconnect on cleanup). Guard against `isFetchingNextPage` inside the observer callback.
- Replace `<PaginationRoot>` block with the sentinel `<Box>` that shows a spinner when `isFetchingNextPage`, "Scroll for more" when `hasNextPage`, and "All scenes loaded" when exhausted.
- Remove the `setPage` helper and all pagination-related imports (`PaginationItems`, `PaginationNextTrigger`, `PaginationPrevTrigger`, `PaginationRoot`).
- Pass `scene.ranking_score` down to `SceneExtractionItem`.
- Update `cleanSearch` to remove `start_date`/`end_date` ISO conversion and pass `sort_by` instead of `order`.

**Verification**:
- [ ] `cd frontend && npm run lint` passes.
- [ ] `cd frontend && npm run build` passes.

## Files to Modify

| File | Action |
|------|--------|
| `backend/app/repositories/scene_extraction.py` | Modify — add `sort_by` param, LEFT JOIN ranking score, update return type |
| `backend/app/schemas/scene_extraction.py` | Modify — add `ranking_score: float \| None` to `SceneExtractionRead` |
| `backend/app/api/routes/scene_extractions.py` | Modify — replace `order` with `sort_by`, remove unused query params, populate `ranking_score` |
| `backend/app/tests/repositories/test_scene_extraction_repository.py` | Create — repository tests for `sort_by` |
| `backend/app/tests/api/routes/test_scene_extractions.py` | Create — route tests for new params and `ranking_score` field |
| `frontend/src/api/sceneExtractions.ts` | Modify — add `ranking_score`, replace `order` with `sort_by`, remove removed params |
| `frontend/src/routes/_layout/extracted-scenes.tsx` | Modify — all UI changes described in Phase 4 |

## Testing Strategy

- **Unit/repository tests**: verify `sort_by=ranking_desc` ordering with and without rankings present; verify nulls-last behaviour.
- **Route tests**: confirm `ranking_score` field present in response, confirm `sort_by` accepted.
- **Manual verification**: load Extracted Scenes, confirm no Chapter/Refinement/date filters; confirm sort dropdown changes order; confirm typing in search does not fire requests mid-word; confirm scrolling to the bottom loads the next page.

## Acceptance Criteria

- [x] Chapter, Refinement, Start Date, and End Date filters are removed from the UI and from the backend query params.
- [x] The "Book" filter label reads "Document"; underlying `book_slug` field is unchanged.
- [x] A sort-by dropdown is present with Newest first / Oldest first / Ranking score options.
- [x] Scenes with a ranking display a "Score X.XX" badge in the accordion trigger row.
- [x] Typing in the search box does not update the URL until 400 ms after the last keystroke.
- [x] Scrolling to the bottom of the scene list loads the next page automatically; no page number controls are shown.
- [x] All backend tests pass (`uv run pytest`).
- [x] Backend linting passes (`uv run bash scripts/lint.sh`).
- [x] Frontend linting and build pass (`npm run lint && npm run build`).

## Completion Notes

Implemented all four phases as planned, plus an additional content warnings filter requested by the user during implementation.

**Deviations from plan:**
- Added a `has_warnings` filter (not in original plan) that exposes `SceneRanking.warnings` through the API. The repository uses a PostgreSQL `EXISTS` + `CASE WHEN jsonb_typeof(...) = 'array' THEN jsonb_array_length(...) ELSE 0 END > 0` pattern to safely check for non-empty warning arrays, guarding against JSON `null` scalar values that would cause `jsonb_array_length` to raise.
- Added `has_content_warnings: bool` to `SceneExtractionRead` so the frontend can show a "Flagged" badge on scene cards.
- The filter panel uses 4 columns instead of 3 (Document, Decision, Content Warnings, Sort By).
- Removed the date range display footer from the filters panel (it was only useful alongside the date range filters that were removed).
- Repository `search()` return type changed from `list[SceneExtraction]` to `list[tuple[SceneExtraction, float | None, bool]]` to carry ranking score and warnings flag alongside each scene. The route unpacks these and populates the schema fields.
- Used `session.execute()` (not `session.exec()`) for the multi-column SELECT query since SQLModel's `exec()` is designed for single-model results.
