In backend/app/services/image_prompt_generation/image_prompt_generation_service.py we encourage the model that is generating the image prompt to come up with a variety of styles. I would like to increase the number of styles that we try even more. I have done research, and I have come up with two lists of styles.

RECOMMEDED_STYLES:
90's anime, Ukiyo-e woodblock, stained glass mosaic, Art Nouveau, Impressionism, Cubism, knolling, papercraft, miniature diorama, wood burned artwork, smudged oil painting, 3D voxel art, technical drawing, Neo-Expressionist, electric luminescent low-poly, paper sculpture, 3D drawing, neon cubism, watercolor pixel art, smudged charcoal, paper cut silhouette, smudged Chinese ink painting, anime-style watercolor, 3D Pixar-style cartoon, neon-line drawing, isometric LEGO, illuminated manuscript

OTHER_STYLES:
Abstract art, abstract geometry, Art Deco, Bauhaus, bokeh art, Brutalism, Byzantine art, Celtic art, chiptune visuals, concept art, Constructivism, Cyber Folk, cybernetic art, cyberpunk, Dadaism, data art, digital collage, digital cubism, digital Impressionism, digital painting, double exposure, dreamy fantasy, dystopian art, etching, Expressionism, Fauvism, flat design, fractal art, Futurism, glitch art, Gothic art, gouache, Greco-Roman art, ink wash painting, isometric art, lithography, low-poly art, macabre art, Magic Realism, Minimalism, Modernism, mosaic art, neon graffiti, neon noir, origami art, parallax art, pastel drawing, photorealism, pixel art, pointillism, polyart, Pop Art, psychedelic art, Renaissance painting, Baroque painting, Retro Wave, Romanticism, sci-fi fantasy art, scratchboard art, steampunk, stippling, Surrealism, Symbolism, trompe-l'œil, Vaporwave, vector art, watercolor painting, Zen doodle, claymation, children's book illustration, graffiti art, manga style, comic book style, cartoon style, caricature style, black-and-white, sepia tone, vintage style

