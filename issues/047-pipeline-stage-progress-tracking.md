# Pipeline Stage Progress Tracking

## Overview

Add per-stage progress tracking to pipeline runs so users can see how far through each stage (extraction, ranking, prompt generation, image generation) a run has progressed while it is active.

## Problem Statement

When a pipeline run is active the documents view shows only the current stage name (e.g. `Stage: generating_prompts`) with no indication of how much work within that stage has been completed. For documents with 30–50 scenes, ranking and prompt generation can take several minutes, and users have no feedback on whether the run is progressing normally or stuck.

## Proposed Solution

- Add a `stage_progress` JSONB column to `pipeline_runs`, separate from the existing `usage_summary` column (which remains a final-state snapshot).
- The orchestrator writes to `stage_progress` at the start and end of each stage, after every scene during ranking and prompt-generation, and after every image via a callback into the image generation service.
- Expose `stage_progress` on `PipelineRunRead` and regenerate the frontend client.
- Replace the single `Stage: generating_prompts` line in `DocumentCard` with a compact 4-row breakdown showing status and item counts per stage.
- The existing 3-second polling loop is unchanged — no new transport or background threads needed.

## Codebase Research Summary

**Key files:**
- `backend/models/pipeline_run.py` — `PipelineRun` SQLModel; has `usage_summary: dict` (JSONB) for final output; no progress field today.
- `backend/app/services/pipeline/orchestrator_config.py` — `PipelineStats` holds live counters (`scenes_extracted`, `scenes_ranked`, `prompts_generated`, `images_generated`) during a run; only flushed to `usage_summary` at finalization.
- `backend/app/services/scene_extraction/scene_extraction.py` — `SceneExtractor.extract_book()` has a `for idx, chapter in enumerate(chapters, start=1)` loop with `total_chapters = len(chapters)` available at the top — natural per-chapter checkpoint. Currently takes no progress callback.
- `backend/app/services/pipeline/pipeline_orchestrator.py`:
  - `_transition_stage()` (line ~1063) — called before each stage, writes `status` and `current_stage` to DB.
  - `_update_run_status()` (line ~394) — opens a fresh DB session and calls `PipelineRunRepository.update_status()`; safe to extend.
  - `_execute_extraction()` (line ~677) — calls `_extract_book_with_fresh_session()` via `run_in_executor` (runs in a thread pool); no loop visible at the orchestrator level today.
  - Per-scene ranking loop (line ~731): iterates `scenes_to_rank`, increments `stats.scenes_ranked` per scene — natural checkpoint.
  - Per-scene prompt loop for `DocumentTarget` (line ~950) and `SceneTarget` (line ~796): iterates scenes, increments `stats.prompts_generated` — natural checkpoint.
  - Image generation (line ~1043): calls `image_service.generate_for_selection()` with `prompt_ids`; total known upfront as `len(prompt_ids)`.
- `backend/app/services/image_generation/image_generation_service.py` — `generate_for_selection()` dispatches all tasks via `asyncio.gather()` with a semaphore (concurrency=3); individual images are generated in `_generate_single()` which is called once per prompt; currently takes no progress callback.
- `backend/app/schemas/pipeline_run.py` — `PipelineRunRead`; mirrors model fields; needs `stage_progress` added.
- `backend/app/api/routes/pipeline_runs.py` — thin GET/POST routes; no changes needed beyond schema pick-up.
- `backend/app/repositories/pipeline_run_repository.py` — `update_status()` is the write path; needs a `stage_progress` kwarg.
- `frontend/src/routes/_layout/documents.tsx` — polls `PipelineRunsApi.get(run.id)` every 3 s; `DocumentCard` renders `runSummary.current_stage`; this is where the progress breakdown will be rendered.

**Shape of `stage_progress`:**
```
{
  "extracting":          {"status": "running",   "items": 3,  "total": 12, "unit": "chapters"},
  "ranking":             {"status": "pending"},
  "generating_prompts":  {"status": "pending"},
  "generating_images":   {"status": "pending"}
}
```
- `status`: one of `pending | running | completed | failed`
- `items`: items completed so far within the stage (omitted when pending)
- `total`: expected total (omitted when not applicable)
- `unit`: display label for the counter — `"chapters"` for extraction (while running), `"scenes"` for ranking and prompts, `"images"` for image generation

After extraction completes the entry becomes `{"status": "completed", "items": 42, "unit": "scenes"}` — i.e. the final scene count, not chapter count, since that is the more meaningful output metric.

## Key Decisions

