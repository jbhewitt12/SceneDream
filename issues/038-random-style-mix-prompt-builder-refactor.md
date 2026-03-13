# Refactor Prompt Generation for Random Style Mix vs Single Art Style

## Overview
Refactor prompt generation so the prompt text changes explicitly based on the resolved prompt art style mode:
- `random_mix`: keep the existing sampled-style behavior
- `single_style`: generate multiple prompt variants for the scene while keeping one user-provided art style consistent

This issue covers prompt-generation config, style planning, prompt-builder branching, and provider strategy updates. It does not cover settings migration or frontend UI work.

## Problem Statement
The current prompt-generation path assumes every request uses a sampled set of styles:
- `ImagePromptGenerationService` always builds a `StyleSampler`
- `PromptBuilder` always injects a `Suggested Styles for This Request` section
- output requirements currently tell the model not to reuse the same style family twice
- provider strategies explicitly instruct the model to choose unique styles per variant

That logic is correct for `Random Style Mix`, but incorrect for a fixed single-style workflow. If a user chooses one art style, we need multiple prompts that vary composition, emphasis, framing, and lighting without changing the core style.

## Proposed Solution
Introduce a style-plan abstraction and make prompt construction mode-aware:
- resolve a `PromptArtStylePlan` before prompt assembly
- for `random_mix`, keep the sampled style list path
- for `single_style`, skip style sampling and render a different style section and different style constraints
- update provider strategy hooks so they can return mode-specific style guidance

## Codebase Research Summary

### Current service behavior
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`
  - `_build_style_sampler()` always assumes sampling
  - `_sample_styles()` always returns a list of sampled styles
  - `_resolve_default_art_style_name()` currently reads the old settings UUID

### Current prompt assembly behavior
- `backend/app/services/image_prompt_generation/prompt_builder.py`
  - always includes `## Suggested Styles for This Request`
  - always says each variant should use a different style
  - always expects `styles` to be non-empty

### Current strategy behavior
- `backend/app/services/image_prompt_generation/strategies/dalle_strategy.py`
- `backend/app/services/image_prompt_generation/strategies/gpt_image_strategy.py`
  - both return style-strategy text that assumes per-variant style diversity

## Key Decisions
- Keep `Random Style Mix` prompt behavior functionally equivalent to the current implementation.
- `single_style` means:
  - all variants should use the same user-entered style
  - variants should differ by composition, subject emphasis, camera, lighting, moment selection, or framing
  - the prompt must not tell the LLM to choose different styles per variant
- Replace `preferred_style` as the primary abstraction with explicit mode/text config.
- Represent the resolved prompt-art-style behavior internally with a dedicated plan object instead of passing around ambiguous strings.
- Preserve `sampled_styles` in stored service metadata only for `random_mix`; do not fabricate sampled lists for `single_style`.

## Implementation Plan

### Phase 1: Update prompt-generation config to use explicit mode/text
**Goal**: align runtime config with the new API model.

**Tasks**:
- Update `backend/app/services/image_prompt_generation/models.py`:
  - replace `preferred_style` with explicit prompt art style mode/text fields
- Update config copying and normalization logic accordingly.
- Update `ImagePromptGenerationService` to consume the resolved prompt art style mode/text from runtime config.
- Do not re-resolve launched-run style mode/text from app settings inside prompt generation.
- If standalone CLI entrypoints need a fallback for direct prompt-generation invocation, resolve that before constructing the runtime config so the service still receives a fully resolved mode/text pair.

**Verification**:
- [ ] Config can represent `random_mix`
- [ ] Config can represent `single_style` with text

### Phase 2: Introduce a style-plan abstraction in prompt generation
**Goal**: isolate style-mode branching before prompt rendering.

**Tasks**:
- Add an internal data structure such as `PromptArtStylePlan` with:
  - `mode`
  - `style_text`
  - `sampled_styles`
- In `ImagePromptGenerationService`, build the plan before prompt assembly:
  - `random_mix`: sample from DB-backed recommended/other style pools
  - `single_style`: skip sampling and set `style_text`
- Update metadata payload generation to record the plan cleanly.

**Verification**:
- [ ] `random_mix` still returns sampled styles
- [ ] `single_style` returns no sampled list and a valid style text

### Phase 3: Make `PromptBuilder` mode-aware
**Goal**: render different prompt sections and output rules per style mode.

**Tasks**:
- Refactor `PromptBuilder.build_prompt()` to accept the style plan instead of a bare list.
- Split prompt assembly into helpers such as:
  - `_build_style_section(...)`
  - `_build_output_requirements(...)`
- For `random_mix`:
  - keep `Suggested Styles for This Request`
  - keep guidance about using a different style for each variant
- For `single_style`:
  - add a section such as `Fixed Art Style for This Request`
  - instruct the model to use the same style across all variants
  - instruct the model to vary angle, composition, lighting, and emotional emphasis rather than style family

**Verification**:
- [ ] `random_mix` prompt remains equivalent to current behavior
- [ ] `single_style` prompt does not mention choosing from sampled styles
- [ ] `single_style` prompt does not instruct style diversity across variants

### Phase 4: Update provider strategies for mode-specific style guidance
**Goal**: remove style-mode contradictions in provider-specific instructions.

**Tasks**:
- Update the strategy interface in `strategies/base.py` so style guidance can depend on mode.
- Update concrete strategy implementations to return:
  - current unique-style guidance for `random_mix`
  - fixed-style consistency guidance for `single_style`
- Verify there are no other provider-specific instructions that still require style diversity in single-style mode.

**Verification**:
- [ ] DALL-E strategy guidance matches the selected style mode
- [ ] GPT Image strategy guidance matches the selected style mode

### Phase 5: Keep storage, previews, and dry runs coherent
**Goal**: ensure debugging and previews accurately reflect the new behavior.

**Tasks**:
- Update prompt preview helpers to include resolved mode/text in raw metadata.
- Store enough metadata in prompt-generation service payloads to explain how style handling worked for a given run.
- Ensure `dry_run` previews reflect the correct prompt text in both modes.

**Verification**:
- [ ] Dry-run previews show the correct mode-specific prompt
- [ ] Stored raw payload metadata distinguishes `random_mix` vs `single_style`

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/image_prompt_generation/models.py` | Modify |
| `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` | Modify |
| `backend/app/services/image_prompt_generation/prompt_builder.py` | Modify |
| `backend/app/services/image_prompt_generation/core/style_sampler.py` | Modify as needed |
| `backend/app/services/image_prompt_generation/strategies/base.py` | Modify |
| `backend/app/services/image_prompt_generation/strategies/dalle_strategy.py` | Modify |
| `backend/app/services/image_prompt_generation/strategies/gpt_image_strategy.py` | Modify |
| `backend/app/tests/services/test_image_prompt_generation_service.py` | Modify |

## Testing Strategy
- Add backend tests for:
  - style-plan resolution in both modes
  - prompt text sections for both modes
  - dry-run preview behavior in both modes
  - provider strategy guidance selection in both modes
- Run:
  - `cd backend && uv run pytest`

## Acceptance Criteria
- [ ] Prompt generation supports two explicit behaviors: `random_mix` and `single_style`
- [ ] `random_mix` continues to sample from Settings art-style lists
- [ ] `single_style` generates multiple variants that keep one art style consistent
- [ ] Prompt text and provider strategy text no longer contradict the selected style mode
- [ ] Prompt-generation metadata clearly records how style selection worked for a run
- [ ] Launched runs use the prompt art style mode/text already resolved upstream rather than re-reading Settings during prompt generation
- [ ] `cd backend && uv run pytest` passes
