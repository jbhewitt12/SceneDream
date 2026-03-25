# Fail Fast on Extraction Setup Errors and Show Remediation in the Pipeline View

## Overview

Follow up the general error-propagation work with a narrower fix for first-run extraction failures.

When extraction hits a common setup problem such as a missing key, invalid key, no credits, quota exhaustion, or model-access error, the pipeline should fail immediately instead of silently skipping chunks and drifting to a misleading completed state. The pipeline status area in the Documents view should then show a clear explanation of the actual problem and what the user needs to do next.

## Problem Statement

Right now the extraction stage treats every chunk-level provider error as recoverable. That is the wrong behavior for first-run setup failures:

- A user with no OpenAI credits can launch a document run.
- The first extraction request can fail with a provider error.
- Extraction logs the failure and continues to the next chunk.
- If every chunk fails, the orchestrator can still finish the run without a terminal failure because no stage exception escaped and no `stats.errors` entry was recorded.
- The frontend can therefore show a successful or empty run instead of a useful failure.

This is especially bad for onboarding because extraction is the first expensive stage, it is the first place setup mistakes are likely to surface, and the current UI does not consistently tell the user what to fix.

The core user experience we want is:

- The first fatal extraction setup error stops the run.
- The pipeline run is marked `failed`.
- The pipeline status area shows the real error.
- The UI includes an actionable fix, for example "Add credits to your OpenAI API account and rerun."

## Proposed Solution

Introduce explicit classification for extraction-stage provider errors and split them into two buckets:

- **Fatal setup/access errors**: fail the extraction stage immediately on the first occurrence.
- **Recoverable chunk errors**: keep the existing best-effort continue behavior.

Fatal setup/access errors should include at least:

- no usable provider credentials
- invalid or revoked API key
- authentication failure
- insufficient credits / insufficient quota
- model access denied or unsupported model for the current account
- exhausted rate-limit retries when the provider message clearly indicates quota or account-level throttling rather than a malformed single chunk

When one of those errors occurs:

1. the extraction service raises a typed exception instead of continuing
2. the orchestrator records a structured failure payload with a stable code and remediation metadata
3. the Documents pipeline status view renders both the failure message and a user-action hint
4. the failure toast uses the same display message

Recoverable errors such as malformed single-chunk model output can remain best-effort if we still want extraction to salvage the rest of the document.

## Codebase Research Summary

### Extraction currently swallows provider failures per chunk

`SceneExtractor._extract_chapter_scenes()` catches every exception from the provider call and continues to the next chunk:

- `backend/app/services/scene_extraction/scene_extraction.py`

That means setup failures such as invalid credentials or exhausted credits are currently treated the same way as a one-off parse problem.

### The orchestrator only fails when an exception escapes or `stats.errors` is populated

`PipelineOrchestrator.execute()` only finalizes a failed run when:

- a stage raises an exception, or
- `stats.errors` contains entries at the end of execution

Since chunk-level extraction failures are swallowed, the run can remain green even when extraction never actually succeeded.

Relevant file:

- `backend/app/services/pipeline/pipeline_orchestrator.py`

### Missing keys and no-provider cases are already closer to the desired behavior

If no usable provider key exists at all, model resolution fails before chunk processing and the orchestrator can surface that as a failed run. The bigger gap is for provider errors that happen after model selection succeeds:

- invalid OpenAI key
- no credits / insufficient quota
- account or model access issues

Those happen inside the chunk loop today and are swallowed.

### The backend already has structured pipeline failure support

`PipelineRunRead` can hydrate `error` from `usage_summary.failure` / `diagnostics.error`, and `ApiErrorDetail` already supports `metadata`.

Relevant files:

- `backend/app/schemas/pipeline_run.py`
- `backend/app/api/errors.py`

This means we do not need a brand-new pipeline error shape for this issue. We can build on the existing structured error envelope and standardize metadata keys for remediation.

### The Documents pipeline status view does not yet render remediation guidance

The Documents page already shows:

- the run badge and stage progress
- `runSummary.error_message`
- flattened usage-summary error messages

But it does not render structured remediation data from `runSummary.error.metadata`.

Relevant file:

- `frontend/src/routes/_layout/documents.tsx`

## Key Decisions

- **Fail fast only for clearly fatal setup/access errors.**
  - Do not turn every chunk-level issue into a hard stop.
  - Preserve best-effort continuation for non-fatal content or parse issues.

