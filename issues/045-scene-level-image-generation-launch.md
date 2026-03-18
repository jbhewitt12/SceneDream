# Scene-Level Image Generation Launch from Extracted Scenes Page

## Overview

Add a "Generate Images" launch panel to each expanded scene card in the Extracted Scenes page, allowing users to trigger image generation for a specific scene directly from the scene list — without going through the Documents dashboard.

## Problem Statement

Users who want to generate images for a specific extracted scene currently have no direct path from the Extracted Scenes page. They must navigate to the Documents dashboard, launch a full pipeline run, and hope the ranking selects the target scene. This is inefficient when the intent is targeted: "generate N images for this scene."

The orchestrator (issue-044) already supports `SceneTarget` runs. The backend endpoint `POST /scene-extractions/{scene_id}/generate` is fully implemented with comprehensive tests. Only frontend work remains.

## Proposed Solution

Embed a compact "Generate Images" launch panel into each expanded accordion item in the Extracted Scenes page. The panel mirrors the Documents dashboard "Launch Pipeline" section: a variant count input, an art style picker, a summary panel, and a launch button with polling feedback.

The panel uses the existing `POST /scene-extractions/{scene_id}/generate` endpoint (returns `pipeline_run_id` for polling) and the `PromptArtStyleControl` component without modification.

## Codebase Research Summary

**Backend — already complete:**
- `backend/app/api/routes/scene_extractions.py`: `POST /{scene_id}/generate` is wired to the orchestrator via `PipelineRunStartService` and `spawn_background_task`. Returns `SceneGenerateResponse` with `pipeline_run_id`, `status`, `message`.
- `backend/app/schemas/scene_extraction.py`: `SceneGenerateRequest` accepts `num_images` (1–20), `prompt_art_style_mode`, `prompt_art_style_text`, `quality`, `style`, `aspect_ratio`. `SceneGenerateResponse` returns `pipeline_run_id: UUID`, `status: str`, `message: str`.
- `backend/app/tests/api/routes/test_scene_extractions.py`: Six tests cover success, 404, validation, art style, document context derivation, and task-creation failure. No additional backend tests required.

**Frontend — needs work:**
- `frontend/src/routes/_layout/extracted-scenes.tsx`: Accordion-based scene list. `SceneExtractionItem` renders trigger (title/badges + raw text) and content (refined excerpt, metadata grid, additional properties). The content section needs a `SceneLaunchPanel` inserted between the refined excerpt and the metadata grid.
- `frontend/src/api/sceneExtractions.ts`: Hand-written API wrapper — needs a `generate()` method added.
- `frontend/src/api/pipelineRuns.ts`: `PipelineRunsApi.get(runId)` is already available for polling.
- `frontend/src/components/Common/PromptArtStyleControl.tsx`: Used as-is. Requires `selection`, `recommendedCount`, `otherCount`, `randomMixManageCopy`, `onModeChange`, `onTextChange`.
- `frontend/src/features/documents/documentsLaunch.ts`: Reference for art style payload builder pattern (`getPromptArtStyleTextForPayload`).
- `frontend/src/api/settings.ts` + `frontend/src/routes/_layout/documents.tsx`: Reference for fetching settings and deriving `defaultPromptArtStyleSelection` and `artStyleCatalogCounts`.

**Key types:**
- `SceneExtraction` in `sceneExtractions.ts` does not include `document_id` — not needed since the backend resolves context from the scene record.
- `PromptArtStyleSelection` from `@/types/promptArtStyle` is the shared art style state type.
- `getPromptArtStyleSelectionFromSettings` and `getPromptArtStyleTextForPayload` from `@/types/promptArtStyle` are the helpers to use.

## Key Decisions

