# End-to-End Error Propagation and Frontend Surfacing

## Overview

Introduce a single, explicit error propagation contract from backend services through FastAPI routes, the generated frontend client, and UI error surfaces so users see the closest useful error message instead of a generic wrapper like `Bad Request` or `Failed to start ...`.

## Problem Statement

The current stack loses error fidelity in multiple places:

- Backend route handlers often catch an exception, log it, and replace it with a generic `HTTPException(detail="Failed to ...")`.
- The generated frontend client throws `ApiError` instances with status-text messages such as `Bad Request` instead of the backend payload.
- Several frontend screens read `error.message` directly, so they show the client wrapper instead of the backend detail.
- Async pipeline failures are somewhat better because they persist `error_message`, but that path still flattens errors into a single truncated string and does not expose structured cause data to the frontend.

As a result, users frequently see a message that is one or two abstraction layers above the real failure. That slows debugging, makes retries feel random, and undermines the point of having route-specific and domain-specific exceptions.

## Proposed Solution

Add a canonical app-level error envelope for non-2xx API responses, centralize backend exception translation, preserve root-cause messages across service and orchestrator boundaries, and centralize frontend error extraction so every toast, banner, and inline error view uses the same logic.

The target behavior is:

- If the backend already has a safe, specific error message, the frontend shows that exact message.
- If a service wraps an exception for context, it preserves the original message and cause chain.
- If a failure happens inside a background pipeline run, polling returns both the legacy flat error string and structured failure metadata.
- If a failure is unexpected and unsafe to expose verbatim, the backend returns a stable generic message plus a machine-readable code and log correlation handle.

## Codebase Research Summary

### Backend route boundaries currently discard specific errors

The following routes replace the caught exception with generic detail strings:

- `backend/app/api/routes/pipeline_runs.py`
  - `start_pipeline_run()` returns `detail="Failed to start pipeline run"` when `spawn_background_task()` fails.
- `backend/app/api/routes/scene_extractions.py`
  - `generate_for_scene()` returns `detail="Failed to start scene generation"` on task spawn failure.
- `backend/app/api/routes/generated_images.py`
  - `remix_generated_image()` returns `detail="Failed to start remix generation"`.
  - `custom_remix_generated_image()` returns `detail="Custom remix prompt creation failed"` and `detail="Failed to start custom remix generation"` for unexpected failures.
  - `crop_image()` returns `detail="Failed to save cropped image"` for write failures.
- `backend/app/api/routes/image_prompts.py`
  - `generate_metadata_variants()` collapses both domain and unexpected failures to `detail="Failed to generate metadata variants"`.

There are also some routes that already preserve the message correctly via `detail=str(exc)` or `detail=exc.detail`, for example settings validation and parts of generated-images. The error-handling behavior is therefore inconsistent across the API surface.

### There is no shared app-level API error schema today

- `backend/app/schemas/common.py` only defines `Message`.
- The OpenAPI-generated frontend types expose `HTTPValidationError` with `detail?: Array<ValidationError>` in `frontend/src/client/types.gen.ts`.
- There is no typed app error response for route-level domain failures or internal errors.

This means the frontend can only infer error shape heuristically.

### The generated frontend client prefers status labels over server detail

In `frontend/src/client/core/request.ts`, `catchErrorCodes()` throws:

- `new ApiError(..., "Bad Request")` when the status is declared in `options.errors`
- a generic synthesized message containing status and serialized body otherwise

That behavior discards useful server messages for many common 4xx/5xx responses before the UI ever sees them.

### Frontend error extraction is duplicated and incomplete

Current patterns include:

- `frontend/src/routes/_layout/documents.tsx`
  - local `getApiErrorMessage()` reads `body.detail` only when it is a string
  - query error banners still use `settingsQuery.error.message` and `dashboardQuery.error.message`
- `frontend/src/routes/_layout/extracted-scenes.tsx`
  - same local helper duplication
  - list query error state uses `listQuery.error.message`
- `frontend/src/routes/_layout/generated-images.tsx`
  - several mutation handlers call `showErrorToast(error.message)` directly
