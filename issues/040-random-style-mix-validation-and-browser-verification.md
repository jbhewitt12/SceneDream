# Validate Random Style Mix and Single Art Style End to End

## Overview
Perform the final verification pass for the new prompt art style behavior across backend tests and manual browser validation. This issue is the release gate for the feature.

It covers:
- backend automated tests
- frontend static checks
- manual Settings and Documents dashboard validation using Agent Browser
- initiating new image generation for one scene with both `Random Style Mix` and a single art style

This issue does not add frontend E2E tests to the repository. Browser work here is manual validation using the Agent Browser skill.

## Problem Statement
This feature changes behavior across multiple layers:
- app settings storage and API contract
- per-run pipeline launch resolution
- prompt-builder logic
- frontend launch controls and defaults

That creates a high regression risk. We need a deliberate verification pass that proves:
- settings persist and round-trip correctly
- the dashboard reflects saved defaults
- launching with `Random Style Mix` and `Single art style` both works
- prompt-generation behavior changes correctly without breaking existing flows

## Proposed Solution
Run a combined automated and manual validation pass after implementation is complete:
- extend backend tests where needed and run the full backend suite
- run frontend lint/static checks
- use Agent Browser to validate the Settings page and Documents dashboard
- generate images for one scene from a book that already has extraction and ranking complete, once with `Random Style Mix` and once with a single custom art style

## Key Decisions
- Browser validation is manual and uses Agent Browser; it is not a new frontend E2E test suite.
- Use a document that already has extraction and ranking complete so the test stays focused on prompt/image generation.
- Set `Scenes this run` to `1` for both launch scenarios.
- Use two separate launches:
  - one with `Random Style Mix`
  - one with a custom single style such as `Ukiyo-e woodblock` or another clear non-empty style string
- Verify helper text and saved defaults, not just happy-path network success.
- Capture screenshots for evidence.

## Implementation Plan

### Phase 1: Complete automated backend coverage
**Goal**: prove the behavior is stable at the service and route layers.

**Tasks**:
- Ensure tests exist or are updated for:
  - settings mode/text persistence
  - pipeline run mode/text resolution priority
  - prompt builder behavior in `random_mix`
  - prompt builder behavior in `single_style`
  - metadata/usage summary recording of resolved mode/text
- Run the full backend suite.

**Verification**:
- [ ] `cd backend && uv run pytest` passes

### Phase 2: Complete frontend static validation
**Goal**: confirm the updated UI compiles and passes lint/format rules.

**Tasks**:
- Regenerate frontend client types if required.
- Run frontend lint/static checks.

**Verification**:
- [ ] `cd frontend && npm run lint` passes

### Phase 3: Manual Settings validation with Agent Browser
**Goal**: prove that Settings correctly persists and explains both modes.

**Tasks**:
- Use the Agent Browser skill to open the local app.
- Navigate to Settings.
- Validate `Pipeline Defaults`:
  - `Random Style Mix` is available and clearly named
  - `Single art style` reveals a text input
  - helper copy explains that `Random Style Mix` samples from Settings art styles
- Save Settings once with:
  - `Random Style Mix`
- Save Settings again with:
  - `Single art style`
  - a non-empty art style string
- Reload the page after each save and confirm persistence.
- Capture screenshots of:
  - `Random Style Mix` selected in Settings
  - `Single art style` selected in Settings with the text input populated

**Verification**:
- [ ] Settings persist correctly for both modes
- [ ] Helper copy is visible and accurate

### Phase 4: Manual Documents dashboard validation with Agent Browser
**Goal**: prove the dashboard defaults and per-run overrides work correctly.

**Tasks**:
- Navigate to Documents dashboard.
- Choose a book that already has extraction and ranking complete.
- Confirm the launch UI reflects the saved Settings default mode/text.
- Validate the launch control:
  - shows `Random Style Mix` terminology
  - shows maximum-clarity helper text for `Random Style Mix`
  - reveals a text input for `Single art style`
- Capture screenshots of:
  - dashboard card with `Random Style Mix`
  - dashboard card with `Single art style`

**Verification**:
- [ ] Dashboard reflects the saved default mode/text
- [ ] Random mix helper text is visible in the launch area

### Phase 5: Launch one-scene image generation in both modes
**Goal**: prove the full user workflow works from the dashboard.

**Tasks**:
- On a book with extraction and ranking complete, set `Scenes this run` to `1`.
- Launch image generation once with `Random Style Mix`.
- Wait for the run to be accepted and complete far enough to confirm prompt/image generation started successfully.
- Launch image generation again for one scene with `Single art style` and a non-empty style string.
- Confirm both runs show the expected resolved mode in any visible run metadata or via API inspection if the UI does not expose it.
- If the selected book already has images for all ranked scenes, pick another completed book or clear one target scene through an approved non-destructive setup step before running the test.

**Verification**:
- [ ] One-scene launch works with `Random Style Mix`
- [ ] One-scene launch works with `Single art style`
- [ ] No validation or backend contract errors occur in either path

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/tests/api/routes/test_settings.py` | Modify if needed |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify if needed |
| `backend/app/tests/services/test_pipeline_run_start_service.py` | Modify if needed |
| `backend/app/tests/services/test_image_prompt_generation_service.py` | Modify if needed |
| `frontend/src/client/*` | Regenerate if required |

## Testing Strategy
- Backend:
  - `cd backend && uv run pytest`
- Frontend:
  - `cd frontend && npm run lint`
- Manual browser verification:
  - use the Agent Browser skill
  - capture screenshots of both Settings states and both dashboard launch states
  - validate one-scene launch in both art-style modes

## Acceptance Criteria
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] Agent Browser validation confirms Settings supports and persists both modes
- [ ] Agent Browser validation confirms Documents dashboard reflects saved defaults and mode-specific controls
- [ ] A completed book is used to launch one-scene image generation with `Random Style Mix`
- [ ] A completed book is used to launch one-scene image generation with `Single art style`
- [ ] Screenshots are captured for both Settings states and both dashboard launch states
- [ ] No frontend E2E test suite is introduced as part of this issue
