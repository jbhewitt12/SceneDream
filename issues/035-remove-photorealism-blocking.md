# Remove Photorealism Blocking from Image Prompt Generation

## Overview
Remove all prompt-generation logic that explicitly blocks or discourages photorealism so photorealistic styles can be sampled, prompted, and persisted when users choose them.

## Problem Statement
The current pipeline still encodes a stylized-only policy in three places:
- style sampling filters out realism terms before styles are sent to the LLM
- prompt instructions tell models to avoid photorealism/live-action language
- post-generation validation scans prompt output for banned realism terms

This creates policy drift versus product direction. If a user adds `photorealism` as a style, the system should not suppress it.

## Proposed Solution
Remove photorealism-specific blocking/discouragement from:
- `StyleSampler` filtering logic
- prompt strategy guidance and critical constraints text
- `VariantProcessor` banned realism checks

Keep unrelated safety controls unchanged (for example `blocked_warnings` on scene content categories like violence/sexual/drugs).

## Codebase Research Summary

### Current blocking surfaces
- `backend/app/services/image_prompt_generation/core/style_sampler.py`
  - `BLOCKED_STYLE_TERMS` constant
  - `sample()` filters any sampled style containing blocked terms
  - preferred style is also suppressed when it matches blocked terms
- `backend/app/services/image_prompt_generation/core/constraints.py`
  - critical constraints explicitly forbid photorealistic/hyper-realistic/live-action treatments
- `backend/app/services/image_prompt_generation/strategies/dalle_strategy.py`
  - creative guidance + style strategy explicitly prohibit photorealism/live-action/cinematic realism
- `backend/app/services/image_prompt_generation/strategies/gpt_image_strategy.py`
  - creative guidance directs explicit negative constraints like "no photorealism"
- `backend/app/services/image_prompt_generation/variant_processing.py`
  - `_BANNED_STYLE_TERMS` and `_enforce_variant_constraints()` scan `prompt_text` and `style_tags` for realism terms

### Tests tied to blocking behavior
- `backend/app/tests/services/test_image_prompt_generation_service.py`
  - `test_sample_styles_filters_blocked_terms`

### Notes
- `ImagePromptGenerationConfig.blocked_warnings` in `models.py` is content-safety for scene warnings, not style realism policy, and should remain unchanged.

## Key Decisions
- Remove realism blocking entirely rather than replacing it with soft warnings in this issue.
- Preserve all non-style validation (schema shape, aspect ratio normalization, etc.).
- Preserve existing content-safety warning behavior (`blocked_warnings`).

## Implementation Plan

### Phase 1: Remove style-sampler realism filtering
**Goal**: sampled style lists are no longer filtered by realism terms.

**Tasks**:
- Remove `BLOCKED_STYLE_TERMS` from `style_sampler.py`
- Remove `blocked_terms` constructor argument/state
- Remove filtering logic in `sample()`
- Ensure preferred style is always allowed if set
- Update `core/__init__.py` exports accordingly

**Verification**:
- [ ] `StyleSampler.sample()` includes `photorealism` styles when present
- [ ] Preferred realism style is not suppressed

### Phase 2: Remove anti-photorealism prompt instructions
**Goal**: LLM prompt text no longer mandates stylized-only/anti-photorealism behavior.

**Tasks**:
- Update `CriticalConstraints.get_constraints_text()` to remove realism prohibition wording
- Update DALLE strategy guidance/style strategy text to remove anti-photorealism directives
- Update GPT Image strategy guidance to remove "no photorealism" constraints language
- Update any prompting cheatsheet lines that explicitly enforce anti-photorealism policy

**Verification**:
- [ ] Rendered prompt templates contain no explicit "avoid photorealism" instruction
- [ ] Prompt schema/output constraints remain intact

### Phase 3: Remove post-generation realism checks
**Goal**: variant processing does not apply realism-term checks.

**Tasks**:
- Remove `_BANNED_STYLE_TERMS` from `variant_processing.py`
- Remove `banned_style_terms` constructor argument and related state
- Remove realism scan logic from `_enforce_variant_constraints()`
- Keep aspect-ratio and structural checks unchanged

**Verification**:
- [ ] Variants containing realism terms do not generate realism-specific issues
- [ ] Existing non-realism constraint behavior continues working

### Phase 4: Update tests and docs
**Goal**: test suite reflects new policy.

**Tasks**:
- Remove or rewrite tests expecting blocked realism filtering
- Add/adjust tests asserting realism styles can pass through sampling and prompt rendering
- Ensure prompt-template tests still validate required sections

**Verification**:
- [ ] `cd backend && uv run pytest` passes
- [ ] No tests assert anti-photorealism filtering behavior

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/image_prompt_generation/core/style_sampler.py` | Modify |
| `backend/app/services/image_prompt_generation/core/__init__.py` | Modify |
| `backend/app/services/image_prompt_generation/core/constraints.py` | Modify |
| `backend/app/services/image_prompt_generation/strategies/dalle_strategy.py` | Modify |
| `backend/app/services/image_prompt_generation/strategies/gpt_image_strategy.py` | Modify |
| `backend/app/services/image_prompt_generation/variant_processing.py` | Modify |
| `backend/app/services/image_prompt_generation/cheatsheets/*.md` | Modify (if anti-photorealism lines exist) |
| `backend/app/tests/services/test_image_prompt_generation_service.py` | Modify |

## Testing Strategy
- Backend unit/service tests for style sampling and prompt rendering
- Regression check for variant processing (aspect ratio + schema validation still intact)
- End-to-end CLI smoke test for prompt + image generation:
  - `cd backend && uv run python -m app.services.image_gen_cli backfill --book-slug excession-iain-m-banks --top-scenes 1`
- Full backend run:
  - `cd backend && uv run pytest`

## Acceptance Criteria
- [ ] No style-sampler filtering exists for photorealism/live-action terms
- [ ] Prompt guidance no longer instructs models to avoid photorealism
- [ ] Variant post-processing no longer flags realism terms in `prompt_text`/`style_tags`
- [ ] Users can include `photorealism` in style lists without system-level suppression
- [ ] `cd backend && uv run python -m app.services.image_gen_cli backfill --book-slug excession-iain-m-banks --top-scenes 1` is run successfully as a final smoke test
- [ ] `cd backend && uv run pytest` passes