- `frontend/src/routes/_layout/settings.tsx`
  - all mutation handlers use `error.message`
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`
  - crop errors use `error.message`
- `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx`
  - generation and update failures use `err.message`
- `frontend/src/utils.ts`
  - `handleError()` only supports `detail` string or validation array first item
- `frontend/src/routes/_layout/scene-rankings.tsx`
  - not individually verified during research, but expected to follow the same `error.message` pattern as `generated-images.tsx` and `settings.tsx`

The net effect is that some screens show the backend message, while others show the client wrapper.

### Pipeline runs already contain useful failure state, but only as flattened strings

`backend/app/services/pipeline/pipeline_orchestrator.py` already does useful work:

- `_format_failure_message()` converts an exception to a bounded string
- `RunDiagnosticsTracker.finalize()` stores `diagnostics["error"] = { code, message, stage }`
- `build_usage_summary()` stores `errors.code` and `errors.messages`
- terminal status writes persist `run.error_message`

However:

- the primary surfaced field is still a single `error_message` string
- structured diagnostics are buried in `usage_summary`/`diagnostics`
- messages are truncated repeatedly
- cause chains are not preserved in a structured way
- document-level stage failures also collapse to a bounded string in `document_stage_status_service.py`

This path is close to what we want, but not yet normalized for frontend use.

### Existing tests codify some of the generic behavior

The following tests currently expect wrapper messages:

- `backend/app/tests/api/routes/test_pipeline_runs.py`
- `backend/app/tests/api/routes/test_scene_extractions.py`
- `backend/app/tests/api/routes/test_generated_images.py`
- `backend/app/tests/api/routes/test_image_prompts.py`

Any implementation will need to update those expectations deliberately rather than treat them as incidental breakage.

## Key Decisions

- **Use a canonical app error envelope** for route-generated non-2xx responses.
  - Proposed shape inside `detail`:
    - `code: str`
    - `message: str`
    - `cause_messages: list[str]`
    - `stage: str | None`
    - `run_id: UUID | None`
    - `metadata: dict[str, Any]`
- **Preserve FastAPI validation responses as-is**.
  - Frontend extraction must handle three detail shapes:
    - validation array
    - legacy string
    - new structured object
- **Prefer exact root-cause messages when safe**.
  - Expected domain/provider/configuration failures should surface the specific message.
  - Only unexpected internal failures that could leak sensitive internals should be redacted.
  - **Unsafe messages** include those containing: stack traces, database connection strings, internal file paths, credentials or secrets, third-party API keys, or raw SQL. Provider error messages that only describe a configuration or content issue (e.g., "model not found", "content policy violation") are generally safe.
- **Keep backward compatibility during rollout**.
  - Existing `error_message` string fields stay in place for now.
  - New structured fields are additive.
- **Centralize extraction on both sides**.
  - Backend gets one exception-to-response translator.
  - Frontend gets one `getDisplayErrorMessage()` helper.

## Implementation Plan

### Phase 1: Define the backend error contract

**Goal**: Create shared typed models for app-level errors.

**Tasks**:
- Add error schemas to `backend/app/schemas/common.py`, for example:
  - `ApiErrorDetail`
  - `ApiErrorResponse`
- Export them from `backend/app/schemas/__init__.py`
- Decide whether the API contract uses:
  - `{"detail": "legacy string"}` for untouched routes
  - `{"detail": {...structured detail...}}` for migrated routes
- Document the detail-shape compatibility rule in the schema docstrings

**Verification**:
- [ ] Common error schemas are importable and used in route annotations where applicable
- [ ] OpenAPI shows the new app error shape for migrated endpoints

### Phase 2: Centralize backend exception translation

**Goal**: Stop writing ad hoc generic `HTTPException` wrappers in each route.

**Tasks**:
- Create a backend error translator module, for example `backend/app/api/errors.py`
- Add helpers to:
  - unwrap `__cause__` / `__context__`
  - classify stable error codes
  - decide whether a root-cause message is safe to expose
  - build `HTTPException` or `JSONResponse` payloads with the shared error shape
- Register app-level exception handlers in `backend/app/main.py` where useful
- For routes that still need local translation, replace generic `detail="Failed to ..."` responses with the shared helper

**Verification**:
- [ ] Generic route-level wrapper strings are removed from migrated endpoints
- [ ] Backend logs still retain full exception context

### Phase 3: Normalize service and orchestrator wrapping rules

**Goal**: Ensure wrapped exceptions keep the real cause.

**Tasks**:
- Audit service-layer `except Exception as exc` blocks in:
  - `backend/app/services/image_prompt_generation/`
  - `backend/app/services/scene_ranking/`
  - `backend/app/services/image_generation/`
  - `backend/app/services/books/`
  - `backend/app/services/prompt_metadata/`
- For service-level wrappers:
  - keep `raise ... from exc`
  - preserve the underlying message unless it is unsafe
  - prefer typed domain exceptions over bare `RuntimeError` or generic wrapper text
- Add a small helper for extracting cause chains to avoid hand-written repetition

**Verification**:
- [ ] Wrapped exceptions preserve cause chains
- [ ] Domain errors retain the provider/config/configuration message where appropriate

### Phase 4: Expose structured pipeline failure data

**Goal**: Make async pipeline errors first-class and frontend-friendly.

**Tasks**:
- Extend `PipelineRunRead` in `backend/app/schemas/pipeline_run.py` with a structured failure field, for example:
  - `error: ApiErrorDetail | None`
  - or `failure: PipelineRunFailure | None`
- Update orchestrator finalization in `backend/app/services/pipeline/pipeline_orchestrator.py` to persist:
  - best display message
  - cause message chain
  - stable error code
  - observed stage
- Keep `error_message` for compatibility, but define it as the top-level display string derived from the structured failure
- **Out of scope**: Document dashboard stage cards are out of scope for this implementation. The existing `error_message` string on stage status is sufficient. Structured stage-level errors can be added in a follow-up.

**Verification**:
- [ ] `GET /pipeline-runs/{run_id}` includes structured failure metadata
- [ ] Polling clients can render the exact failure without reading logs

### Phase 5: Fix the generated frontend client error message behavior

**Goal**: Ensure the frontend surfaces backend error payloads correctly.

**Tasks**:
- Do not edit `frontend/src/client/core/request.ts` — it is auto-generated and will be overwritten on every `./scripts/generate-client.sh` run.
- The shared frontend helper (`getDisplayErrorMessage()`) reads `error.body.detail` directly from `ApiError.body`, which already contains the full response payload. `ApiError.message` (the HTTP status label) will not be used after every call site adopts the helper.
- The helper must handle all three detail shapes in `ApiError.body`:
  1. `detail.message` when `detail` is an object (new structured shape)
  2. `detail` when it is a string (legacy shape)
  3. first validation message when `detail` is an array (FastAPI validation shape)
  4. fallback to a caller-supplied default message

**Verification**:
- [ ] The shared helper correctly extracts backend detail from `ApiError.body` for all three shape variants
- [ ] Validation errors still render correctly

### Phase 6: Centralize frontend error extraction and UI usage

**Goal**: Remove per-screen error parsing drift.

**Tasks**:
- Create a shared helper, for example `frontend/src/utils/apiErrors.ts`
- Replace the duplicated local helpers in:
  - `frontend/src/routes/_layout/documents.tsx`
  - `frontend/src/routes/_layout/extracted-scenes.tsx`
- Update mutation and query error surfaces in:
  - `frontend/src/routes/_layout/generated-images.tsx`
  - `frontend/src/routes/_layout/settings.tsx`
  - `frontend/src/routes/_layout/scene-rankings.tsx`
  - `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`
  - `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx`
  - `frontend/src/utils.ts`
- Standardize on one rule:
  - if backend sent a concrete message, show it
  - otherwise show the local fallback

**Verification**:
- [ ] No UI error surface relies directly on raw `error.message` without using the shared extractor
- [ ] Toasts, banners, and inline messages all display the same backend message for the same failure

### Phase 7: Regenerate client and update tests

**Goal**: Lock in the contract.

**Tasks**:
- Run `./scripts/generate-client.sh` after backend schema changes
- Update backend route tests to assert the new error shape or more specific message
- Add service-level tests for the cause-chain extraction and translation helper
**Verification**:
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npm run build` passes

