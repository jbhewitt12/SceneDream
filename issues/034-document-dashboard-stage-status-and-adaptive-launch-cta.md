# Add Document Stage Statuses and Adaptive Dashboard CTA

## Overview
Make the Documents dashboard stage indicators explicit and reliable by persisting extraction/ranking stage status in the database, then drive the launch button label/behavior from those statuses.

## Problem Statement
The dashboard currently marks stages complete when counts are greater than zero, which does not reliably mean the stage is fully complete. This creates UX ambiguity:
- users cannot clearly tell if extraction/ranking is fully done
- the CTA always says "Run pipeline", even when the practical action is "generate more images", once extraction and ranking are complete
- users are not explicitly told image generation picks highest-ranked scenes without images

## Proposed Solution
Add document-level stage fields for extraction and ranking, keep them synchronized with pipeline execution and data coverage, and update dashboard UI logic:
- persist extraction/ranking stage status in `documents`
- recompute/synchronize stage status after terminal pipeline runs
- return stage status metadata in `/documents/dashboard`
- switch CTA text:
  - `Run pipeline` when extraction/ranking is not complete
  - `Generate images for scenes` when extraction and ranking are complete
- show helper text explaining image selection behavior (highest-ranked scenes that do not yet have images)

## Codebase Research Summary

### Current dashboard behavior
- `DocumentDashboardService` sets stage booleans from `count > 0` rather than true completion.
- Frontend card CTA is always `Run pipeline`.

### Existing pipeline signals we can reuse
- Pipeline usage summary already records outputs (`scenes_extracted`, `scenes_ranked`, etc.).
- Pipeline run diagnostics track stage transitions and terminal state.
- Pipeline flow already auto-detects extraction/ranking completeness for skip decisions.

### Existing image-selection behavior
- Image generation already selects top-ranked scenes while skipping scenes that already have images, so UI copy can reflect current backend behavior.

## Key Decisions
- Use explicit string statuses (not booleans) for extraction/ranking: `pending`, `running`, `completed`, `failed`, `stale`.
- Add completion timestamps and error fields for extraction/ranking.
- Use a shared "stage status sync" service to recompute correctness from source-of-truth data and avoid drift.
- Keep legacy dashboard compatibility for rows without `document_id` by using existing fallback logic.

## Implementation Plan

### Phase 1: Add stage fields to canonical documents
**Goal**: Persist extraction/ranking lifecycle in DB.

**Tasks**:
- Add columns to `documents` model via Alembic migration:
  - `extraction_status`, `extraction_completed_at`, `extraction_error`
  - `ranking_status`, `ranking_completed_at`, `ranking_error`
- Default new statuses to `pending`.
- Update SQLModel + Pydantic schemas to expose the new fields where appropriate.

**Verification**:
- [ ] Migration applies cleanly on existing DB
- [ ] New documents receive default stage values
- [ ] Schema serialization includes new stage fields

### Phase 2: Introduce a stage status synchronization service
**Goal**: Centralize status correctness and prevent inconsistent writes.

**Tasks**:
- Create a service (for example `document_stage_status_service.py`) that computes:
  - extraction completeness (full coverage semantics)
  - ranking completeness (all extracted scenes have ranking coverage)
  - stale state when extraction coverage advances beyond ranking coverage
- Add a method to persist computed status + timestamps/errors for a document.
- Reuse existing extraction/ranking completeness heuristics already used by pipeline auto-skip logic.

**Verification**:
- [ ] Service returns deterministic status for complete/partial/failed/stale scenarios
- [ ] Persisted statuses match computed status for seeded test data

### Phase 3: Wire pipeline run lifecycle to stage fields
**Goal**: Keep document stage status aligned with runtime progress.

**Tasks**:
- Update pipeline run execution flow to set stage status transitions:
  - stage start: set relevant stage to `running`
  - terminal success/failure: recompute + persist extraction/ranking statuses using sync service
- Ensure failure paths update the right stage error field and preserve already-completed stage state.
- Ensure reruns that add new extractions can mark ranking `stale` as needed.

**Verification**:
- [ ] Successful full run ends with extraction/ranking marked `completed`
- [ ] Failure during extraction marks extraction `failed`
- [ ] Failure during ranking leaves extraction complete and marks ranking `failed`
- [ ] New extraction progress after prior completion can mark ranking `stale`

### Phase 4: Update dashboard API aggregation to use stage fields
**Goal**: Return explicit stage state to frontend.