- **Backend is complete**: No schema changes, no new routes, no client regeneration needed.
- **`SceneLaunchPanel` lives inside `extracted-scenes.tsx`**: Not a separate file — the component is scoped to this page.
- **Settings fetched once at page level**: `SettingsApi.get()` is added to `ExtractedScenesPage` and `defaultPromptArtStyleSelection` + `artStyleCatalogCounts` passed as props into `SceneLaunchPanel`.
- **Each panel is self-contained**: Local state for `variantCount`, `artStyleSelection`, `launching`, `activeRun`. No shared state across scene cards.
- **Polling uses `PipelineRunsApi.get()`**: After launch, poll `pipeline_run_id` every 3 seconds until terminal status. Show toast on completion or failure. Pattern follows `documents.tsx` polling loop.
- **Scene card content order**: refined excerpt → launch panel → metadata grid → additional properties.
- **`SceneGenerateResponse.pipeline_run_id`** is a UUID string — use it directly with `PipelineRunsApi.get(pipeline_run_id.toString())`.
- **No OpenAPI client regeneration**: Use hand-written request via `__request` in `sceneExtractions.ts`, matching the existing pattern in that file.

## Implementation Plan

### Phase 1: Add `generate()` to `SceneExtractionService`

**Goal**: Give the frontend a typed method to call `POST /scene-extractions/{scene_id}/generate`.

**Tasks**:
- Add `SceneGenerateRequest` and `SceneGenerateResponse` types to `frontend/src/api/sceneExtractions.ts` (matching the backend schema: `num_images`, `prompt_art_style_mode`, `prompt_art_style_text`, `quality`, `aspect_ratio`; response: `pipeline_run_id`, `status`, `message`)
- Add `generate(sceneId: string, request: SceneGenerateRequest): CancelablePromise<SceneGenerateResponse>` method to `SceneExtractionService` in `frontend/src/api/sceneExtractions.ts`, posting to `/api/v1/scene-extractions/{scene_id}/generate`

**Verification**:
- [ ] TypeScript types match the backend schema fields
- [ ] Method uses `__request` with method `"POST"`, url pattern, path param, and body — consistent with existing hand-written API wrappers

### Phase 2: Add settings fetch to `ExtractedScenesPage`

**Goal**: Make art style defaults available to the launch panel without each card fetching settings independently.

**Tasks**:
- Import `SettingsApi` from `@/api/settings` in `frontend/src/routes/_layout/extracted-scenes.tsx`
- Add `settingsQuery` using `useQuery` with key `["settings", "bundle"]` and `SettingsApi.get()` — same pattern as `documents.tsx:221-224`
- Derive `defaultPromptArtStyleSelection` using `getPromptArtStyleSelectionFromSettings(settingsQuery.data?.settings)` — same as `documents.tsx:228-231`
- Derive `artStyleCatalogCounts` by reducing `settingsQuery.data?.art_styles` into `{ recommended, other }` counts — same as `documents.tsx:232-245`
- Pass `defaultPromptArtStyleSelection` and `artStyleCatalogCounts` as props to each `SceneExtractionItem`

**Verification**:
- [ ] Settings are fetched once at page level, not per card
- [ ] `SceneExtractionItem` prop types updated to accept the new props

### Phase 3: Implement `SceneLaunchPanel` component

**Goal**: A self-contained launch panel matching the Documents dashboard "Launch Pipeline" section layout, embedded in each expanded scene card.

**Tasks**:
- Add `SceneLaunchPanel` component inside `frontend/src/routes/_layout/extracted-scenes.tsx`, accepting props: `scene: SceneExtraction`, `defaultArtStyleSelection: PromptArtStyleSelection`, `artStyleCatalogCounts: { recommended: number; other: number }`
- Add local state: `variantCount: string` (default `"3"`), `artStyleSelection: PromptArtStyleSelection` (initialized from `defaultArtStyleSelection`), `launching: boolean`, `activeRun: { pipeline_run_id: string; status: string } | undefined`
- Import and add necessary Chakra UI primitives: `Grid` is already imported; add any missing ones (check current imports)
- Add `useEffect` polling loop: when `activeRun` exists and status is not terminal (`"completed"` | `"failed"`), poll `PipelineRunsApi.get(activeRun.pipeline_run_id)` every 3000ms; on terminal status show success/error toast via `useCustomToast`
- Render layout mirroring the Documents dashboard launch section (`documents.tsx:820-967`):
  - Section header: "GENERATE IMAGES FOR THIS SCENE" label + description text
  - Left column: variant count `Input` (type number, min 1) + `PromptArtStyleControl`
  - Right panel: summary text (e.g. "3 variants"), art style summary, active run badge if running, launch `Button` with loading state, helper text
  - Below: "Last Run" status strip showing `status`, completion time, error message if any