- **Use typed extraction-stage exceptions.**
  - Introduce explicit domain exceptions for fatal extraction provider/setup failures instead of relying only on raw SDK messages.

- **Store remediation in structured metadata.**
  - Reuse `ApiErrorDetail.metadata` with a stable shape such as:
    - `hint`
    - `action_items`
    - `provider`
    - `model`
    - `category`

- **Make the Documents pipeline status area the primary surface.**
  - Toasts are useful, but the persistent pipeline status block should show the same failure plus the fix so the user can come back and understand what happened.

- **Keep missing-key behavior aligned with in-call provider failures.**
  - "No API key configured" and "OpenAI rejected the configured key" should both end up as failed runs with similarly actionable guidance.

## Suggested User-Facing Error Mapping

These are examples of the intended display behavior, not final copy:

- **Missing API key**
  - Message: `No API key is configured for extraction.`
  - Hint: `Add OPENAI_API_KEY to your .env file and restart the backend.`

- **Invalid API key**
  - Message: `OpenAI rejected the configured API key.`
  - Hint: `Replace OPENAI_API_KEY with a valid key and restart the backend.`

- **No credits / insufficient quota**
  - Message: `Your OpenAI API account does not have available credits.`
  - Hint: `Add billing or prepaid credits to your OpenAI API account, then rerun the pipeline.`

- **Model access denied**
  - Message: `Your OpenAI API account cannot use the configured extraction model.`
  - Hint: `Confirm your account has access to the model or change the configured model.`

- **Rate limit exhausted after retries**
  - Message: `OpenAI rate limits prevented extraction from starting.`
  - Hint: `Retry later or reduce the extraction workload if this persists.`

## Implementation Plan

### Phase 1: Add extraction fatal-error classification

**Goal**: Distinguish fatal setup/access errors from recoverable chunk failures.

**Tasks**:

- Add a small provider-error classification helper under `backend/app/services/langchain/` or `backend/app/services/scene_extraction/`.
- Detect at least:
  - missing credentials
  - authentication failure
  - insufficient quota / credits
  - model access denied
  - account-level throttling after retries
- Introduce typed exceptions such as:
  - `ExtractionSetupError`
  - `ExtractionProviderAccessError`
  - `ExtractionQuotaError`
- Include structured remediation fields on those exceptions or a helper that converts them into `ApiErrorDetail.metadata`.

**Verification**:

- [ ] Unit tests classify representative OpenAI error strings and exception objects into the expected fatal categories
- [ ] Non-fatal malformed-output cases are not classified as fatal

### Phase 2: Make extraction fail fast on fatal provider errors

**Goal**: Stop the extraction stage immediately when setup/access errors occur.

**Tasks**:

- Update `SceneExtractor._extract_chapter_scenes()` so fatal classified errors are re-raised instead of swallowed.
- Keep `continue` behavior only for explicitly recoverable chunk failures.
- Consider the same rule for the optional refinement pass if it can hit the same provider/setup problems during the extraction stage.
- Include chapter/chunk/provider/model context in logs, but keep the surfaced UI message concise.

**Verification**:

- [ ] If the first extraction chunk fails with an authentication or quota error, `extract_book()` raises and the stage stops immediately
- [ ] If a later chunk hits a recoverable parse issue, extraction still continues

### Phase 3: Persist actionable extraction failures on the pipeline run

**Goal**: Ensure fatal extraction errors become first-class failed pipeline runs.

**Tasks**:

- Update orchestrator failure handling to preserve:
  - stable error code
  - display message
  - remediation metadata
  - observed stage
- Make sure extraction-stage fatal errors become `run.error`, `run.error_message`, and `usage_summary.failure`.
- Standardize metadata keys so the frontend can render them without screen-specific parsing.

**Verification**:

- [ ] `GET /pipeline-runs/{run_id}` includes structured failure metadata for extraction setup errors
- [ ] The run ends with `status="failed"` and `current_stage="failed"`

### Phase 4: Show remediation in the Documents pipeline view

**Goal**: The pipeline status block should tell the user what happened and what to do.

**Tasks**:

- Update the Documents pipeline status section to prefer structured failure data from `runSummary.error`.
- Render:
  - the main failure message
  - a short remediation hint
  - optional bullet list of action items when present