Help me come up with a plan that incorporates these two lists into the Image prompt generation system. Remember that the number of prompts we generate for a particular scene varies. I'm thinking that if we are generating, for example, four prompts, then we should sample 6 styles from RECOMMEDED_STYLES and 2 styles from OTHER_STYLES. Then shuffle the list and provide this list of eight styles to the model in the prompt and ask the model to choose from these styles when creating the image prompts. This would ensure that we get a lot of variety in the styles that are used, and we also use styles that have a chance of being great.

  - Sampling Mix: For N prompts to generate, sample min( max(2, N+2), len(RECOMMENDED_STYLES)) from RECOMMENDED and min(max(1, N//2), len(OTHER_STYLES)) from OTHER to bias toward high-quality styles while injecting variety (e.g., N=4 → 6+2; N=1 → 3+1; N=8 → 10+4 capped by list sizes).
  - Dedup & Shuffle: Ensure sampled styles are unique, then shuffle before sending to the model so ordering doesn't bias selections.

As part of the plan, we should also remove any existing lists of recommended styles. Keep the parts in `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` and `backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md` that talk about not doing photorealistic images or similar.

---

# Dynamic Style List Generation for Image Prompts

## Overview
Enhance the image prompt generation system to provide curated, dynamically-sampled style lists to the LLM, biasing toward high-quality artistic styles while maintaining variety. This replaces the current approach where the cheatsheet contains static style inspiration pools with a more targeted, per-request style sampling strategy.

## Problem Statement
Currently, the image prompt generation service provides a static cheatsheet (`dalle3_multi_genre_prompting_cheatsheet.md`) containing style inspiration pools, but it does not provide a curated selection of specific styles tailored to the number of variants being generated. This leads to:
- **Inconsistent style diversity**: The model may gravitate toward familiar styles without exploring the full range of artistic possibilities
- **Missed opportunities**: High-performing styles from RECOMMENDED_STYLES may be underutilized
- **Suboptimal variety**: With no sampling mechanism, the model lacks structured guidance on style selection per variant

By implementing a dynamic style sampling system that feeds the LLM a curated list based on the variant count, we can:
- Bias toward proven high-quality styles (RECOMMENDED_STYLES) while injecting creative variety (OTHER_STYLES)
- Ensure each prompt generation run explores a fresh mix of artistic styles
- Maintain style diversity across variants without requiring manual prompt engineering

## Proposed Solution
Implement a style sampling utility that:
1. Defines two style lists (RECOMMENDED_STYLES and OTHER_STYLES) as constants in the image prompt generation module
2. Dynamically samples styles based on the number of variants being generated using the formula provided:
   - `recommended_count = min(max(2, N+2), len(RECOMMENDED_STYLES))`
   - `other_count = min(max(1, N//2), len(OTHER_STYLES))`
3. Deduplicates and shuffles the sampled styles before injecting them into the LLM prompt
4. Updates the prompt template to include a "Suggested Styles" section with the sampled list
5. Removes static style lists from the cheatsheet while preserving photorealism constraints

## Codebase Research Summary

### Relevant Existing Patterns
- **Configuration & Models**: The `ImagePromptGenerationConfig` dataclass in `backend/app/services/image_prompt_generation/models.py` already handles runtime configuration with a `copy_with` pattern for overrides
- **Prompt Building**: The `_build_prompt` method in `image_prompt_generation_service.py` (lines 732-848) assembles the LLM prompt from multiple sections including cheatsheet content, guidance, and output requirements
- **Cheatsheet Loading**: The `_load_cheatsheet_text` method (lines 1014-1026) loads and caches the cheatsheet markdown file
- **Service Architecture**: The service follows a repository pattern with clear separation: service → repository → SQLModel
- **Testing Patterns**: Service tests in `backend/app/tests/services/` use pytest fixtures with session management

### Files That Will Be Affected
1. **backend/app/services/image_prompt_generation/image_prompt_generation_service.py** (main service, ~1100 lines)
   - Add style sampling logic
   - Modify `_build_prompt` method to inject sampled styles
2. **backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md**
   - Remove "Style Inspiration Pools" section
   - Preserve photorealism constraints and other guidance
3. **backend/app/services/image_prompt_generation/models.py** (optional)
   - Could add style list constants here or in a new `styles.py` module for better separation

### Similar Features as Reference
- The `_determine_variant_count` method (lines 694-730) shows how the service dynamically adjusts variant counts based on ranking recommendations
- The context builder (`SceneContextBuilder`) demonstrates modular, reusable utilities that services can use

### Potential Risks or Conflicts
- **Prompt Length**: Adding style lists will increase prompt tokens; need to ensure we stay within Gemini's limits (currently uses max_output_tokens=8192)
- **Reproducibility**: Shuffling styles will make results non-deterministic; this is acceptable but should be documented
- **Style Filtering**: Need to ensure photorealism-related styles (e.g., "photorealism" in OTHER_STYLES) are filtered out or flagged
- **Testing**: Need to verify sampled styles are correctly injected and don't break existing prompt structure

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Review `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` to understand current prompt building
3. Check `dalle3_multi_genre_prompting_cheatsheet.md` to identify which sections to preserve vs. remove
4. Verify tests in `backend/app/tests/services/image_prompt_generation/` run successfully before and after changes

**Key Decisions Made**:
- **Sampling Formula**: Using `min(max(2, N+2), len(RECOMMENDED))` for recommended and `min(max(1, N//2), len(OTHER))` for other styles to ensure at least 3 styles total even for N=1
- **Style List Location**: Defining style lists as module-level constants in `image_prompt_generation_service.py` for now; could be moved to a separate module if the list grows
- **Cheatsheet Preservation**: Keeping all sections of the cheatsheet except "Style Inspiration Pools" to maintain photorealism constraints and other guidance
- **No Database Changes**: This is purely a prompt engineering enhancement; no schema migrations needed

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify the latest version of `image_prompt_generation_service.py` is read
- [ ] Run existing tests to establish baseline: `cd backend && uv run pytest app/tests/services/image_prompt_generation/`
- [ ] Understand the current prompt structure by running `render_prompt_template` in a test

## Implementation Phases

### Phase 1: Define Style Lists and Sampling Logic
**Goal**: Create the style list constants and implement the sampling function as a standalone utility

**Dependencies**: None

**Time Estimate**: 30-45 minutes

**Success Metrics**:
- [ ] RECOMMENDED_STYLES and OTHER_STYLES constants defined with all styles from the issue description
- [ ] `_sample_styles(variants_count: int) -> list[str]` method implemented with correct sampling formula
- [ ] Photorealism-related styles filtered out from sampling results
- [ ] Unit tests verify sampling counts for N=1, N=4, N=8 variants
- [ ] Deduplication and shuffling work correctly

**Tasks**:
1. In `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`:
   - Add module-level constants `RECOMMENDED_STYLES` (tuple of 27 styles) and `OTHER_STYLES` (tuple of ~100 styles) after the existing imports and before the service class
   - Define a tuple `BLOCKED_STYLE_TERMS` containing terms like "photorealism", "hyper-realistic", "live-action" to filter from sampled styles
2. Add a private method `_sample_styles` to `ImagePromptGenerationService` class:
   - Takes `variants_count: int` as parameter
   - Calculates `recommended_count = min(max(2, variants_count + 2), len(RECOMMENDED_STYLES))`
   - Calculates `other_count = min(max(1, variants_count // 2), len(OTHER_STYLES))`
   - Uses `random.sample` to select from each list
   - Filters out styles containing blocked terms (case-insensitive)
   - Combines, deduplicates, shuffles, and returns the final list
3. Add import for `random` module at the top of the file
4. Write unit tests in `backend/app/tests/services/image_prompt_generation/test_image_prompt_generation_service.py`:
   - Test `_sample_styles(1)` returns at least 3 styles with correct proportions
   - Test `_sample_styles(4)` returns ~8 styles (6 recommended + 2 other)
   - Test `_sample_styles(8)` respects list size caps
   - Test photorealism filtering works
   - Test deduplication works if a style appears in both lists

**Reference Patterns**:
- See `_determine_variant_count` (lines 694-730) for a similar dynamic calculation method
- See `_load_cheatsheet_text` (lines 1014-1026) for module-level caching pattern

---

### Phase 2: Integrate Sampled Styles into Prompt Template
**Goal**: Modify the `_build_prompt` method to include sampled styles in the LLM prompt

**Dependencies**: Phase 1 must be completed

**Time Estimate**: 45-60 minutes

**Success Metrics**:
- [ ] Prompt version incremented to "image-prompts-v3" in models.py
- [ ] `_build_prompt` calls `_sample_styles` with the configured variant count
- [ ] A new "Suggested Styles" section is added to the prompt before "Creative Guidance"
- [ ] Sampled styles are formatted as a comma-separated list or bullet points
- [ ] The style strategy guidance is updated to reference the suggested styles list
- [ ] Integration tests verify the prompt template renders correctly with styles

**Tasks**:
1. In `backend/app/services/image_prompt_generation/models.py`:
   - Update the default `prompt_version` from `"image-prompts-v2"` to `"image-prompts-v3"` (line 24) to track this significant prompt template change
2. In `_build_prompt` method (around line 732):
   - Call `sampled_styles = self._sample_styles(config.variants_count)` after the cheatsheet is loaded
   - Format styles as a comma-separated string: `suggested_styles_text = ", ".join(sampled_styles)`
3. Update the prompt assembly section (around lines 808-847):
   - Add a new section after "## Scene Excerpt" and before "## Creative Guidance":
     ```
     ## Suggested Styles for This Request
     The following {len(sampled_styles)} styles have been curated for variety and quality. Select from this list when designing your {config.variants_count} variants, ensuring each variant uses a different style:
     {suggested_styles_text}
     ```
   - Update the `style_strategy` guidance text to mention: "Consult the Suggested Styles list provided above and ensure each variant uses a different style from that list."
4. Update `_build_remix_prompt` to also sample and include styles (around line 850)
5. Add integration test in `backend/app/tests/services/image_prompt_generation/test_image_prompt_generation_service.py`:
   - Create a test that calls `render_prompt_template` for a scene with variants_count=4
   - Assert "Suggested Styles for This Request" appears in the prompt
   - Assert the prompt contains at least 6 style names from RECOMMENDED_STYLES

**Reference Patterns**:
- See how `metadata_block` is assembled (lines 746-755) for multi-line section construction
- See `render_prompt_template` method (lines 273-326) for testing prompt generation without LLM calls

---

### Phase 3: Update Cheatsheet to Remove Static Style Lists
**Goal**: Clean up the cheatsheet markdown to remove redundant static style pools while preserving other guidance

**Dependencies**: Phase 2 must be completed

**Time Estimate**: 20-30 minutes

**Success Metrics**:
- [ ] "Style Inspiration Pools" section removed from cheatsheet
- [ ] All other sections (Core Formula, Palette & Sensory Hooks, Movement/Scale, etc.) preserved
- [ ] Photorealism constraints remain intact
- [ ] Cheatsheet still loads successfully via `_load_cheatsheet_text`
- [ ] Integration tests pass with updated cheatsheet

**Tasks**:
1. Edit `backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md`:
   - Remove the "### Style Inspiration Pools" section (lines 12-21)
   - Keep all other sections: Core Formula, Rapid Scene Diagnosis, Palette & Sensory Hooks, Movement/Scale/Composition Seeds, Emotional Lanes, Prompt Construction Boosters, Variant Mapping Worksheet, Example Spark Prompts
   - Verify the file still contains guidance on avoiding photorealism
2. Verify the cheatsheet loads correctly by running an integration test
3. Optional: Add a comment at the top of the cheatsheet explaining that style lists are now dynamically sampled per request

**Reference Patterns**:
- See the cheatsheet structure in the current file (lines 1-54)

---

### Phase 4: Add Raw Response Metadata for Style Tracking
**Goal**: Store sampled styles in the raw_response payload for debugging and analysis

**Dependencies**: Phase 2 must be completed

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Sampled styles are stored in `service_payload["sampled_styles"]` as a list
- [ ] Raw response bundles include the sampled styles
- [ ] Database records preserve this metadata
- [ ] Tests verify metadata is stored correctly

**Tasks**:
1. In `generate_for_scene` method (around line 158):
   - Add `sampled_styles` to the `service_payload` dictionary before creating `raw_bundle`
   - Update line ~167 to: `service_payload["sampled_styles"] = sampled_styles` (where `sampled_styles` is obtained from `_sample_styles`)
2. Ensure the sampled styles are passed from `_build_prompt` back to `generate_for_scene`:
   - Option A: Store as instance variable `self._last_sampled_styles` (simple but stateful)
   - Option B: Return sampled styles from `_build_prompt` as a tuple `(prompt_text, sampled_styles)`
   - Recommended: Option B for better testability
3. Update `generate_remix_variants` method (around line 426) to also store sampled styles
4. Add test to verify `raw_response` contains `sampled_styles` list

**Reference Patterns**:
- See how `service_payload` is constructed (lines 158-174)
- See how `raw_bundle` is assembled (lines 171-174)

---

### Phase 5: End-to-End Testing and Validation
**Goal**: Verify the complete feature works as expected with real scenes

**Dependencies**: All previous phases must be completed

**Time Estimate**: 30-45 minutes

**Success Metrics**:
- [ ] All existing unit and integration tests pass
- [ ] New tests for style sampling pass
- [ ] Linting and type checking pass
- [ ] Manual CLI test generates prompts with varied styles
- [ ] Generated prompts no longer contain photorealism terms

**Tasks**:
1. Run full test suite: `cd backend && uv run pytest app/tests/services/image_prompt_generation/`
2. Run linting: `cd backend && uv run ruff check app/services/image_prompt_generation/`
3. Run type checking: `cd backend && uv run mypy app/services/image_prompt_generation/`
4. Manual validation using CLI:
   - Run end-to-end test: `cd backend && uv run python -m app.services.image_gen_cli backfill --top-scenes 1`
   - Inspect the generated prompt records in the database or logs
   - Verify "Suggested Styles" section appears in the prompts with 6-8 styles for a 4-variant request
   - Check that generated prompts use diverse styles from the suggested list
   - Verify raw_response metadata contains sampled_styles list
5. Optional: Generate prompts for N=1, N=4, N=8 to validate sampling counts by adjusting variants_count in config

**Reference Patterns**:
- See existing test files in `backend/app/tests/services/image_prompt_generation/`
- See CLI entry point patterns in other services (e.g., `scene_ranking/main.py`)

---

## System Integration Points
- **Database Tables**: `image_prompts` (writes sampled styles to raw_response JSONB column)
- **External APIs**: Gemini API (receives modified prompts with style lists)
- **LLM Configuration**: No changes to temperature, max_tokens, or other LLM settings
- **Cheatsheet File**: Read-only dependency on `dalle3_multi_genre_prompting_cheatsheet.md`

## Technical Considerations
- **Performance**: Sampling is O(n) with small lists (~130 total styles), negligible overhead
- **Prompt Tokens**: Adding ~100-200 tokens per request; well within Gemini 2.5 Pro context limits
- **Randomness**: Using `random.sample` introduces non-determinism; acceptable for creative applications. Could add optional seed parameter if reproducibility is needed
- **Style Quality**: RECOMMENDED_STYLES are manually curated; consider periodic review and updates
- **Error Handling**: If sampling fails (e.g., empty lists), fall back to current behavior (no suggested styles section)
- **Monitoring**: Consider tracking style usage frequency in analytics to identify top performers

## Testing Strategy
1. **Unit Tests**:
   - Test `_sample_styles` method with various variant counts (1, 4, 8, 20)
   - Test blocked term filtering
   - Test deduplication logic
   - Test edge cases (empty lists, single variant)
2. **Integration Tests**:
   - Test prompt template rendering includes "Suggested Styles" section
   - Test style metadata is stored in raw_response
   - Test existing prompt generation flow still works
3. **Manual Verification**:
   - Generate prompts for a test scene: `cd backend && uv run python -m app.services.image_gen_cli backfill --top-scenes 1`
   - Inspect output to verify style variety and that "Suggested Styles" section appears in prompts

## Acceptance Criteria
- [ ] All automated tests pass (`uv run pytest app/tests/services/image_prompt_generation/`)
- [ ] Code follows project conventions (4-space indentation, type hints, docstrings)
- [ ] Linting passes (`uv run ruff check app/services/image_prompt_generation/`)
- [ ] Type checking passes (`uv run mypy app/services/image_prompt_generation/`)
- [ ] Prompt version incremented to "image-prompts-v3" in models.py
- [ ] Style lists are correctly defined with all styles from issue description
- [ ] Sampling formula matches specification (N+2 recommended, N//2 other)
- [ ] Photorealism terms are filtered from suggestions
- [ ] Prompt template includes "Suggested Styles" section
- [ ] Cheatsheet no longer contains static style pools
- [ ] Raw response metadata includes sampled styles
- [ ] Generated prompts demonstrate style variety

## Quick Reference Commands
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run tests**: `cd backend && uv run pytest app/tests/services/image_prompt_generation/`
- **Lint check**: `cd backend && uv run ruff check app/services/image_prompt_generation/`
- **Type check**: `cd backend && uv run mypy app/services/image_prompt_generation/`
- **Generate prompts (CLI)**: `cd backend && uv run python -m app.services.image_gen_cli backfill --top-scenes 1`
- **View prompt template**: Use `render_prompt_template` method in tests

## Inter-Instance Communication
### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->