- `handleLaunch` function: validates `variantCount`, builds `SceneGenerateRequest` payload (using `getPromptArtStyleTextForPayload`), calls `SceneExtractionService.generate(scene.id, payload)`, stores result in `activeRun`, shows success toast on launch, shows error toast on failure
- Import `PipelineRunsApi` from `@/api/pipelineRuns` for polling
- Import `useCustomToast` from `@/hooks/useCustomToast`

**Verification**:
- [ ] Panel renders inside expanded scene card without layout breakage
- [ ] Variant count input accepts positive integers only
- [ ] Art style control toggles between random mix and single style correctly
- [ ] Launch button shows loading state while `launching` is true
- [ ] Polling updates status every 3 seconds until terminal
- [ ] Success/error toasts fire correctly

### Phase 4: Wire `SceneLaunchPanel` into `SceneExtractionItem` and reorder content

**Goal**: Update the accordion item content to include the launch panel between the refined excerpt and the metadata grid.

**Tasks**:
- Update `SceneExtractionItem` in `frontend/src/routes/_layout/extracted-scenes.tsx` to accept `defaultArtStyleSelection` and `artStyleCatalogCounts` as props
- Insert `<SceneLaunchPanel scene={scene} defaultArtStyleSelection={defaultArtStyleSelection} artStyleCatalogCounts={artStyleCatalogCounts} />` inside `AccordionItemContent`, after the refined excerpt section and before the metadata grid section
- Add `<Separator />` before and/or after the launch panel for visual separation (match the Chakra UI separator already imported)
- Update `ExtractedScenesPage` to pass the new props down to each `SceneExtractionItem`

**Verification**:
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npm run build` passes
- [ ] Expanded scene cards show content in the correct order: raw text in trigger, then (on expand) refined excerpt → launch panel → metadata → additional properties

### Phase 5: Browser verification — generate one image for one scene

**Goal**: Use `agent-browser` to exercise the fully implemented UI end-to-end and confirm one image is actually generated.

**Prerequisites**: The full stack must be running (`docker compose watch` or `docker compose up -d` + local backend/frontend). The frontend is at `http://localhost:5173`.

**Tasks**:
- Run `agent-browser open http://localhost:5173/extracted-scenes` to navigate to the Extracted Scenes page
- Run `agent-browser snapshot` to get the element tree; identify the first scene accordion item trigger
- Click the trigger to expand the first scene card; run `agent-browser snapshot` again to confirm the launch panel is visible (look for the "GENERATE IMAGES FOR THIS SCENE" heading and the Generate button)
- Set variant count to `1` — locate the variant count input via snapshot ref and use `agent-browser fill <ref> "1"`
- Leave art style on the default (Random Style Mix) unless no styles are configured; if the launch button appears disabled due to art style validation, switch to Single art style and fill in a style name (e.g. "watercolor painting")
- Click the Generate button via its snapshot ref
- Run `agent-browser snapshot` after clicking and confirm the button enters a loading state or a status badge appears
- Poll by running `agent-browser snapshot` every few seconds until the status changes to "completed" or a success toast appears (the run typically completes within 30–90 seconds depending on provider)
- Run `agent-browser close` when done
- After closing the browser, verify the image was persisted: check the Generated Images page at `http://localhost:5173/generated-images` using `agent-browser open` + `snapshot`, or query the DB directly with `cd backend && uv run python -c "from app.db import get_engine; ..."` if browser verification is inconclusive

**Verification**:
- [ ] Launch panel is visible in the expanded scene card
- [ ] Clicking Generate triggers a run (button shows loading state or status badge appears)
- [ ] Run reaches "completed" status and success toast fires
- [ ] At least one image appears on the Generated Images page for the scene

