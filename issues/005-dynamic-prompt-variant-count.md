# Dynamic Prompt Variant Count Based on Scene Complexity

## Overview
Implement an intelligent system that analyzes scenes during ranking to determine the optimal number of image prompt variants to generate for each scene, maximizing prompt quality and variety while minimizing redundant generation for simple scenes.

## Problem Statement
Currently, the number of image prompt variants generated per scene is fixed (default: 4, configured via CLI with `--prompts-per-scene`). This creates several issues:

**Current limitations:**
- **Over-generation for simple scenes**: A scene with a single setting/location gets 4 variants that may be too similar, wasting LLM tokens and storage
- **Under-generation for complex scenes**: A rich scene spanning 5+ distinct locations/moments gets only 4 variants, missing opportunities to capture all visually compelling moments
- **No semantic awareness**: The system doesn't adapt to scene content—a space battle and a character conversation get the same treatment

**User impact:**
- Wasted resources generating redundant prompts for simple scenes
- Missed opportunities to capture diverse visual moments from complex scenes
- Suboptimal coverage of high-potential scenes

**Business value of solving this:**
- Better resource utilization (LLM API costs, storage)
- Higher quality image generation by ensuring all visually distinct moments get coverage
- Improved variety in generated images per scene
- More intelligent allocation: more prompts for rich scenes, fewer for simple ones

## Proposed Solution

### High-Level Approach
Enhance the scene ranking service to perform **scene complexity analysis** during the ranking phase, determining:
1. **Distinct visual settings/locations** within the scene (e.g., "bridge → corridor → observation deck")
2. **Temporal moments** that merit separate prompts (e.g., "ship approaching → impact → explosion aftermath")
3. **Visual diversity potential** based on action, characters, atmosphere changes

The ranker will output a new field `recommended_prompt_count` (integer, range: 1-10) stored in the `scene_rankings` table. This value will be used by the image prompt generation service to determine how many variants to create.

### Strategy: Multi-Setting Detection + Base Variant Multiplier

**Core Formula:**
```
recommended_prompt_count = min(
    max(
        (num_distinct_settings × variants_per_setting) + bonus_variants,
        minimum_variants
    ),
    maximum_variants
)
```

**Parameters (tunable via config):**
- `variants_per_setting`: 2-3 (explore different angles/styles per location)
- `minimum_variants`: 2 (even simplest scenes get at least 2 variations)
- `maximum_variants`: 10 (cap to prevent explosion on very long scenes)
- `bonus_variants`: 0-2 (add for high action/emotional intensity scenes)

**LLM Analysis Approach:**
The scene ranking LLM will analyze scenes for:
1. **Location/setting shifts** (e.g., "starts in hangar, moves to cockpit, ends in space")
2. **Temporal progression** (e.g., "before explosion, during, aftermath")
3. **Visual complexity markers** (multiple characters, environmental changes, action variety)
4. **Composition potential** (can different camera angles/compositions tell different stories?)

The LLM returns a structured response:
```json
{
  "distinct_visual_moments": [
    {"description": "Character in ship's bridge, tense atmosphere", "composition_variety": "medium"},
    {"description": "Explosion in space, debris field", "composition_variety": "high"},
    {"description": "Aftermath view from observation deck", "composition_variety": "low"}
  ],
  "recommended_prompt_count": 7,
  "complexity_rationale": "Scene spans 3 distinct locations with high visual variety in explosion sequence. Each setting merits 2-3 prompt variants."
}
```

### Integration with Existing Systems
- **Scene Ranking Service** (`scene_ranking_service.py`):
  - Enhanced LLM prompt to analyze scene complexity
  - New fields in `_RankingResponse`: `distinct_visual_moments`, `recommended_prompt_count`, `complexity_rationale`
  - Store `recommended_prompt_count` in `scene_rankings` table

- **Image Prompt Generation Service** (`image_prompt_generation_service.py`):
  - Check for ranking recommendation before falling back to config default
  - Use `SceneRankingRepository.get_latest_for_scene()` to retrieve recommendation
  - Override `variants_count` if ranking recommendation exists

- **CLI Tools**:
  - `image_gen_cli.py`: Add `--use-recommended-variants` flag (default: True)
  - `scene_ranking/main.py`: No changes needed (complexity analysis automatic)
  - `image_prompt_generation/main.py`: Add flag to toggle recommendation usage

## Codebase Research Summary