- Keep the existing toast, but ensure the persistent card shows the same message so the user does not need to catch the toast in real time.
- Fall back to legacy `error_message` when structured metadata is absent.

**Verification**:

- [ ] A failed extraction run shows the exact error in the pipeline status block
- [ ] The same block shows a concrete fix such as adding credits or updating the API key
- [ ] Older runs without structured remediation still render cleanly

### Phase 5: Cover the first-run setup cases in tests

**Goal**: Prevent regressions in the onboarding flow.

**Tasks**:

- Add service tests for extraction fail-fast classification and behavior.
- Add orchestrator tests verifying fatal extraction setup errors mark the run as failed with structured metadata.
- Add route/schema tests for `GET /pipeline-runs/{run_id}` structured failure hydration.
- Add frontend tests for the Documents pipeline status block rendering remediation hints.

**Verification**:

- [ ] Backend tests cover missing-key, invalid-key, and insufficient-quota scenarios
- [ ] Frontend tests cover structured remediation rendering

### Phase 6: Tighten onboarding documentation

**Goal**: Reduce how often users hit these failures in the first place.

**Tasks**:

- Update `README.md` quickstart and troubleshooting copy to state that:
  - an OpenAI API key alone is not enough without active billing / available credits
  - common failures will now show up in the pipeline status area
- Add short troubleshooting entries for:
  - missing API key
  - invalid API key
  - no credits / insufficient quota

**Verification**:

- [ ] README setup guidance matches the new runtime behavior
- [ ] Troubleshooting copy matches the surfaced UI messages closely enough that users can self-serve

## Files to Modify

| File | Action |
|------|--------|
| `backend/app/services/scene_extraction/scene_extraction.py` | Modify - fail fast on classified fatal extraction errors |
| `backend/app/services/scene_extraction/scene_refinement.py` | Modify - align refinement-stage fatal error handling if needed |
| `backend/app/services/langchain/retry_utils.py` | Modify - avoid lumping all provider failures into generic retry behavior if needed |
| `backend/app/services/langchain/` | Create/modify - add provider/setup error classification helper |
| `backend/app/services/pipeline/pipeline_orchestrator.py` | Modify - preserve structured extraction failure metadata on failed runs |
| `backend/app/api/errors.py` | Modify - standardize remediation metadata keys if needed |
| `backend/app/schemas/pipeline_run.py` | Modify - ensure structured failure hydration remains frontend-friendly |
| `frontend/src/routes/_layout/documents.tsx` | Modify - render remediation in the pipeline status section |
| `backend/app/tests/services/test_scene_extractor_book_loading.py` | Modify - add fail-fast extraction setup tests |
| `backend/app/tests/services/test_pipeline_orchestrator.py` | Modify - assert failed run metadata for extraction setup errors |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify - assert structured pipeline failure round-trip |
| `frontend/src/routes/_layout/documents.tsx` tests | Create/modify - verify pipeline error and remediation rendering |
| `README.md` | Modify - clarify billing/credits requirement and troubleshooting |

## Testing Strategy

- **Service tests**: validate fatal classification and fail-fast extraction behavior.
- **Orchestrator tests**: verify the pipeline run is marked failed and includes structured remediation.
- **Route/schema tests**: verify `PipelineRunRead` exposes the structured failure cleanly.
- **Frontend tests**: verify the pipeline status block renders both the failure and the fix.
- **Manual verification**: run the pipeline with:
  - no `OPENAI_API_KEY`
  - an invalid OpenAI key
  - an account with no available credits

## Acceptance Criteria

- [ ] A fatal extraction setup/access error stops the run on the first occurrence
- [ ] The run ends in `failed` rather than silently completing with zero output
- [ ] The Documents pipeline status area shows the real error message
- [ ] The Documents pipeline status area also shows a concrete remediation hint
- [ ] Common onboarding failures are covered: missing key, invalid key, no credits, model access denial
- [ ] Recoverable non-fatal chunk issues can still continue when appropriate
- [ ] Backend tests pass (`cd backend && uv run pytest`)
- [ ] Frontend builds cleanly (`cd frontend && npm run build`)
- [ ] README setup/troubleshooting guidance matches the new behavior

## Related Issues

- `issues/048-end-to-end-error-propagation-and-frontend-surfacing.md`
- `issues/047-pipeline-stage-progress-tracking.md`