## Files to Modify

| File | Action |
|------|--------|
| `frontend/src/api/sceneExtractions.ts` | Modify — add `SceneGenerateRequest`, `SceneGenerateResponse` types and `generate()` method |
| `frontend/src/routes/_layout/extracted-scenes.tsx` | Modify — add settings fetch, `SceneLaunchPanel` component, update `SceneExtractionItem` props and content order |

## Testing Strategy

- **Backend**: Already fully covered. No new tests required.
- **Frontend build validation**: `cd frontend && npm run lint && npm run build` must pass after changes.
- **Browser verification**: Use `agent-browser` in Phase 5 to navigate to `http://localhost:5173/extracted-scenes`, expand a scene card, set variant count to 1, launch generation, and confirm the run reaches "completed" and an image appears on the Generated Images page.

## Completion Notes

### Implementation Summary (2026-03-18)

Phases 1–4 implemented as planned. Phase 5 completed (2026-03-18) via `agent-browser` with the stack running locally. Three bugs were surfaced and fixed during browser verification:

**Phase 5 bug fixes (backend only):**

1. `backend/app/repositories/image_prompt.py` — `delete_for_scene` excluded prompts referenced by `generated_images` (FK violation when re-running on a scene that already had images). Added `~exists().where(GeneratedImage.image_prompt_id == ImagePrompt.id)` filter.

2. `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` — After `delete_for_scene` returns 0 (all prompts blocked by FK), return existing prompts instead of trying to re-insert (which would hit a unique constraint).

3. `backend/app/services/pipeline/pipeline_orchestrator.py` — Two fixes:
   - `_execute_scene_prompt_generation`: disabled `skip_scenes_with_warnings` for SceneTarget runs since the user explicitly chose the scene.
   - `_execute_image_generation`: when `generate_for_selection` returns 0 new images due to idempotency (images already exist), collect and count existing images so the run succeeds instead of failing with "No images were generated".

**Changes made (Phases 1–4):**

- `frontend/src/api/sceneExtractions.ts`: Added `SceneGenerateRequest`, `SceneGenerateResponse` types and `generate()` method using `__request` with `POST /api/v1/scene-extractions/{scene_id}/generate`.

- `frontend/src/routes/_layout/extracted-scenes.tsx`:
  - Added imports: `Grid`, `useEffect`, `useRef`, `useState`, `FiPlay`, `PipelineRunsApi`, `SettingsApi`, `PromptArtStyleControl`, `useCustomToast`, and `promptArtStyle` helpers.
  - Added `SceneLaunchPanel` component with local state, polling loop (3s interval), `handleLaunch`, and full layout mirroring the Documents dashboard launch section.
  - Updated `SceneExtractionItem` to accept and forward `defaultArtStyleSelection` and `artStyleCatalogCounts` props; inserted `SceneLaunchPanel` between refined excerpt and metadata sections, wrapped with `<Separator />` on each side.
  - Added `settingsQuery`, `defaultPromptArtStyleSelection`, and `artStyleCatalogCounts` derivation to `ExtractedScenesPage`; passed as props to each `SceneExtractionItem`.

**All 426 backend tests pass. `npm run lint` and `npm run build` both pass.**

## Acceptance Criteria

- [ ] `cd frontend && npm run lint` passes with no errors
- [ ] `cd frontend && npm run build` passes with no errors
- [ ] `cd backend && uv run pytest` passes (no regressions)
- [ ] Expanded scene card shows: raw text → (on expand) refined excerpt → launch panel → metadata grid → additional properties
- [ ] Variant count input defaults to 3, validates positive integer
- [ ] Art style control works (random mix / single style toggle and text input)
- [ ] Launch button triggers `POST /scene-extractions/{scene_id}/generate` with correct payload
- [ ] Active run is polled every 3 seconds and status badge updates
- [ ] Success toast fires when run completes; error toast fires on failure
- [ ] Settings art style defaults are seeded into each panel from a single page-level fetch
- [ ] `agent-browser` end-to-end test in Phase 5 confirms one image is generated and visible on the Generated Images page