**Note**: No frontend unit test infrastructure exists in this repo. Frontend error extractor coverage is deferred to a separate initiative. TypeScript build and lint passing are sufficient for this phase.

## Files to Modify

| File | Action |
|------|--------|
| `backend/app/schemas/common.py` | Modify — add app error schemas |
| `backend/app/schemas/__init__.py` | Modify — export app error schemas |
| `backend/app/api/errors.py` | Create — shared exception translation helpers |
| `backend/app/main.py` | Modify — register exception handlers if used |
| `backend/app/api/routes/pipeline_runs.py` | Modify — replace generic wrapper handling |
| `backend/app/api/routes/scene_extractions.py` | Modify — replace generic wrapper handling |
| `backend/app/api/routes/generated_images.py` | Modify — replace generic wrapper handling |
| `backend/app/api/routes/image_prompts.py` | Modify — replace generic wrapper handling |
| `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` | Modify — preserve cause chain, use typed domain exceptions |
| `backend/app/services/scene_ranking/scene_ranking_service.py` | Modify — preserve cause chain, use typed domain exceptions |
| `backend/app/services/image_generation/image_generation_service.py` | Modify — preserve cause chain, use typed domain exceptions |
| `backend/app/services/books/` (relevant loader files) | Modify — preserve cause chain |
| `backend/app/services/prompt_metadata/` (relevant service files) | Modify — preserve cause chain |
| `backend/app/services/pipeline/pipeline_orchestrator.py` | Modify — persist structured failure data |
| `backend/app/services/pipeline/document_stage_status_service.py` | Modify — align stored stage error behavior |
| `backend/app/schemas/pipeline_run.py` | Modify — expose structured pipeline failure data |
| `frontend/src/client/core/request.ts` | No change needed — auto-generated file, overwritten on every `generate-client.sh` run |
| `frontend/src/client/types.gen.ts` | Regenerate |
| `frontend/src/utils/apiErrors.ts` | Create — shared frontend extraction helpers |
| `frontend/src/routes/_layout/documents.tsx` | Modify — use shared extractor everywhere |
| `frontend/src/routes/_layout/extracted-scenes.tsx` | Modify — use shared extractor everywhere |
| `frontend/src/routes/_layout/generated-images.tsx` | Modify — use shared extractor everywhere |
| `frontend/src/routes/_layout/settings.tsx` | Modify — use shared extractor everywhere |
| `frontend/src/routes/_layout/scene-rankings.tsx` | Modify — use shared extractor everywhere |
| `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` | Modify — use shared extractor |
| `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx` | Modify — use shared extractor |
| `frontend/src/utils.ts` | Modify — either remove or delegate `handleError()` |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify |
| `backend/app/tests/api/routes/test_scene_extractions.py` | Modify |
| `backend/app/tests/api/routes/test_generated_images.py` | Modify |
| `backend/app/tests/api/routes/test_image_prompts.py` | Modify |
| `backend/app/tests/services/` | Add or update tests for error translation helpers |