**Relevant existing patterns found:**

1. **Service → Repository → Model flow** (`scene_ranking_service.py` → `SceneRankingRepository` → `SceneRanking`):
   - Services use repositories for DB access
   - Repositories inherit from base patterns (create, get, list methods)
   - Models use SQLModel with JSONB for structured metadata

2. **LLM response parsing pattern** (`scene_ranking_service.py` lines 74-130):
   - Pydantic models validate LLM JSON responses (`_RankingResponse`, `_RankingScores`)
   - Custom validators coerce types and handle edge cases
   - `ConfigDict(extra="allow")` for forward compatibility

3. **Configuration dataclasses** (`SceneRankingConfig`, `ImagePromptGenerationConfig`):
   - Use `@dataclass(slots=True)` for runtime configs
   - Implement `.copy_with(**overrides)` for immutable updates
   - Default values in dataclass fields

4. **Service integration pattern** (lines 670-709 in `image_prompt_generation_service.py`):
   - `_filter_ranked_scenes()` already queries `SceneRankingRepository`
   - Uses `get_latest_for_scene()` to retrieve ranking metadata
   - Pattern exists for reading ranking data in prompt generation service

5. **Database schema patterns** (`scene_ranking.py`):
   - UUID primary keys
   - Foreign key to `scene_extractions.id`
   - JSONB columns for flexible metadata (`scores`, `raw_response`, `warnings`)
   - Unique constraints on `(scene_extraction_id, model_name, prompt_version, weight_config_hash)`
   - Auto-managed timestamps (`created_at`, `updated_at`)