**Tasks**:
- Extend `DocumentDashboardStages` (or add a dedicated nested schema) to include status metadata instead of only booleans.
- Update dashboard aggregation to prefer persisted stage statuses for canonical documents.
- Keep fallback behavior for legacy/non-canonical entries (`document_id is None`).
- Add any derived metrics needed by UI (for example ranked-without-images remaining count if needed for CTA helper/disable state).

**Verification**:
- [ ] `/api/v1/documents/dashboard` returns explicit extraction/ranking statuses
- [ ] Legacy rows still render without backend errors
- [ ] Existing count fields remain accurate

### Phase 5: Update frontend dashboard UX and CTA behavior
**Goal**: Make action intent obvious and aligned with stage completion.

**Tasks**:
- Update API types and card rendering to consume new stage status payload.
- Replace current boolean-complete assumptions with explicit status badges.
- Update launch button label logic:
  - show `Run pipeline` if extraction or ranking status is not `completed`
  - show `Generate images for scenes` when both are `completed`
- Add helper copy under CTA:
  - "Generates images for the highest-ranked scenes that do not already have images."
- Optional disable state:
  - disable CTA when no ranked scenes remain without images and show explanatory text.

**Verification**:
- [ ] Button label changes correctly across status states
- [ ] Status badges show pending/running/completed/failed/stale clearly
- [ ] Helper copy appears when CTA is in image-generation mode

### Phase 6: Backfill and compatibility hardening
**Goal**: Ensure existing data is upgraded safely.

**Tasks**:
- Add a one-time backfill path (migration-time script or startup-safe sync command) to initialize stage statuses for existing documents.
- Validate behavior for documents with missing source files but existing extracted scenes.
- Ensure pipeline start validation and skip logic continue to work after new fields are introduced.

**Verification**:
- [ ] Existing documents get sensible initial stage states
- [ ] No regressions in pipeline launch behavior for legacy records

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/alembic/versions/<new_revision>_add_document_stage_status_fields.py` | Create |
| `backend/models/document.py` | Modify |
| `backend/app/schemas/document.py` | Modify |
| `backend/app/services/document_dashboard_service.py` | Modify |
| `backend/app/services/pipeline/pipeline_run_start_service.py` | Modify (if needed for status preflight/sync calls) |
| `backend/app/api/routes/pipeline_runs.py` | Modify |
| `backend/app/services/image_gen_cli.py` | Refactor shared completeness logic (extract/reuse) |
| `backend/app/services/<new_or_existing_stage_sync_service>.py` | Create/Modify |
| `backend/app/tests/services/test_document_dashboard_service.py` | Modify |
| `backend/app/tests/api/routes/test_documents.py` | Modify |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify |
| `backend/app/tests/services/test_pipeline_run_start_service.py` | Modify (if behavior changes) |
| `frontend/src/api/documents.ts` | Modify |
| `frontend/src/routes/_layout/documents.tsx` | Modify |

## Testing Strategy
- Backend automated tests:
  - Add/extend service tests for status synchronization logic (`pending/running/completed/failed/stale`)
  - Extend pipeline run route tests to assert stage field updates on success and failure paths
  - Extend dashboard route/service tests to assert new stage payload and CTA-driving semantics
- Run full backend test suite:
  - `cd backend && uv run pytest`
- Frontend static checks:
  - `cd frontend && npm run lint`

### Required frontend manual verification (Agent Browser)
The implementing Codex agent must perform browser validation with the Agent Browser plugin/skill on at least one short story from `example_docs/` (for example `example_docs/W_W_Jacobs-The_Monkeys_Paw.epub` or `example_docs/E_A_Poe-The_Cask_of_Amontillado.md`).

Required manual flow:
- Ensure the selected `example_docs` short story appears in the Documents dashboard.
- Validate CTA shows `Run pipeline` when extraction/ranking are not complete.
- Run pipeline (or seed stage state if API credentials are unavailable) until extraction/ranking are complete.
- Validate CTA changes to `Generate images for scenes`.
- Validate helper text explicitly states highest-ranked scenes without images are selected.
- Capture screenshots of:
  - pre-completion CTA state
  - post-completion CTA state

## Acceptance Criteria
- [ ] Extraction and ranking stage fields are persisted on `documents`
- [ ] Pipeline execution updates stage fields consistently for success/failure/stale transitions
- [ ] Dashboard API exposes explicit stage statuses used by frontend
- [ ] Documents dashboard CTA changes from `Run pipeline` to `Generate images for scenes` when extraction+ranking are complete
- [ ] UI explains that image generation targets highest-ranked scenes without images
- [ ] Legacy/partial data scenarios continue to work without crashes
- [ ] `cd backend && uv run pytest` passes
- [ ] Frontend manual verification is completed with Agent Browser on a short story from `example_docs` and screenshots are captured
