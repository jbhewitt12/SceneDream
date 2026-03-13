# Introduce Random Style Mix Mode in Settings and Pipeline APIs

## Overview
Replace the current art-style UUID-based defaults/overrides with an explicit prompt art style mode model that supports:
- `random_mix` for the existing sampled behavior, named in product copy as `Random Style Mix`
- `single_style` for a user-entered fixed art style string

This issue covers database migration, backend schemas, API contracts, and pipeline request resolution. It does not cover prompt-template refactoring or frontend wiring.

## Problem Statement
The current backend contract does not match the intended product behavior:
- app settings store `default_art_style_id`, which represents a catalog row, not a user-visible mode
- pipeline launches accept `art_style_id`, which only supports choosing an existing catalog entry
- prompt generation currently interprets `preferred_style` as "bias the sampled list", not "force every variant to use this one style"

That model is no longer sufficient. The product now needs two explicit behaviors:
- `Random Style Mix`: randomly sample from the editable style lists in Settings
- `Single art style`: use one free-text style consistently across generated prompts

## Proposed Solution
Promote prompt art style choice to a first-class mode everywhere in the backend:
- add settings fields for default prompt art style mode and text
- add pipeline launch request fields for prompt art style mode and text
- resolve the effective mode/text once in `PipelineRunStartService`
- persist resolved values into pipeline run config/usage metadata
- deprecate the old UUID-based default/override path

## Codebase Research Summary

### Current settings storage
- `backend/models/app_settings.py`
  - stores `default_scenes_per_run`
  - stores `default_art_style_id`
- `backend/app/schemas/app_settings.py`
  - mirrors the UUID-based setting in read/update schemas
- `backend/app/api/routes/settings.py`
  - validates `default_art_style_id` against `art_styles`

### Current pipeline launch contract
- `backend/app/schemas/pipeline_run.py`
  - accepts `art_style_id`
- `backend/app/services/pipeline/pipeline_run_start_service.py`
  - resolves `art_style_id` to `display_name`
  - passes `prompt_art_style` string into CLI args
  - records `resolved_prompt_art_style` in `config_overrides`

### Why UUID-based style selection is now the wrong abstraction
- a UUID cannot represent `Random Style Mix`
- a UUID cannot represent arbitrary free-text single-style input
- the old "default art style" semantics were "preferred within the sampled pool", which is not equivalent to "force one style for all variants"

## Key Decisions
- Use backend mode values `random_mix` and `single_style`.
- Use the user-facing name `Random Style Mix` everywhere in frontend copy, but keep snake_case enum values in the API.
- Settings default to `random_mix`.
- Do not migrate existing `default_art_style_id` rows into `single_style`; that would silently change behavior.
- The canonical backend fields should be:
  - `default_prompt_art_style_mode`
  - `default_prompt_art_style_text`
  - `prompt_art_style_mode`
  - `prompt_art_style_text`
- Keep image-generation `style` (`vivid` / `natural`) separate from prompt art style mode/text.
- `random_mix` ignores any text value.
- `single_style` requires a non-empty trimmed text value.

## Implementation Plan

### Phase 1: Add new app settings fields and migration
**Goal**: store the product concept directly in the database.

**Tasks**:
- Add Alembic migration to `app_settings`:
  - add `default_prompt_art_style_mode` with default `random_mix`
  - add `default_prompt_art_style_text` nullable
- Leave `default_art_style_id` in place only as a temporary compatibility field if needed during rollout.
- Backfill all existing rows to:
  - `default_prompt_art_style_mode = "random_mix"`
  - `default_prompt_art_style_text = NULL`

**Verification**:
- [ ] Migration applies cleanly on an existing database
- [ ] Existing installs preserve current behavior after migration
- [ ] New settings rows default to `random_mix`

### Phase 2: Update settings model, schemas, and route contract
**Goal**: expose the new settings shape via `/api/v1/settings`.

**Tasks**:
- Update `backend/models/app_settings.py` to include the new fields.
- Update `backend/app/schemas/app_settings.py`:
  - replace `default_art_style_id` in read/update schemas
  - add enum validation for mode
  - validate that `single_style` requires text
- Update `backend/app/api/routes/settings.py` to read/write the new fields.
- Remove UUID validation for default art style from the settings route.

**Verification**:
- [ ] `GET /api/v1/settings` returns default mode/text
- [ ] `PATCH /api/v1/settings` accepts `random_mix`
- [ ] `PATCH /api/v1/settings` accepts `single_style` with text
- [ ] `PATCH /api/v1/settings` rejects `single_style` with blank text

### Phase 3: Update pipeline run request contract and resolution logic
**Goal**: let launches override the default using the same mode/text model.

**Tasks**:
- Update `backend/app/schemas/pipeline_run.py`:
  - replace `art_style_id` with `prompt_art_style_mode` and `prompt_art_style_text`
- Update `backend/app/services/pipeline/pipeline_run_start_service.py` to resolve effective mode/text using this priority:
  - request override
  - app settings default
  - hard fallback to `random_mix`
- Pass the resolved values into the CLI namespace.
- Persist the resolved values into `config_overrides`.
- Update `usage_summary` generation in `backend/app/api/routes/pipeline_runs.py` to record:
  - `prompt_art_style_mode`
  - `prompt_art_style_text`

**Verification**:
- [ ] Launch requests can explicitly choose `random_mix`
- [ ] Launch requests can explicitly choose `single_style`
- [ ] Blank text is rejected when mode is `single_style`
- [ ] Resolved mode/text are visible in stored pipeline run metadata

### Phase 4: Remove UUID-based default/override semantics from service boundaries
**Goal**: eliminate old naming that no longer matches behavior.

**Tasks**:
- Stop resolving prompt art style through `ArtStyleRepository` IDs in pipeline start logic.
- Remove or deprecate `resolved_prompt_art_style` in favor of:
  - `resolved_prompt_art_style_mode`
  - `resolved_prompt_art_style_text`
- Audit any remaining references to `default_art_style_id` and `art_style_id`.
- Keep compatibility shims only if needed to avoid breaking the transition in a partial rollout branch.

**Verification**:
- [ ] No live pipeline path depends on `art_style_id`
- [ ] No settings save path depends on `default_art_style_id`

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/alembic/versions/<new_revision>_prompt_art_style_mode_fields.py` | Create |
| `backend/models/app_settings.py` | Modify |
| `backend/app/repositories/app_settings.py` | Modify |
| `backend/app/schemas/app_settings.py` | Modify |
| `backend/app/schemas/pipeline_run.py` | Modify |
| `backend/app/api/routes/settings.py` | Modify |
| `backend/app/services/pipeline/pipeline_run_start_service.py` | Modify |
| `backend/app/api/routes/pipeline_runs.py` | Modify |
| `frontend/src/client/types.gen.ts` | Regenerate later |

## Testing Strategy
- Backend automated tests:
  - settings route tests for new mode/text contract
  - pipeline start service tests for mode resolution priority and validation
  - pipeline route tests for stored resolved metadata
- Run:
  - `cd backend && uv run pytest`

## Acceptance Criteria
- [ ] `app_settings` stores default prompt art style as mode + text, not as a catalog UUID
- [ ] Settings API defaults to `random_mix`
- [ ] Settings API supports `single_style` with free-text input
- [ ] Pipeline launch API supports prompt art style mode/text overrides
- [ ] Pipeline run resolution stores resolved mode/text in run metadata
- [ ] No existing install is silently converted from sampled behavior into fixed single-style behavior
- [ ] `cd backend && uv run pytest` passes