- **Separate column** (`stage_progress`) rather than a key inside `usage_summary`, to keep live mutable state separate from the final immutable snapshot.
- **Write frequency**: every scene during ranking and prompt-generation loops; every chapter during extraction (typical doc is 10–20 chapters, so write count is fine).
- **Extraction progress via callback**: `SceneExtractor.extract_book()` receives an optional `on_progress: Callable[[int, int], None] | None` parameter. The orchestrator creates a closure that opens a fresh DB session (matching the pattern of `_update_run_status`) and writes chapter progress. This avoids threading issues since the extractor runs in a thread pool executor.
- **Extraction completed state**: once extraction finishes, the entry switches from chapter-based progress to the final scene count (`{"status": "completed", "items": 42, "unit": "scenes"}`).
- **Image generation progress via callback**: `generate_for_selection()` (and `_generate_single()`) receives an optional `on_image_generated: Callable[[int, int], None] | None` callback. The orchestrator passes a closure with total captured as `len(prompt_ids)`. Since image generation is fully async (not a thread pool), the callback can call `_write_stage_progress` directly without a separate DB session. Counter will jump by up to 3 at a time due to the semaphore concurrency, which is expected.
- **Frontend layout**: replace the single stage-name line in `DocumentCard` with a 4-row compact breakdown. Keep the existing polling interval and transport unchanged.

## Implementation Plan

### Phase 1: Backend model, migration, and repository

**Goal**: Add `stage_progress` to the DB and the write path.

**Tasks**:
- Add `stage_progress: dict[str, Any]` (JSONB, nullable, default `None`) to `PipelineRun` in `backend/models/pipeline_run.py`
- Generate an Alembic migration: `cd backend && uv run alembic revision --autogenerate -m "add stage_progress to pipeline_runs"` and verify the generated file is correct
- Add `stage_progress: dict[str, Any] | None = None` kwarg to `PipelineRunRepository.update_status()` in `backend/app/repositories/pipeline_run_repository.py` and apply it to the model when provided
- Add a helper function `_build_stage_progress(stages: list[str]) -> dict` in `backend/app/services/pipeline/orchestrator_config.py` that returns a fresh progress dict with all four stage keys set to `{"status": "pending"}`

**Verification**:
- [ ] `uv run alembic upgrade head` applies cleanly
- [ ] `PipelineRun` has a `stage_progress` column in the DB

### Phase 2: Extraction progress callback

**Goal**: Surface per-chapter progress from the extraction service up to the orchestrator.

**Tasks**:
- Add optional `on_progress: Callable[[int, int], None] | None = None` parameter to `SceneExtractor.extract_book()` in `backend/app/services/scene_extraction/scene_extraction.py`
- At the end of each chapter iteration in the `for idx, chapter in enumerate(chapters, start=1)` loop, call `on_progress(idx, total_chapters)` if the callback is set
- Update `_extract_book_with_fresh_session()` in `pipeline_orchestrator.py` to accept and forward an `on_progress` callback
- In `_execute_extraction()`, create a closure for `on_progress` that opens a fresh DB session and writes `stage_progress["extracting"] = {"status": "running", "items": idx, "total": total_chapters, "unit": "chapters"}`; pass it through `run_in_executor` via `functools.partial`

**Verification**:
- [ ] Running extraction on a multi-chapter document writes incrementing chapter progress to `stage_progress` in DB

### Phase 3: Orchestrator writes for all other stages

**Goal**: Have the orchestrator populate `stage_progress` for ranking, prompts, and images.

**Tasks**:
- Add an optional `on_image_generated: Callable[[int, int], None] | None = None` parameter to `ImageGenerationService.generate_for_selection()` and forward it into `_generate_single()` in `backend/app/services/image_generation/image_generation_service.py`; call it after each image is successfully committed to the DB, passing `(images_done_so_far, total)`
- Add a `_write_stage_progress()` helper to `PipelineOrchestrator` in `pipeline_orchestrator.py` that accepts `run_id` and a partial progress dict and calls `_update_run_status()` with only the `stage_progress` kwarg updated (merge into existing column value)
- In `execute()`, initialise `stage_progress` to the all-pending dict when the run moves from `pending` to the first stage
- In `_transition_stage()`, mark the incoming stage as `{"status": "running"}` and the just-completed stage (if any) as `{"status": "completed"}` in `stage_progress`; for extraction completion write `{"status": "completed", "items": scene_count, "unit": "scenes"}`
- In the ranking loop (line ~731): after each successful `rank_scene()` call, call `_write_stage_progress()` with `ranking = {"status": "running", "items": stats.scenes_ranked, "total": len(scenes_to_rank), "unit": "scenes"}`
- In the prompt-generation loop for `DocumentTarget` (line ~950) and `SceneTarget` (line ~796): after each scene's prompts are generated, call `_write_stage_progress()` with `generating_prompts = {"status": "running", "items": stats.prompts_generated, "total": resolved_scene_count, "unit": "scenes"}`
- In `_execute_image_generation()`, create a closure for `on_image_generated` that captures `total = len(prompt_ids)` and calls `_write_stage_progress()` with `generating_images = {"status": "running", "items": done, "total": total, "unit": "images"}`; since this is async, no new session is needed
- In `_finalize_success()` and `_finalize_failure()`: mark the active stage as `completed` or `failed` in `stage_progress`