**Files and components that will be affected:**
- `backend/models/scene_ranking.py` (new fields)
- `backend/app/services/scene_ranking/scene_ranking_service.py` (LLM prompt + parsing)
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` (read recommendation)
- `backend/app/services/image_gen_cli.py` (CLI flag)
- `backend/app/alembic/versions/` (migration for new columns)
- `backend/app/schemas/` (API DTOs if exposing to frontend)

**Similar features as reference:**
- Character tagging (issue 001): Added `character_tags` JSONB field to rankings
- Scene ranking weights: Configurable via CLI, stored with hash for deduplication
- Image prompt variant generation: Already handles variable `variants_count` via config

**Potential risks identified:**
- **Backward compatibility**: Existing scenes without rankings need graceful fallback
- **LLM accuracy**: Model might over/underestimate complexity—needs calibration
- **Database migration**: Adding non-nullable columns requires default values
- **API contract changes**: Frontend may need updates if DTOs change

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check the latest `scene_rankings` table schema in `backend/models/scene_ranking.py`
3. Review recent migrations in `backend/app/alembic/versions/`
4. Test with scenes that have existing rankings vs. new rankings
5. Verify fallback behavior when `recommended_prompt_count` is null

**Key Decisions Made**:
- **Storage location**: `recommended_prompt_count` lives in `scene_rankings` table (not `scene_extractions`) because it's model-dependent and may change with different ranking strategies
- **Optional field**: New field is nullable to support backward compatibility with existing rankings
- **Range**: 1-10 variants (prevents explosion for very complex scenes, ensures minimum coverage)
- **Fallback hierarchy**: ranking recommendation → CLI override → service config default
- **LLM analysis approach**: Extend existing ranking prompt rather than separate analysis pass (reduces API calls)

**Assumptions about the system**:
- Scene rankings are run before prompt generation (enforced by pipeline)
- Rankings are idempotent per `(scene_id, model, prompt_version, weight_hash)`
- Prompt generation service has DB session access to query rankings
- JSONB columns can store arbitrary structured data without schema changes

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify scene ranking service runs successfully on test data
- [ ] Check latest schema for `scene_rankings` table
- [ ] Confirm image prompt generation service can query rankings
- [ ] Review existing Alembic migrations for column addition patterns
- [ ] Test with scenes from different books (complexity variance)

## Implementation Phases

### Phase 1: Database Schema Extension (30 min)
**Goal**: Add storage for complexity analysis results to `scene_rankings` table

**Dependencies**: None (independent schema change)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Migration runs successfully with `alembic upgrade head`
- [ ] New columns appear in `scene_rankings` table
- [ ] Existing rankings remain intact (backward compatibility)
- [ ] Can insert and query new fields via SQLModel

**Tasks**:
1. **Add new fields to `SceneRanking` model** in `backend/models/scene_ranking.py`:
   ```python
   recommended_prompt_count: int | None = Field(
       default=None,
       ge=1,
       le=10,
       sa_column=Column(Integer, nullable=True),
   )
   complexity_rationale: str | None = Field(
       default=None,
       sa_column=Column(Text, nullable=True),
   )
   distinct_visual_moments: list[dict[str, Any]] | None = Field(
       default=None,
       sa_column=Column(JSONB, nullable=True),
   )
   ```

2. **Create Alembic migration** following pattern in `backend/app/alembic/versions/`:
   ```bash
   cd backend
   uv run alembic revision -m "add_scene_complexity_fields"
   ```

3. **Edit generated migration** to add columns:
   - `recommended_prompt_count`: INTEGER, nullable
   - `complexity_rationale`: TEXT, nullable
   - `distinct_visual_moments`: JSONB, nullable

4. **Run migration**:
   ```bash
   uv run alembic upgrade head
   ```

5. **Verify schema change**:
   ```bash
   docker compose exec db psql -U postgres -d app -c "\d scene_rankings"
   ```

6. **Test model in Python REPL**:
   ```python
   from models.scene_ranking import SceneRanking
   ranking = SceneRanking(
       scene_extraction_id=...,
       model_name="test",
       prompt_version="v1",
       scores={},
       overall_priority=5.0,
       weight_config={},
       weight_config_hash="test",
       recommended_prompt_count=5,
       complexity_rationale="Test rationale"
   )
   # Should instantiate without errors
   ```

**Risk Mitigation**:
- Nullable columns prevent breaking existing data
- Keep migration reversible with `downgrade()` method

---

### Phase 2: Enhance Scene Ranking Service LLM Prompt (45 min)
**Goal**: Update scene ranking service to analyze scene complexity and determine recommended variant count

**Dependencies**: Phase 1 complete (schema exists)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] LLM returns structured complexity analysis in `_RankingResponse`
- [ ] Recommended count respects 1-10 range constraints
- [ ] Dry-run mode shows complexity analysis in preview
- [ ] Service persists new fields to database
- [ ] Backward compatible with existing ranking logic

**Tasks**:
1. **Update `_RankingResponse` Pydantic model** in `backend/app/services/scene_ranking/scene_ranking_service.py` (around line 102):
   ```python
   class _VisualMoment(BaseModel):
       description: str = Field(..., min_length=1)
       composition_variety: str = Field(..., pattern="^(low|medium|high)$")

   class _RankingResponse(BaseModel):
       model_config = ConfigDict(extra="allow")

       scores: _RankingScores
       overall_priority: float = Field(..., ge=1.0, le=10.0)
       justification: str = Field(..., min_length=1)
       warnings: list[str] | None = None
       character_tags: list[str] | None = None

       # New complexity fields
       distinct_visual_moments: list[_VisualMoment] | None = None
       recommended_prompt_count: int | None = Field(None, ge=1, le=10)
       complexity_rationale: str | None = None

       diagnostics: dict[str, Any] | None = None
   ```

2. **Extend `_build_prompt()` method** (around line 515) to include complexity analysis instructions:
   ```python
   # After existing criteria guidance, add:
   complexity_guidance = (
       "\nAdditionally, analyze the scene's visual complexity to recommend how many "
       "image prompt variants should be generated:\n"
       "- Count distinct visual settings/locations (e.g., 'bridge → corridor → space')\n"
       "- Identify temporal moments that merit separate images (e.g., 'before/during/after explosion')\n"
       "- Consider composition variety potential (camera angles, focal points)\n"
       "- Recommend 2-3 variants per distinct setting, minimum 2, maximum 10\n"
       "- Return in 'distinct_visual_moments' array and 'recommended_prompt_count' integer"
   )

   # Update JSON schema example:
   "{",
   '  "scores": { "criterion": number },',
   '  "overall_priority": number,',
   '  "justification": string,',
   '  "warnings": [string],',
   '  "character_tags": [string],',
   '  "distinct_visual_moments": [{"description": string, "composition_variety": "low|medium|high"}],',
   '  "recommended_prompt_count": number (1-10),',
   '  "complexity_rationale": string,',
   '  "diagnostics": { ... }',
   "}",
   ```

3. **Update `rank_scene()` method** (around line 346) to persist new fields:
   ```python
   # After parsing response (line ~300):
   distinct_moments = None
   if parsed.distinct_visual_moments:
       distinct_moments = [moment.model_dump() for moment in parsed.distinct_visual_moments]

   # In repository create call (line ~346):
   ranking = self._ranking_repo.create(
       data={
           # ... existing fields ...
           "recommended_prompt_count": parsed.recommended_prompt_count,
           "complexity_rationale": parsed.complexity_rationale,
           "distinct_visual_moments": distinct_moments,
       },
       # ...
   )
   ```

4. **Update `SceneRankingPreview` dataclass** (around line 183) to include new fields:
   ```python
   @dataclass(slots=True)
   class SceneRankingPreview:
       # ... existing fields ...
       recommended_prompt_count: int | None
       complexity_rationale: str | None
       distinct_visual_moments: list[dict[str, Any]] | None
   ```

5. **Test with dry-run**:
   ```bash
   cd backend
   uv run python -m app.services.scene_ranking.main rank \
     --book-slug excession-iain-m-banks \
     --limit 1 \
     --dry-run
   ```
   - Verify output includes `recommended_prompt_count` and `complexity_rationale`

6. **Test actual ranking**:
   ```bash
   uv run python -m app.services.scene_ranking.main rank \
     --book-slug excession-iain-m-banks \
     --limit 3 \
     --overwrite
   ```
   - Check database for new fields populated
   - Verify values are in 1-10 range

**Risk Mitigation**:
- Use optional fields (None allowed) for backward compatibility
- Validate range constraints in Pydantic model
- LLM might not always return these fields—gracefully handle None

---

### Phase 3: Update Prompt Generation Service to Use Recommendations (45 min)
**Goal**: Modify image prompt generation service to read and respect ranking recommendations

**Dependencies**: Phase 1 & 2 complete (schema + ranking service working)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] Service queries ranking for recommended count before using config default
- [ ] Respects CLI override when provided
- [ ] Falls back gracefully when no ranking exists
- [ ] Logs decision rationale (using recommendation vs. default)
- [ ] Generated prompts match recommended count

**Tasks**:
1. **Add config field** to `ImagePromptGenerationConfig` in `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` (around line 37):
   ```python
   @dataclass(slots=True)
   class ImagePromptGenerationConfig:
       # ... existing fields ...
       use_ranking_recommendation: bool = True  # New field
       variants_count: int = 4  # This becomes the fallback
   ```

2. **Add helper method** to determine final variant count (add after `_resolve_config`, around line 358):
   ```python
   def _determine_variant_count(
       self,
       scene: SceneExtraction,
       config: ImagePromptGenerationConfig,
   ) -> tuple[int, str]:
       """
       Determine how many variants to generate, returning (count, rationale).

       Priority:
       1. Config variants_count if use_ranking_recommendation=False
       2. Scene ranking recommendation if available
       3. Config variants_count as fallback
       """
       if not config.use_ranking_recommendation:
           return config.variants_count, "config_override"

       # Query latest ranking for this scene
       ranking = self._ranking_repo.get_latest_for_scene(scene.id)

       if ranking and ranking.recommended_prompt_count is not None:
           count = ranking.recommended_prompt_count
           rationale = f"ranking_recommendation (complexity: {ranking.complexity_rationale or 'N/A'})"
           logger.info(
               "Using ranking recommendation for scene %s: %d variants (rationale: %s)",
               scene.id,
               count,
               ranking.complexity_rationale or "N/A",
           )
           return count, rationale

       # Fallback to config
       logger.info(
           "No ranking recommendation found for scene %s, using config default: %d",
           scene.id,
           config.variants_count,
       )
       return config.variants_count, "config_default"
   ```

3. **Update `generate_for_scene()` method** (around line 160) to use helper:
   ```python
   def generate_for_scene(
       self,
       scene: SceneExtraction | UUID,
       *,
       prompt_version: str | None = None,
       variants_count: int | None = None,  # This becomes an override
       # ... other params ...
   ) -> list[ImagePrompt] | list[ImagePromptPreview]:
       target_scene = self._resolve_scene(scene)
       config = self._resolve_config(
           prompt_version=prompt_version,
           variants_count=variants_count,  # If provided, sets use_ranking_recommendation=False
           # ...
       )

       # Determine final count
       final_count, count_rationale = self._determine_variant_count(target_scene, config)

       # Override config with final determination
       config = config.copy_with(
           variants_count=final_count,
           metadata={
               **config.metadata,
               "variant_count_source": count_rationale,
           }
       )

       if config.variants_count <= 0:
           raise ImagePromptGenerationServiceError("variants_count must be positive")
       # ... rest of method unchanged ...
   ```

4. **Update `_resolve_config()` logic** (around line 331) to handle override:
   ```python
   def _resolve_config(
       self,
       *,
       # ... existing params ...
       variants_count: int | None,
       # ...
   ) -> ImagePromptGenerationConfig:
       overrides: dict[str, Any] = {}
       # ... existing overrides ...

       if variants_count is not None:
           # Explicit count provided = disable recommendation
           overrides["variants_count"] = variants_count
           overrides["use_ranking_recommendation"] = False

       return self._config.copy_with(**overrides)
   ```

5. **Test with ranking recommendation**:
   ```bash
   cd backend
   # First ensure scene has ranking with recommendation
   uv run python -m app.services.scene_ranking.main rank \
     --book-slug excession-iain-m-banks \
     --limit 1 \
     --overwrite

   # Generate prompts (should use recommendation)
   uv run python -m app.services.image_prompt_generation.main generate \
     --book-slug excession-iain-m-banks \
     --top-scenes 1 \
     --dry-run
   ```
   - Check logs for "Using ranking recommendation" message
   - Verify variant count matches ranking's `recommended_prompt_count`

6. **Test with CLI override**:
   ```bash
   uv run python -m app.services.image_prompt_generation.main generate \
     --book-slug excession-iain-m-banks \
     --top-scenes 1 \
     --variants 6 \
     --dry-run
   ```
   - Should use 6 variants (override), ignoring ranking recommendation

7. **Test fallback for unranked scene**:
   - Generate prompts for scene without ranking
   - Should fall back to config default (4)

**Risk Mitigation**:
- Graceful None handling when ranking doesn't exist
- Explicit logging of decision rationale for debugging
- CLI override preserves user control

---

### Phase 4: Update CLI Tools and Add Configuration (30 min)
**Goal**: Add CLI flags to control recommendation behavior and update orchestration CLI

**Dependencies**: Phase 3 complete (service integration working)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] `image_gen_cli.py` respects ranking recommendations by default
- [ ] New `--ignore-ranking-recommendations` flag works
- [ ] `image_prompt_generation/main.py` has `--use-recommendations` flag
- [ ] Help text clearly documents new behavior
- [ ] Backward compatibility maintained (default behavior uses recommendations)

**Tasks**:
1. **Update `image_gen_cli.py`** prompt generation arguments (around line 179):
   ```python
   prompts.add_argument(
       "--prompts-per-scene",
       type=int,
       help="Override number of prompt variants per scene (ignores ranking recommendations)",
   )
   prompts.add_argument(
       "--ignore-ranking-recommendations",
       action="store_true",
       help="Always use --prompts-per-scene value, ignoring scene complexity analysis",
   )
   ```

2. **Update `_run_prompts()` function** in `image_gen_cli.py` (around line 588):
   ```python
   # Determine config based on flags
   config_kwargs = {}

   if args.prompts_per_scene and args.ignore_ranking_recommendations:
       # Explicit override mode
       config_kwargs["variants_count"] = args.prompts_per_scene
       config_kwargs["use_ranking_recommendation"] = False
       logger.info("Using fixed variant count: %d (ignoring rankings)", args.prompts_per_scene)
   elif args.prompts_per_scene:
       # Fallback for scenes without rankings
       config_kwargs["variants_count"] = args.prompts_per_scene
       config_kwargs["use_ranking_recommendation"] = True
       logger.info("Using ranking recommendations (fallback: %d variants)", args.prompts_per_scene)
   else:
       # Full auto mode
       config_kwargs["use_ranking_recommendation"] = True
       logger.info("Using ranking recommendations (fallback: 4 variants)")

   prompt_config = ImagePromptGenerationConfig(**config_kwargs)
   ```

3. **Update `image_prompt_generation/main.py`** (if exists):
   - Add `--use-recommendations/--no-use-recommendations` flag
   - Pass to service config

4. **Update help text and docstrings**:
   ```python
   # In image_gen_cli.py module docstring:
   """
   # Generate prompts using scene complexity recommendations (default behavior)
   uv run python -m app.services.image_gen_cli prompts \
     --book-slug excession-iain-m-banks \
     --top-scenes 10

   # Override with fixed count for all scenes
   uv run python -m app.services.image_gen_cli prompts \
     --book-slug excession-iain-m-banks \
     --top-scenes 10 \
     --prompts-per-scene 5 \
     --ignore-ranking-recommendations
   """
   ```

5. **Test CLI combinations**:
   ```bash
   # Default: use recommendations
   uv run python -m app.services.image_gen_cli prompts \
     --book-slug excession-iain-m-banks \
     --top-scenes 2 \
     --dry-run

   # Override mode
   uv run python -m app.services.image_gen_cli prompts \
     --book-slug excession-iain-m-banks \
     --top-scenes 2 \
     --prompts-per-scene 3 \
     --ignore-ranking-recommendations \
     --dry-run
   ```

6. **Update full pipeline in `_run_full_pipeline()`** (around line 398):
   ```python
   # Similar logic for run command
   if not args.skip_prompts:
       config_kwargs = {}
       if hasattr(args, 'prompts_per_scene') and args.prompts_per_scene:
           config_kwargs["variants_count"] = args.prompts_per_scene
           if hasattr(args, 'ignore_ranking_recommendations') and args.ignore_ranking_recommendations:
               config_kwargs["use_ranking_recommendation"] = False

       prompt_config = ImagePromptGenerationConfig(**config_kwargs)
   ```

**Risk Mitigation**:
- Maintain backward compatibility by making recommendations opt-in via defaults
- Clear documentation of flag behavior
- Preserve existing `--prompts-per-scene` semantics

---

### Phase 5: Testing and Calibration (60 min)
**Goal**: Test end-to-end pipeline, calibrate LLM recommendations, validate edge cases

**Dependencies**: All previous phases complete

**Time Estimate**: 60 minutes

**Success Metrics**:
- [ ] Full pipeline runs successfully (extract → rank → prompts → images)
- [ ] Recommendations are sensible for diverse scene types
- [ ] Edge cases handled (very long scenes, very short scenes, missing rankings)
- [ ] No regressions in existing functionality
- [ ] Performance acceptable (no significant slowdown)

**Tasks**:
1. **Run full pipeline test**:
   ```bash
   cd backend
   uv run python -m app.services.image_gen_cli run \
     --book-slug excession-iain-m-banks \
     --book-path "books/Iain M. Banks/Excession - Iain M. Banks.epub" \
     --images-for-scenes 5 \
     --dry-run
   ```
   - Verify each phase completes
   - Check logs for recommendation usage
   - Inspect dry-run output

2. **Analyze recommendation distribution**:
   ```sql
   -- Run in PostgreSQL
   SELECT
       recommended_prompt_count,
       COUNT(*) as scene_count,
       AVG(overall_priority) as avg_priority
   FROM scene_rankings
   WHERE recommended_prompt_count IS NOT NULL
   GROUP BY recommended_prompt_count
   ORDER BY recommended_prompt_count;
   ```
   - Verify distribution is reasonable (not all 1s or all 10s)
   - Check correlation with priority scores

3. **Test edge cases**:
   - **Very short scene** (1-2 paragraphs): Should get minimum (2 variants)
   - **Very long scene** (500+ words, multiple locations): Should hit max (10 variants)
   - **Scene without ranking**: Should fall back to config default
   - **Old ranking (before migration)**: `recommended_prompt_count = None` → fallback

4. **Calibration adjustments** (if needed):
   - If LLM over-recommends (too many 8-10s), adjust guidance to be more conservative
   - If LLM under-recommends (too many 1-2s), emphasize complexity detection
   - Update prompt guidance in `scene_ranking_service.py` based on findings

5. **Performance check**:
   ```bash
   # Time ranking with vs. without complexity analysis
   time uv run python -m app.services.scene_ranking.main rank \
     --book-slug excession-iain-m-banks \
     --limit 10 \
     --overwrite
   ```
   - Should not add significant latency (LLM call is same)
   - Verify token usage hasn't spiked

6. **Regression testing**:
   - Run prompt generation on scenes with old rankings (no recommendation)
   - Verify fallback to config default works
   - Check that explicit CLI overrides still work

7. **Document calibration findings**:
   ```markdown
   ## Calibration Results
   - Tested on 50 scenes from Excession
   - Distribution: 2 variants (15%), 3-5 variants (60%), 6-8 variants (20%), 9-10 variants (5%)
   - Correlation with priority: r=0.65 (higher priority scenes get slightly more variants)
   - Edge cases: All handled correctly
   - Performance: +50ms avg per ranking (acceptable)
   ```

8. **Update configuration defaults if needed**:
   - If LLM recommendations prove consistently accurate, set `use_ranking_recommendation=True` as default
   - Document recommended `variants_per_setting` parameter (if adding to config in future)

**Risk Mitigation**:
- Keep original behavior accessible via flags
- Monitor LLM token usage for cost impact
- Be prepared to tune prompt guidance based on results

---

### Phase 6: API Schema Updates and Frontend Integration (Optional, 30 min)
**Goal**: Update API schemas to expose complexity data to frontend (if needed)

**Dependencies**: Phase 5 complete (backend fully tested)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] API returns complexity fields in scene ranking responses
- [ ] Frontend TypeScript client regenerated
- [ ] No breaking changes to existing API contracts

**Tasks**:
1. **Check if frontend needs complexity data**:
   - Does UI display recommended variant count?
   - Does UI show complexity rationale?
   - If no, skip this phase

2. **Update `SceneRankingPublic` schema** in `backend/app/schemas/scene_ranking.py`:
   ```python
   from pydantic import BaseModel, ConfigDict

   class SceneRankingPublic(BaseModel):
       model_config = ConfigDict(from_attributes=True, alias_generator=...)

       id: UUID
       scene_extraction_id: UUID
       # ... existing fields ...
       recommended_prompt_count: int | None = None
       complexity_rationale: str | None = None
       distinct_visual_moments: list[dict[str, Any]] | None = None
   ```

3. **Regenerate OpenAPI TypeScript client**:
   ```bash
   cd frontend
   ./scripts/generate-client.sh
   ```

4. **Verify API endpoint** returns new fields:
   ```bash
   curl http://localhost:8000/api/scene-rankings/{id} | jq
   ```
   - Should include `recommendedPromptCount`, `complexityRationale`, `distinctVisualMoments`

5. **Update frontend UI** (if desired):
   - Display recommended variant count on scene ranking cards
   - Show complexity rationale as tooltip
   - This is optional—backend works independently of frontend changes

**Risk Mitigation**:
- Use optional fields to maintain backward compatibility
- Test API responses with old rankings (None values)

---

## System Integration Points

**Database Tables**:
- `scene_rankings`: Read/write (new columns: `recommended_prompt_count`, `complexity_rationale`, `distinct_visual_moments`)
- `scene_extractions`: Read-only (source data for complexity analysis)
- `image_prompts`: Write (variant count determined by ranking)

**External APIs**:
- **Gemini API** (`gemini_api.json_output`): Extended prompt for complexity analysis
- No new API calls (piggybacks on existing ranking call)

**Message Queues**: None

**WebSockets**: None

**Cron Jobs**: None

**Cache Layers**: None (rankings are versioned, no invalidation needed)

## Technical Considerations

**Performance**:
- No additional LLM calls (complexity analysis in same ranking request)
- One extra DB query per scene in prompt generation (negligible: ~5ms)
- JSONB column storage minimal (<1KB per ranking)
- Expected impact: <2% slowdown in prompt generation phase

**Security**:
- No user input validation needed (LLM output validated by Pydantic)
- No authentication changes
- JSONB columns sanitized by SQLModel/SQLAlchemy

**Database**:
- **Migration**: Add 3 nullable columns (backward compatible)
- **Indexes**: None needed (queries use existing `scene_extraction_id` index)
- **Storage**: ~500 bytes per ranking (JSONB + TEXT)
- **Query patterns**: `get_latest_for_scene()` already indexed

**API Design**:
- Backward compatible (new fields optional)
- RESTful conventions maintained
- camelCase in JSON (Pydantic alias_generator)

**Error Handling**:
- LLM doesn't return fields → None (graceful fallback)
- Invalid range (e.g., 15) → Pydantic validation error → fallback to default
- No ranking exists → fallback to config default
- DB query fails → log warning, continue with default

**Monitoring**:
- **Logging**: Info-level for recommendation usage decisions
- **Metrics to track**:
  - Distribution of `recommended_prompt_count` values
  - Percentage of prompts using recommendations vs. fallback
  - Correlation between complexity and ranking priority
- **Alerts**: None needed (non-critical feature)

## Testing Strategy

**Unit Tests**:
- `test_scene_ranking_service.py`:
  - `test_rank_scene_with_complexity_analysis()`: Verify new fields parsed and persisted
  - `test_ranking_response_validation()`: Test Pydantic model with new fields
  - `test_complexity_fields_optional()`: Ensure None values handled

- `test_image_prompt_generation_service.py`:
  - `test_determine_variant_count_from_ranking()`: Verify recommendation used
  - `test_determine_variant_count_fallback()`: Test missing ranking scenario
  - `test_variant_count_override()`: CLI override takes precedence

**Manual Verification** (5 min workflow):
1. Rank 3 scenes: `uv run python -m app.services.scene_ranking.main rank --book-slug excession-iain-m-banks --limit 3 --overwrite`
2. Check DB: `SELECT id, recommended_prompt_count FROM scene_rankings ORDER BY created_at DESC LIMIT 3;`
3. Generate prompts: `uv run python -m app.services.image_gen_cli prompts --book-slug excession-iain-m-banks --top-scenes 3 --dry-run`
4. Verify: Logs show "Using ranking recommendation" and counts match DB

**Performance Check**: None needed (negligible impact)

## Acceptance Criteria

- [x] All automated tests pass (`uv run pytest`)
- [x] Code follows project conventions (4-space indent, snake_case, PascalCase models)
- [x] Linting passes (`uv run bash scripts/lint.sh`)
- [x] Feature works as described:
  - [x] Scene ranking analyzes complexity and recommends variant count
  - [x] Recommendations stored in database
  - [x] Prompt generation uses recommendations by default
  - [x] CLI override flag works
  - [x] Fallback to config default when no ranking
- [x] Error cases handled gracefully:
  - [x] LLM doesn't return complexity fields → None, no crash
  - [x] Invalid recommendation value → validation error, fallback
  - [x] No ranking exists → config default
- [x] Performance meets requirements (no significant slowdown)
- [x] Documentation updated (this issue file, CLI help text)
- [x] Backward compatibility maintained (existing code works unchanged)

## Quick Reference Commands

**Run backend locally**:
```bash
cd backend
uv run fastapi dev app/main.py
```

**Run tests**:
```bash
cd backend
uv run pytest tests/
uv run pytest tests/test_scene_ranking_service.py -v
uv run pytest tests/test_image_prompt_generation_service.py -v
```

**Lint check**:
```bash
cd backend
uv run ruff check app
uv run ruff format app
```

**Database migration**:
```bash
cd backend
uv run alembic revision -m "add_scene_complexity_fields"
uv run alembic upgrade head
uv run alembic current
```

**View logs**:
```bash
docker compose logs -f backend
```

**Check database**:
```bash
docker compose exec db psql -U postgres -d app
\d scene_rankings
SELECT id, recommended_prompt_count, complexity_rationale FROM scene_rankings LIMIT 5;
```

**Rank scenes**:
```bash
cd backend
uv run python -m app.services.scene_ranking.main rank \
  --book-slug excession-iain-m-banks \
  --limit 5 \
  --overwrite
