# Auto-Complete Extraction/Ranking Stages Before Pipeline Launch

## Overview
When a user clicks "Run Pipeline", the backend should automatically synchronize document stage statuses (extraction and ranking) before deciding which stages to skip. This ensures old pipeline runs whose data is actually complete get their statuses updated so the pipeline can skip straight to prompt/image generation.

## Problem Statement
After adding the `extraction_status` and `ranking_status` fields to the Document model, existing documents that were fully extracted and ranked before the migration still show non-completed statuses (e.g. `pending`). The frontend's `shouldLaunchImageGenerationOnly()` check requires both stages to be `"completed"` before setting `skip_extraction=true` and `skip_ranking=true`. As a result, clicking "Run Pipeline" re-runs extraction and ranking even though all the data already exists.

The `sync_document_stage_statuses()` call that recomputes these statuses only runs at the **end** of a pipeline run (`_execute_pipeline_run` lines 617-620), so documents from pre-migration runs never get synced unless a full pipeline completes for them again.

## Proposed Solution
1. **Sync at pipeline start**: Call `DocumentStageStatusService.sync_document()` in `PipelineRunStartService.resolve_pipeline_request()` before the skip-flag resolution logic runs. This ensures the Document record reflects actual data state, so the existing auto-detect logic in `_run_full_pipeline` works correctly.
2. **Bulk sync endpoint**: Add a `POST /documents/sync-stages` endpoint that iterates all documents and calls `sync_document()` for each. This fixes all existing documents without requiring individual pipeline launches.
3. **Application startup hook**: Call the bulk sync on app startup so the fix is automatically applied when the backend restarts.

## Codebase Research Summary

### Key patterns found
- `DocumentStageStatusService.sync_document()` already computes correct extraction/ranking statuses from source-of-truth records (scenes and rankings in DB). It handles `pending`, `completed`, `stale`, and preserves `failed` states.
- `_apply_document_stage_update_for_run()` in `pipeline_runs.py` shows the pattern for looking up a document from a run and applying a status service update.
- `PipelineRunStartService.resolve_pipeline_request()` is the entry point that resolves skip flags and creates the PipelineRun record. This is where the sync should happen — before lines 79-106 that evaluate `should_skip_extraction`.
- The frontend's `documentsLaunch.ts:shouldLaunchImageGenerationOnly()` checks `status === "completed"` on both stages to decide skip flags.

### Files affected
- `backend/app/services/pipeline/pipeline_run_start_service.py` — add sync call before skip-flag resolution
- `backend/app/services/pipeline/document_stage_status_service.py` — add `sync_all_documents()` bulk method
- `backend/app/api/routes/documents.py` — add `POST /documents/sync-stages` endpoint
- `backend/app/main.py` — add startup event to trigger bulk sync
- Test files for the above

### Similar features as reference
- `_sync_document_stage_statuses()` in `pipeline_runs.py` (lines 317-341) — existing pattern for calling `sync_document` on a single document via a helper
- `DocumentStageStatusService.sync_document()` (lines 117-168) — already does the heavy lifting
- `DocumentDashboardService.list_entries()` — shows pattern for iterating all documents

## Key Decisions
- **Backend only**: The frontend will not be changed. The backend sync ensures document statuses are correct before the frontend ever queries them, so the existing `shouldLaunchImageGenerationOnly()` check works naturally.
- **Sync at pipeline start**: The sync runs in `resolve_pipeline_request()` before skip-flag evaluation, ensuring the Document record matches reality before any decisions are made.
- **Bulk sync + startup**: A one-time bulk sync fixes all historical data. Running it on startup means deploying the update is sufficient — no manual intervention needed.

## Implementation Plan

### Phase 1: Sync at Pipeline Start
**Goal**: Ensure document stage statuses are current before evaluating skip flags.

**Tasks**:
- Add a `sync_document()` call in `PipelineRunStartService.resolve_pipeline_request()` after resolving `resolved_document` (around line 72) but before evaluating `should_skip_extraction` (line 79). Only call sync when `resolved_document` is not None.
- The sync call should use the existing `DocumentStageStatusService(session).sync_document(document=resolved_document)` pattern followed by a `session.flush()` so skip-flag logic sees updated values.

**Verification**:
- [ ] Unit test: pipeline start request with a document whose `extraction_status="pending"` but has complete extraction data results in `skip_extraction=True` in the resolved args
- [ ] Unit test: pipeline start request with a document whose `ranking_status="pending"` but has full rankings results in `skip_ranking=True` in the resolved args
- [ ] Existing `test_pipeline_run_start_service.py` tests still pass

### Phase 2: Bulk Sync Method
**Goal**: Provide a reusable method that syncs all documents' stage statuses.

**Tasks**:
- Add `sync_all_documents()` method to `DocumentStageStatusService` that queries all Document records and calls `sync_document()` for each, committing once at the end.
- The method should return a count of documents synced for logging/response purposes.

**Verification**:
- [ ] Unit test: `sync_all_documents()` updates multiple documents with stale statuses to correct values
- [ ] Unit test: documents already in correct state are not broken by re-syncing

### Phase 3: Bulk Sync Endpoint + Startup Hook
**Goal**: Make bulk sync accessible via API and automatic on startup.

**Tasks**:
- Add `POST /documents/sync-stages` route in `backend/app/api/routes/documents.py` that calls `sync_all_documents()` and returns `{"synced": N}`.
- Add a `lifespan` or `startup` event in `backend/app/main.py` that calls `sync_all_documents()` on app boot. Use `Session(engine)` directly (same pattern as background tasks in `pipeline_runs.py`).

**Verification**:
- [ ] Route test: POST `/documents/sync-stages` returns 200 with synced count
- [ ] Manual: restart backend, verify documents dashboard shows correct statuses
- [ ] Manual: click "Run Pipeline" on a document with existing extraction+ranking data, verify it skips to prompt/image generation

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/pipeline/pipeline_run_start_service.py` | Modify — add sync_document call before skip-flag resolution |
| `backend/app/services/pipeline/document_stage_status_service.py` | Modify — add sync_all_documents() method |
| `backend/app/api/routes/documents.py` | Modify — add POST /documents/sync-stages endpoint |
| `backend/app/main.py` | Modify — add startup hook to call sync_all_documents() |
| `backend/app/tests/services/test_pipeline_run_start_service.py` | Modify — add tests for sync-before-skip behavior |
| `backend/app/tests/services/test_document_stage_status_service.py` | Modify — add tests for sync_all_documents() |
| `backend/app/tests/api/routes/test_documents.py` | Modify — add test for sync-stages endpoint |

## Testing Strategy
- **Unit Tests**: Test sync-at-start in `test_pipeline_run_start_service.py` by providing documents with stale statuses and verifying skip flags are correctly resolved after sync. Test bulk sync in `test_document_stage_status_service.py` with multiple documents in varying states.
- **Route Tests**: Test the new `POST /documents/sync-stages` endpoint returns correct response.
- **Manual Verification**: After deploying, check the documents dashboard shows correct stage statuses for all existing documents. Click "Run Pipeline" on a fully-extracted/ranked document and verify it shows "Generate images for scenes" label and skips to prompt generation.

## Acceptance Criteria
- [ ] All existing tests pass
- [ ] New tests cover sync-at-start behavior and bulk sync
- [ ] Linting passes (`uv run bash scripts/lint.sh`)
- [ ] Documents with complete extraction/ranking data show "completed" status on dashboard after backend restart
- [ ] "Run Pipeline" skips extraction and ranking for documents that are already complete
