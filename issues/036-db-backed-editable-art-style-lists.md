# Switch Art Style Lists to DB-Backed, Frontend-Editable Settings

## Overview
Replace runtime hardcoded style lists with database-backed style lists that users can edit directly in Settings using two large text areas: Recommended Styles and Other Styles.

## Problem Statement
Art style management is only partially migrated:
- styles are stored as `art_styles` rows (`is_recommended` split), but there is no bulk list-editing API
- the Settings UI only exposes default scene count + default art style dropdown
- runtime still imports hardcoded fallback lists from `style_sampler.py`

This does not match the intended product workflow where users can edit both style pools quickly as line-based lists.

## Proposed Solution
Implement full list-based style management backed by existing `art_styles` rows:
- add settings APIs to read/write both style lists as ordered arrays
- redesign Settings page with an **Art Styles** section containing two big textareas (one style per line)
- apply updates transactionally to `art_styles` (upsert, ordering, active/inactive lifecycle)
- make DB the runtime source of truth for style sampling

Out of scope for this issue:
- blocked terms or realism-policy controls
- photorealism filtering logic

## Codebase Research Summary

### Existing backend pieces
- `backend/models/art_style.py`
  - already has `display_name`, `is_recommended`, `is_active`, `sort_order`
- `backend/app/repositories/art_style.py`
  - supports `list_active()`, `create()`, `update()`, `get_by_slug()`
- `backend/app/api/routes/settings.py`
  - currently supports:
    - `GET /api/v1/settings` (bundle with active styles)
    - `PATCH /api/v1/settings` (default scenes + default style)
    - `GET /api/v1/settings/art-styles` (flat active style list)

### Existing frontend pieces
- `frontend/src/routes/_layout/settings.tsx`
  - currently renders only default scenes + default style dropdown
- `frontend/src/api/settings.ts`
  - only supports get/update defaults

### Existing runtime behavior
- `ImagePromptGenerationService._build_style_sampler()` reads DB styles first but falls back to hardcoded lists from `style_sampler.py`.

## Key Decisions
- Reuse current `art_styles` table; do not introduce a new table for list blobs.
- Use a dedicated list API contract (arrays), while frontend textareas remain a presentation layer.
- Preserve removed styles as inactive rows (`is_active=False`) instead of deleting.
- Keep ordering from textarea line order by writing `sort_order`.
- No blocked-term validation/filtering in this issue.

## Implementation Plan

### Phase 1: Add list-oriented settings API contract
**Goal**: expose both style pools as first-class list settings.

**Tasks**:
- Add schemas for:
  - `ArtStyleListsRead` (recommended + other arrays + updated timestamp)
  - `ArtStyleListsUpdateRequest` (recommended + other arrays)
- Add endpoints under `/api/v1/settings`:
  - `GET /art-style-lists`
  - `PUT /art-style-lists`
- Return deterministic ordering based on `sort_order` then `display_name`

**Verification**:
- [ ] API returns both lists separately with stable ordering
- [ ] API accepts full replacement payload for both lists

### Phase 2: Implement transactional sync service for list updates
**Goal**: convert array payloads into `art_styles` row updates safely.

**Tasks**:
- Add service (for example `app/services/art_style/art_style_catalog_service.py`) to:
  - normalize entries (trim, remove empties)
  - deduplicate within each list
  - resolve duplicates across lists deterministically (recommended list wins)
  - upsert rows by slug/display name
  - set `is_recommended` + `sort_order`
  - mark missing styles inactive
- Ensure updates happen in one transaction
- If current `default_art_style_id` is no longer active, set to first recommended active style or `null`

**Verification**:
- [ ] Save operation is idempotent
- [ ] Reordering lines updates sort order
- [ ] Removing a style marks it inactive
- [ ] Default art style does not reference inactive rows

### Phase 3: Make runtime sampling fully DB-driven
**Goal**: remove runtime dependency on hardcoded style catalogs.

**Tasks**:
- Update `ImagePromptGenerationService._build_style_sampler()` to use active DB styles as source of truth
- Remove hardcoded fallback-list usage in runtime path (retain only explicit error handling if no active styles)
- Surface clear error if style catalog is empty/misconfigured

**Verification**:
- [ ] Prompt generation uses DB lists only
- [ ] Prompt generation fails with actionable error if no active styles exist

### Phase 4: Redesign Settings UI with two editable text lists
**Goal**: deliver intended UX for style management.

**Tasks**:
- Keep current defaults controls, but split page into sections:
  - `Pipeline Defaults`
  - `Art Styles`
- Add two large textareas:
  - `Recommended Styles` (one per line)
  - `Other Styles` (one per line)
- Add explanation block in plain language describing sampling behavior:
  - for `N` variants, sample `min(max(2, N+2), len(recommended))` from recommended
  - sample `min(max(1, N//2), len(other))` from other
  - combine and shuffle before prompt generation
- Update save/reset flow to include lists
- Show validation errors inline (empty both lists, duplicate handling outcomes)

**Verification**:
- [ ] Users can paste/edit/remove styles line-by-line
- [ ] Saving persists list content and order
- [ ] Reloading settings reflects saved lists exactly
- [ ] Explanation text is visible and understandable

### Phase 5: Tests and API client alignment
**Goal**: ensure end-to-end reliability.

**Tasks**:
- Backend tests:
  - route tests for `GET/PUT /settings/art-style-lists`
  - service tests for sync rules (ordering, dedupe, inactive lifecycle)
- Frontend:
  - update OpenAPI client generation and `frontend/src/api/settings.ts` wrappers
  - verify settings screen mutation/query behavior
- Run required checks

**Verification**:
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/api/routes/settings.py` | Modify |
| `backend/app/schemas/app_settings.py` and/or new settings schema module | Modify/Create |
| `backend/app/services/art_style/art_style_catalog_service.py` | Create |
| `backend/app/services/art_style/__init__.py` | Modify |
| `backend/app/repositories/art_style.py` | Modify (supporting queries/updates as needed) |
| `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` | Modify |
| `backend/app/services/image_prompt_generation/core/style_sampler.py` | Modify (remove hardcoded catalog dependency in runtime path) |
| `backend/app/tests/api/routes/test_settings.py` | Modify |
| `backend/app/tests/services/test_art_style_service.py` and/or new catalog service tests | Modify/Create |
| `frontend/src/routes/_layout/settings.tsx` | Modify |
| `frontend/src/api/settings.ts` | Modify |
| `frontend/src/client/*` (generated) | Regenerate |

## Testing Strategy
- Backend unit + route tests for list sync semantics and endpoint behavior
- Frontend manual validation on Settings page:
  - edit both lists
  - save
  - refresh and confirm persistence
  - verify default style dropdown stays valid
- End-to-end CLI smoke test for prompt + image generation:
  - `cd backend && uv run python -m app.services.image_gen_cli backfill --book-slug excession-iain-m-banks --top-scenes 1`
- Full test/lint runs:
  - `cd backend && uv run pytest`
  - `cd frontend && npm run lint`

## Acceptance Criteria
- [ ] Settings page has an `Art Styles` section with two large line-based textareas
- [ ] Users can edit and save both style lists without touching code
- [ ] Style ordering in textareas is preserved in sampling source data
- [ ] Runtime sampling reads styles from DB (not hardcoded runtime lists)
- [ ] No blocked-terms behavior is introduced in this feature
- [ ] If users add `photorealism` to either list, it is stored and eligible for sampling
- [ ] `cd backend && uv run python -m app.services.image_gen_cli backfill --book-slug excession-iain-m-banks --top-scenes 1` is run successfully as a final smoke test
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