**Verification**:
- [ ] After a full run, `stage_progress` in the DB contains all four stage keys with `"completed"` status and non-zero item counts
- [ ] Querying the run mid-flight shows a `"running"` stage with incrementing `items`

### Phase 4: API schema and client regeneration

**Goal**: Expose `stage_progress` to the frontend.

**Tasks**:
- Add `stage_progress: dict[str, Any] | None = None` to `PipelineRunRead` in `backend/app/schemas/pipeline_run.py`
- Run `./scripts/generate-client.sh` to regenerate `openapi.json` and the frontend client
- Verify the generated `PipelineRunRead` type in `frontend/src/client` includes `stage_progress`

**Verification**:
- [ ] `GET /pipeline-runs/{run_id}` response includes `stage_progress`
- [ ] `cd frontend && npm run build` passes

### Phase 5: Frontend progress breakdown in DocumentCard

**Goal**: Show a compact per-stage breakdown in `DocumentCard` while a run is active.

**Tasks**:
- Create `frontend/src/components/Common/PipelineStageProgress.tsx` — a small component that accepts `stageProgress: Record<string, {status: string; items?: number; total?: number}> | null | undefined` and renders four labeled rows (Extraction, Ranking, Prompts, Images) each with a status icon and optional counter string
- Stage label map: `extracting` → "Extraction", `ranking` → "Ranking", `generating_prompts` → "Prompts", `generating_images` → "Images"
- Status icons/colors: `completed` → checkmark (green), `running` → arrow/spinner (blue), `failed` → cross (red), `pending` → circle (gray)
- Counter format: show `"3 / 12 chapters"` or `"18 / 42 scenes"` using the `unit` field when both `items` and `total` are present; show `"42 scenes"` when only `items`; show nothing when pending
- In `frontend/src/routes/_layout/documents.tsx`, replace the existing `Stage: {formatStageStatus(runSummary.current_stage)}` line with `<PipelineStageProgress stageProgress={runSummary.stage_progress} />` when `stage_progress` is present; fall back to the current text when it is absent (backward compatibility with older runs)

**Verification**:
- [ ] Active run shows 4-row breakdown; completed stages show checkmark and item count
- [ ] Completed/failed runs also show the final `stage_progress` snapshot
- [ ] `npm run lint` and `npm run build` pass

### Phase 6: Tests

**Goal**: Cover the new orchestrator writes and the updated schema.

**Tasks**:
- Add unit tests in `backend/app/tests/services/test_pipeline_orchestrator.py` (or create the file) that verify `stage_progress` is set correctly at stage transitions and after per-scene writes; mock `_update_run_status` to capture calls
- Add a test in `backend/app/tests/api/routes/test_pipeline_runs.py` asserting that `GET /pipeline-runs/{run_id}` returns `stage_progress` when set
- Add a repository test in `backend/app/tests/repositories/` verifying `update_status` persists `stage_progress`
- Run the full backend suite: `cd backend && uv run pytest`

**Verification**:
- [ ] All existing tests pass
- [ ] New tests cover stage-progress writes and the schema field

## Files to Modify

| File | Action |
|------|--------|
| `backend/models/pipeline_run.py` | Modify — add `stage_progress` JSONB column |
| `backend/alembic/versions/<new>.py` | Create — migration for new column |
| `backend/app/repositories/pipeline_run_repository.py` | Modify — add `stage_progress` kwarg to `update_status()` |
| `backend/app/services/pipeline/orchestrator_config.py` | Modify — add `_build_stage_progress()` helper |
| `backend/app/services/scene_extraction/scene_extraction.py` | Modify — add `on_progress` callback to `extract_book()` |
| `backend/app/services/image_generation/image_generation_service.py` | Modify — add `on_image_generated` callback to `generate_for_selection()` and `_generate_single()` |
| `backend/app/services/pipeline/pipeline_orchestrator.py` | Modify — add extraction callback, `_write_stage_progress()`, instrument stage transitions and per-scene loops |
| `backend/app/schemas/pipeline_run.py` | Modify — add `stage_progress` to `PipelineRunRead` |
| `frontend/openapi.json` | Regenerate |
| `frontend/src/client/` | Regenerate |
| `frontend/src/components/Common/PipelineStageProgress.tsx` | Create |
| `frontend/src/routes/_layout/documents.tsx` | Modify — render `PipelineStageProgress` in `DocumentCard` |
| `backend/app/tests/services/test_pipeline_orchestrator.py` | Create/Modify |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify |
| `backend/app/tests/repositories/test_pipeline_run_repository.py` | Create/Modify |