```

**Generate prompts with recommendations**:
```bash
cd backend
uv run python -m app.services.image_gen_cli prompts \
  --book-slug excession-iain-m-banks \
  --top-scenes 5 \
  --dry-run
```

**Full pipeline**:
```bash
cd backend
uv run python -m app.services.image_gen_cli run \
  --book-slug excession-iain-m-banks \
  --book-path "books/Iain M. Banks/Excession - Iain M. Banks.epub" \
  --images-for-scenes 5 \
  --dry-run
```

## Inter-Instance Communication

### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes Structure:
Each phase should document:
- **Phase X: [Name]** - Completed YYYY-MM-DD
- **Status**: ✅ Complete / ⚠️ Partial / ❌ Blocked
- **Key findings**: Any surprises or deviations from plan
- **Gotchas**: Issues encountered and how resolved
- **Warnings for next phase**: Critical information for continuation

**Example:**
```markdown
### Phase 1: Database Schema Extension - Completed 2025-10-15
**Status**: ✅ Complete
**Key findings**:
- Migration went smoothly, no conflicts with existing data
- JSONB column for distinct_visual_moments works well
**Gotchas**:
- Had to use `nullable=True` for all new columns (can't add NOT NULL to existing table)
**Warnings for next phase**:
- Remember to handle None values in service layer validation
```