## Testing Strategy

- **Backend route tests**: assert that expected domain failures surface the specific underlying message and stable error code
- **Backend service tests**: verify cause-chain extraction and safe/unsafe exposure logic
- **Pipeline tests**: verify failed runs expose both legacy `error_message` and structured failure metadata
- **Frontend tests**: No frontend unit test infrastructure exists in this repo. Frontend error extractor coverage is deferred to a separate initiative. TypeScript build (`npm run build`) and lint passing are the verification gates.
- **Manual verification**:
  - trigger a known validation failure
  - trigger a known provider/config failure
  - trigger a background pipeline failure
  - confirm the same concrete message appears in the toast/banner without reading logs

## Acceptance Criteria

- [ ] Migrated API endpoints no longer replace specific caught exceptions with generic `Failed to ...` messages
- [ ] There is a shared typed app-level error payload for non-validation API failures
- [ ] All frontend error surfaces use one shared extraction helper that reads `ApiError.body.detail` directly
- [ ] Background pipeline polling surfaces structured failure data, not only a flat string
- [ ] Expected user-safe root-cause messages are shown verbatim in the frontend
- [ ] Unexpected unsafe internal failures return a stable generic message plus code/error identifier
- [ ] Backend route tests are updated to assert the new behavior
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npm run build` passes