## Testing Strategy

- **Unit tests**: mock `_update_run_status` in orchestrator tests to assert `stage_progress` payload at each checkpoint; test `PipelineStageProgress` component renders correct icons and counters for each status value
- **Route test**: assert `stage_progress` key is present in `PipelineRunRead` response
- **Repository test**: assert `stage_progress` is persisted and round-trips through `update_status()`
- **Manual verification**: run a full pipeline on a test document and watch the documents view update every 3 seconds

## Acceptance Criteria

- [ ] `stage_progress` column exists on `pipeline_runs` and is populated during a run
- [ ] All four stage keys are present in `stage_progress` for the duration of a run (pending → running → completed/failed)
- [ ] Extraction stage shows incrementing chapter progress during execution
- [ ] Ranking and prompt-generation stages show incrementing `items` counts during execution
- [ ] `GET /pipeline-runs/{run_id}` returns `stage_progress`
- [ ] `DocumentCard` displays the 4-row stage breakdown while a run is active
- [ ] Completed and failed runs retain their final `stage_progress` snapshot
- [ ] All backend tests pass (`uv run pytest`)
- [ ] Frontend builds cleanly (`npm run build`)
- [ ] Backend lint passes (`uv run bash scripts/lint.sh`)

## Completion Notes

Implemented as planned across all 6 phases. Key implementation details:

**Phase 1** — Added `stage_progress: dict[str, Any] | None` (JSONB, nullable) to `PipelineRun` model. Wrote migration manually (`e5f7a8b9c012`) since DB was not running locally. Added `stage_progress` kwarg to `PipelineRunRepository.update_status()`. Added `build_stage_progress()` helper to `orchestrator_config.py`.

**Phase 2** — Added `on_progress: Callable[[int, int], None] | None = None` to `SceneExtractor.extract_book()` and `_extract_book_with_fresh_session()`. In `_execute_extraction()`, a closure `_on_extraction_progress` opens a fresh DB session per call to write chapter progress. After extraction completes, `self._stage_progress["extracting"]` is updated to the final scene count.

**Phase 3** — Added `_stage_progress: dict` instance variable and `_write_stage_progress()` method to `PipelineOrchestrator`. Initialized in `execute()` via `build_stage_progress()`. Updated `_transition_stage()` to mark the completed stage and set the new stage to `running` in `_stage_progress`. Added per-scene `_write_stage_progress` calls in ranking loop, both prompt generation loops (scene-targeted and document-targeted). Added `on_image_generated` callback to `ImageGenerationService.generate_for_selection()`, `_execute_tasks()` (with `asyncio.Lock` for atomic counter), flowing through from `_execute_image_generation()`. Updated all three finalize methods to mark active stage as `failed`/`completed` and pass `stage_progress` to the final DB write.

**Phase 4** — Added `stage_progress: dict[str, Any] | None = None` to `PipelineRunRead`. Regenerated client via `./scripts/generate-client.sh`.

**Phase 5** — Created `PipelineStageProgress.tsx` with 4-row compact breakdown (checkmark/arrow/cross/circle icons per status, counter format `"3 / 12 chapters"`). Updated `RunSummaryLike` type and `DocumentCard` to render `PipelineStageProgress` when `stage_progress` is present, falling back to the existing single-line stage text for older runs.

**Phase 6** — Added `TestStageProgress` class to `test_pipeline_orchestrator.py` with 5 tests covering initialization, success completion, exception failure, all-four-stages run, and helper function. Added `test_pipeline_run_repository_stage_progress` to `test_core_domain_repositories.py`. Added `test_get_pipeline_run_returns_stage_progress` to `test_pipeline_runs.py`.

**Deviations from plan**: Minor — the `_update_run_status` helper function signature was also updated to accept `stage_progress` (the plan implied this implicitly). The `_finalize_success` logic for marking the last running stage as completed was slightly richer than described (preserves existing items/total/unit fields, only overwrites the status key).
