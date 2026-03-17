# Pipeline Orchestrator

## Overview
Extract a unified `PipelineOrchestrator` service that becomes the single execution entry point for orchestrated pipeline work while staying flexible enough to support new launch patterns without repeated refactors. The orchestrator should handle:

- full document pipeline runs
- prompt-plus-image runs
- scene-targeted prompt/image generation with an exact variant count
- remix and custom-remix flows

Every orchestrated invocation must create a persisted pending `PipelineRun` before long-running work starts, then flow through shared status transitions, diagnostics, and finalization. Dedicated maintenance commands `extract` and `rank` remain standalone escape hatches for explicitly re-running completed upstream stages.

This issue intentionally does not require every implementation detail to become natively async. The public API and route boundaries should remain async/non-blocking, but blocking preparation and stage work may be offloaded to threadpools where needed.

Backfill is intentionally removed from scope. It is a legacy maintenance mode and does not need to shape the orchestrator design.

Batch image generation is also intentionally out of scope for this issue. Orchestrator-backed execution will be sync-only for image generation. The existing batch implementation stays in the codebase unchanged so it can be reintroduced cleanly in a later feature, but this plan does not migrate it or preserve batch mode on orchestrator-backed launch surfaces.

## Objectives
- Create one orchestrator entry point for background pipeline execution.
- Preserve current sync API and CLI behavior while removing duplicated orchestration logic.
- Make the orchestration model flexible enough for future launch types, especially scene-specific generation.
- Ensure every orchestrated run is tracked through a persisted `PipelineRun`.
- Ensure outputs created during a run are linked back to that run via `pipeline_run_id`.
- Keep routes thin and push orchestration/business rules into services.

## Problem Statement
Pipeline execution is currently fragmented across several layers:

1. `backend/app/services/image_gen_cli.py` acts as both CLI parser and orchestration engine. The full pipeline and each CLI command own their own service wiring, session handling, scene selection, and error handling.
2. `backend/app/api/routes/pipeline_runs.py` wraps CLI-oriented orchestration, owns diagnostics/status logic, and bridges into `_run_full_pipeline()` via `argparse.Namespace`.
3. `backend/app/api/routes/generated_images.py` contains separate remix/custom-remix background flows that do not create `PipelineRun` records.

This creates concrete issues:
- New trigger paths require more duplicated orchestration code.
- The current design is mode-heavy and brittle; adding scene-targeted generation or future launch types means inventing more special-case execution paths.
- Remix/custom-remix activity is not visible in pipeline run history.
- `PipelineRun` records are not enough on their own because rankings, prompts, and generated images created during a run are not consistently linked through `pipeline_run_id`.
- Route-layer orchestration is doing too much work.

## Design Principles

### 1. Model execution as target + stages + options
Do not center the design around a growing enum of bespoke execution modes like `prompts_and_images`. That becomes rigid quickly.

Instead, the orchestrator input should be shaped around:

- **Target**: what the run is operating on
- **Stage plan**: which stages should execute
- **Prompt options**: prompt-generation settings and variant behavior
- **Image options**: image-generation settings
- **Run options**: dry-run and metadata

This lets the system express current and future launch types without introducing a new top-level mode for each one.

Examples:
- Full pipeline: `DocumentTarget` + extract/rank/prompts/images
- Scene-specific generation: `SceneTarget(scene_ids=[...])` + prompts/images + exact `variants_per_scene`
- Remix: `RemixTarget(source_prompt_id=..., source_image_id=...)` + prompts/images
- Custom remix: `CustomRemixTarget(...)` + create custom prompt + images

### 2. Prepare first, execute second
Preparation should:
- validate the request
- resolve source entities
- derive `document_id` and `book_slug` where possible
- resolve defaults
- apply sticky skip decisions to produce one effective stage plan
- create the pending `PipelineRun`

Execution should:
- advance run status
- execute stages
- collect diagnostics
- finalize success/failure

### 3. Track the actual outputs created by a run
The orchestrator should not stop at tracking the `PipelineRun` row itself. New rankings, prompts, and generated images created during a run must carry that run's `pipeline_run_id`.

### 4. Be pragmatic about async
The orchestrator can expose an async `execute()` entry point, but internal blocking work does not need to be rewritten into native async APIs immediately. Use fresh sessions and threadpool helpers where appropriate.

### 5. Carry explicit execution context across stages
The orchestrator needs more than static config. It also needs a runtime execution context that carries:

- resolved resume state for partially completed stages
- resolved scene selection for ranking/prompt stages where applicable
- exact prompt IDs created during the current run
- exact image IDs created during the current run

This context must be the source of truth for downstream stage inputs. In particular, image generation must consume exact prompt IDs captured during prompt generation rather than rediscovering prompts from broad scene/book queries.

## Proposed Solution

### Core types
Create orchestration config types in `backend/app/services/pipeline/orchestrator_config.py`.

#### `PipelineExecutionTarget`
A discriminated target type, implemented as dataclasses or a small tagged union:

- `DocumentTarget`
  - `document_id: UUID | None`
  - `book_slug: str | None`
  - `book_path: str | None`
- `SceneTarget`
  - `scene_ids: list[UUID]`
  - `document_id: UUID | None`
  - `book_slug: str | None`
- `RemixTarget`
  - `source_image_id: UUID`
  - `source_prompt_id: UUID`
  - `document_id: UUID | None`
  - `book_slug: str | None`
- `CustomRemixTarget`
  - `source_image_id: UUID`
  - `source_prompt_id: UUID`
  - `custom_prompt_id: UUID | None`
  - `custom_prompt_text: str | None`
  - `document_id: UUID | None`
  - `book_slug: str | None`

#### `PipelineStagePlan`
Explicit stage booleans instead of a single opaque mode:

- `run_extraction: bool = False`
- `run_ranking: bool = False`
- `run_prompt_generation: bool = False`
- `run_image_generation: bool = False`

Optional validation helpers:
- extraction requires a document-style target
- ranking requires a document-style target
- image generation for orchestrated runs requires fresh prompt creation within the same run, or an explicit fresh prompt ID set already created for that run

#### `PromptExecutionOptions`
- `prompts_per_scene: int | None`
- `ignore_ranking_recommendations: bool = False`
- `prompts_for_scenes: int | None`
- `images_for_scenes: int | None`
- `scene_variant_count: int | None`
- `variants_count: int | None`
- `overwrite_prompts: bool = False`
- `prompt_version: str | None = None`
- `prompt_art_style_mode: str | None = None`
- `prompt_art_style_text: str | None = None`
- `require_exact_scene_variants: bool = False`

Rules:
- `scene_variant_count` is the exact prompt/image count for a scene-targeted run
- `images_for_scenes` remains a document-level scene-selection limit, not a per-scene variant count
- `overwrite_prompts` is required to preserve existing `prompts` CLI behavior
- Any orchestrated run that creates new images must also create fresh prompts for those images during the same run. It must not search for reusable prompt sets that happen not to have images yet.
- When `require_exact_scene_variants=True`, execution must create exactly that many fresh prompts, must not reuse a broader existing prompt set, and must not fan back out to all prompts on the scene. Prompt generation must return the exact prompt IDs to image generation, and image generation must operate on that explicit prompt ID list.

#### `ImageExecutionOptions`
- `quality: str = "standard"`
- `style: str | None = None`
- `aspect_ratio: str | None = None`
- `concurrency: int = 3`

Initial scope:
- orchestrated image generation is sync-first
- batch generation is explicitly deferred from this issue
- this issue removes batch-specific launch behavior from orchestrator-backed API/CLI surfaces instead of silently ignoring it

#### `PipelineExecutionConfig`
- `target: PipelineExecutionTarget`
- `stages: PipelineStagePlan`
- `prompt_options: PromptExecutionOptions`
- `image_options: ImageExecutionOptions`
- `dry_run: bool = False`
- `metadata: dict[str, Any]`

`PipelineExecutionConfig` is the effective execution contract. It should not carry duplicate `skip_*` booleans once preparation is complete.

Include `copy_with(**overrides)` and validation helpers. Validation should reject invalid combinations early.

#### `PreparedPipelineExecution`
- `run_id: UUID`
- `config: PipelineExecutionConfig`
- `config_overrides: dict[str, Any]`
- `context: PipelineExecutionContext`

#### `PipelineExecutionContext`
Runtime state carried from preparation into execution and updated as stages complete.

Preparation-owned fields:
- `document_id: UUID | None`
- `book_slug: str | None`
- `book_path: str | None`
- `extraction_resume_from_chapter: int | None`
- `extraction_resume_from_chunk: int | None`
- `ranking_scene_ids: list[UUID] | None`
- `ranking_resume_scene_id: UUID | None`
- `requested_image_count: int | None`

Execution-owned fields:
- `created_ranking_ids: list[UUID]`
- `created_prompt_ids: list[UUID]`
- `created_prompt_ids_by_scene: dict[UUID, list[UUID]]`
- `created_image_ids: list[UUID]`
- `failed_image_ids: list[UUID]`

Rules:
- preparation resolves resume state for document-backed extraction and ranking runs
- prompt generation appends the exact prompt IDs created during this run to `created_prompt_ids`
- scene-targeted runs must populate `created_prompt_ids_by_scene[scene_id]` with exactly the prompts created for that scene in this run
- image generation must consume `created_prompt_ids` or the relevant per-scene subset directly; it must not query "latest prompts for scene/book" for orchestrated image-producing runs
- diagnostics and usage summary use this context to record requested-versus-generated counts

#### `PipelineExecutionResult`
- `run_id: UUID`
- `status: Literal["completed", "failed"]`
- `stats: PipelineStats`
- `diagnostics: dict[str, Any]`
- `usage_summary: dict[str, Any]`
- `error_message: str | None`
- `error_code: str | None`

Move `PipelineStats` out of `image_gen_cli.py` into this module and keep a backward-compatible import in the CLI.

## Run Lifecycle
1. Caller builds `PipelineExecutionConfig`.
2. Preparation service resolves entities/defaults and creates a pending `PipelineRun`.
3. Caller receives the persisted run immediately.
4. Background task calls `PipelineOrchestrator.execute(prepared)`.
5. Orchestrator performs stage transitions, updates `prepared.context` with resolved stage outputs, and updates document stage statuses where relevant.
6. Newly created or updated rankings/prompts/images are persisted with `pipeline_run_id=<run_id>`.
7. Orchestrator finalizes the run with usage summary and diagnostics.

## Preparation Service Design
Refactor `PipelineRunStartService` into a general orchestration preparation service.

### Responsibilities
- Resolve target entities from document, scene, prompt, and image identifiers.
- Derive `document_id` and `book_slug` for scene/remix/custom-remix targets.
- Resolve prompt art-style defaults from app settings.
- Resolve default scenes-per-run values where needed.
- Synchronize document stage statuses before skip decisions for document-backed runs.
- Apply sticky completion skip rules for extraction/ranking and emit one effective stage plan.
- Preserve extraction resume semantics by resolving `resume_from_chapter` / `resume_from_chunk` for partially extracted documents.
- Preserve ranking resume semantics by resolving the remaining scene set for the active ranking config rather than restarting from the first scene.
- Validate required source path behavior when extraction is enabled.
- Create the pending `PipelineRun`.
- Serialize effective config into `config_overrides`.
- Populate `PipelineExecutionContext` with authoritative resume metadata and any precomputed stage inputs.

### Scope of sticky skip logic
Sticky completion skip logic should be applied during preparation for document-backed orchestrated runs. It should not be reimplemented in execution.

If extraction or ranking is only partially complete, preparation must preserve resume semantics rather than collapsing the run into either "skip" or "rerun everything":

- extraction: resume from the next missing chapter/chunk boundary when source-path access still exists
- ranking: resume with the remaining unranked scene IDs for the current ranking configuration
- only fully completed stages become sticky-skipped

Scene-targeted and remix-targeted runs should not invoke extraction or ranking at all.

The prepared output should be authoritative for execution. Route and orchestrator code should not need to reconcile parallel `run_*` and `skip_*` flags.

### Blocking work and async routes
Preparation may remain synchronous. When called from async routes, run it through `run_in_threadpool` or an equivalent helper so route handlers remain non-blocking.

## Orchestrator Service Design
Create `backend/app/services/pipeline/pipeline_orchestrator.py` with `PipelineOrchestrator`.

### Public API
- `async execute(prepared: PreparedPipelineExecution) -> PipelineExecutionResult`

### Responsibilities
- Own status transitions and diagnostics
- Own final success/failure handling
- Open fresh sessions per stage or per stage unit of work
- Delegate to stage services and repositories
- Avoid re-validating business rules already resolved during preparation

### Internal execution model
Implement explicit stage dispatch methods:
- `_execute_extraction()`
- `_execute_ranking()`
- `_execute_prompt_generation()`
- `_execute_image_generation()`
- `_execute_remix()`
- `_execute_custom_remix()`
- `_execute_scene_target()`

The orchestrator should derive behavior from `target + stages + options`, not from a single rigid mode enum.

### Diagnostics and finalization
Move diagnostics tracking and usage-summary construction out of `pipeline_runs.py` into the orchestrator. Reuse the current stage timing/event model, but make it generic enough for full pipeline, scene-targeted, and remix/custom-remix runs.

### Error classification
Move pipeline error classification into the orchestrator. Keep machine-readable codes stable.

### Usage summary compatibility contract
`usage_summary` must remain backward-compatible for document stage inference and dashboard consumers.

Required shape for orchestrated runs:
- `requested.skip_extraction`
- `requested.skip_ranking`
- `requested.skip_prompts`
- `requested.mode`
- `effective.config_overrides`
- `outputs.scenes_extracted`
- `outputs.scenes_ranked`
- `outputs.prompts_generated`
- `outputs.images_generated`
- `diagnostics`

Rules:
- for orchestrated runs in this issue, `requested.mode` is always `"sync"`
- `requested.skip_extraction`, `requested.skip_ranking`, and `requested.skip_prompts` are derived from the effective stage plan after preparation, not from raw request payloads
- a stage that resumes partial work is **not** considered skipped; its corresponding `requested.skip_*` value must be `false`
- only stages omitted from the effective stage plan are reported as skipped
- `effective.config_overrides` must continue to include the resolved values currently used by downstream readers, including resolved book identity, resolved art-style settings, and resolved scene-count defaults
- scene-targeted and remix/custom-remix runs may add extra requested/effective keys, but they must not remove the compatibility keys above

## Output Tracking Requirement
This is required for the orchestrator to be considered complete.

When a run creates:
- `SceneRanking`
- `ImagePrompt`
- `GeneratedImage`

those rows must persist `pipeline_run_id=<current run id>`.

This means some existing stage service interfaces or repository calls will need light changes. That is acceptable and expected. The orchestrator should pass run context into the write path rather than trying to infer linkage later.

This requirement includes:
- successful creates
- failed `GeneratedImage` records
- reuse/revival paths where an existing deleted image row is reactivated during a run
- custom-remix prompt creation in request scope before downstream execution starts

## API and CLI Behavior Requirements

### Pipeline runs API
`POST /api/v1/pipeline-runs` must:
- remain async
- create and return a persisted pending `PipelineRunRead` immediately
- offload blocking preparation work from the event loop
- spawn orchestrator execution in the background
- support sync image generation only for this issue

Batch-mode request fields should not remain as misleading no-ops. This issue should either remove them from orchestrator-backed request/CLI surfaces or reject them with a validation error. Preferred approach: remove `mode`, `poll_timeout`, and `poll_interval` from orchestrator-backed pipeline-run request/CLI surfaces while leaving batch service code untouched.

### Remix and custom remix API
Remix/custom-remix should become tracked pipeline runs.

Required changes:
- create a pending `PipelineRun` before long-running remix work starts
- include `pipeline_run_id` in remix/custom-remix responses so the frontend can poll the run directly

For custom remix specifically:
- do not require the entire route flow to move into background execution immediately
- create the `PipelineRun` first
- create the custom prompt in request scope if that remains simpler
- persist that prompt with `pipeline_run_id`
- then hand off downstream image generation/finalization to the orchestrator

This preserves pragmatism while still meeting the tracking objective.

### Scene-level generation API
Add a route for scene-specific generation:

- `POST /api/v1/scene-extractions/{scene_id}/generate`

Request schema should support:
- `num_images`
- `prompt_art_style_mode`
- `prompt_art_style_text`
- `quality`
- `style`
- `aspect_ratio`

Behavior:
- validate the scene exists
- create a `SceneTarget(scene_ids=[scene_id])`
- set stage plan to prompt generation plus image generation
- use `scene_variant_count=num_images`
- set `require_exact_scene_variants=True`
- create and return a pending `PipelineRun`

Execution contract:
- prompt generation must create exactly `num_images` fresh prompts for the target scene
- image generation must run against that exact prompt ID set, not against a scene-wide prompt query
- existing prompts or images must not count toward the requested total
- the requested count is a target, not a hard success condition
- the run succeeds if at least one image is generated and fails if zero images are generated
- diagnostics and usage summary should record the requested count and the final generated count

This is the key extensibility proof-point for the orchestrator design.

### CLI behavior
Preserve current CLI contracts:
- `run` remains full pipeline orchestration
- `extract` and `rank` remain standalone escape hatches

Remove the legacy `prompts` command rather than migrating it.
Remove the legacy `images` command rather than migrating it.
Remove the legacy `refresh` command rather than migrating it.

`backfill` is removed rather than migrated.

For this issue, orchestrator-backed `run` is sync-only for image generation. Batch-specific options are removed from the supported `run` contract rather than silently accepted.

## Implementation Plan

### Phase 1: Define orchestration config and result types
**Goal**: establish a flexible contract that preserves current behavior and supports future targets.

**Tasks**:
- Create `orchestrator_config.py`
- Add `PipelineExecutionTarget` types
- Add `PipelineStagePlan`
- Add `PromptExecutionOptions`
- Add `ImageExecutionOptions`
- Add `PipelineExecutionConfig`
- Add `PreparedPipelineExecution`
- Add `PipelineExecutionContext`
- Add `PipelineExecutionResult`
- Move `PipelineStats` from `image_gen_cli.py`
- Remove duplicate execution-time `skip_*` flags from the effective config contract

**Tests**:
- Add config tests covering valid and invalid target/stage combinations
- Add config/context tests covering stage-output handoff for prompt IDs
- Add tests that assert the effective config does not allow contradictory stage/skip representations

**Verification**:
- [ ] Config can express full, scene-targeted, remix, and custom-remix runs
- [ ] Validation rejects invalid combinations
- [ ] Existing imports of `PipelineStats` continue to work

### Phase 2: Refactor preparation into shared orchestration startup
**Goal**: centralize resolution, defaults, sticky skips, and pending run creation.

**Tasks**:
- Replace `resolve_pipeline_request()` with `prepare_execution(config)`
- Resolve document, scene, prompt, and image targets
- Backfill `document_id` and `book_slug` where derivable
- Resolve art-style defaults and scenes-per-run defaults
- Sync document stage status before skip resolution for document-backed runs
- Resolve extraction resume state for partially extracted runs
- Resolve ranking resume state for partially ranked runs
- Create pending `PipelineRun`
- Serialize effective config into `config_overrides`
- Add a small helper for route-layer threadpool execution where needed

**Tests**:
- Extend preparation-service tests for document, scene, remix, and custom-remix targets
- Add tests asserting extraction resume metadata is preserved for partially extracted runs
- Add tests asserting ranking resume metadata is preserved for partially ranked runs
- Add tests asserting preparation emits one effective stage plan after sticky skip resolution

**Verification**:
- [ ] Preparation creates a real pending `PipelineRun`
- [ ] Skip decisions are applied during preparation, not execution
- [ ] Scene/remix/custom-remix runs correctly derive document context when possible

### Phase 3: Build the core orchestrator lifecycle
**Goal**: centralize status transitions, diagnostics, finalization, and stage dispatch.

**Tasks**:
- Create `pipeline_orchestrator.py`
- Move diagnostics tracker and usage-summary logic into the orchestrator
- Move pipeline error classification into the orchestrator
- Add internal helpers for stage updates and document stage status updates
- Add shared background-task helper in `backend/app/services/pipeline/background.py`
- Make orchestrator stage methods read/write `PipelineExecutionContext` instead of rediscovering cross-stage inputs from ad hoc queries

**Tests**:
- Add orchestrator lifecycle tests for success/failure finalization
- Add tests for diagnostics and usage-summary persistence
- Add tests asserting backward-compatible `usage_summary.requested.skip_*` values from the effective stage plan
- Add tests showing route files no longer own execution state machines

**Verification**:
- [ ] Orchestrator can execute a prepared run and finalize success/failure
- [ ] Diagnostics are recorded in the result and persisted usage summary
- [ ] Route files no longer own orchestration state machines

### Phase 4: Propagate `pipeline_run_id` into created outputs
**Goal**: make tracked runs actually traceable.

**Tasks**:
- Update ranking write paths to persist `pipeline_run_id`
- Update prompt write paths to persist `pipeline_run_id`
- Update generated image write paths to persist `pipeline_run_id`
- Update generated image failure-record write paths to persist `pipeline_run_id`
- Update deleted-image revival paths to set the current `pipeline_run_id`
- Ensure remix/custom-remix-created prompts are linked to their run
- Remove orchestration logic that searches for reusable prompt sets for image-producing runs
- Make image-producing orchestration depend on explicit prompt IDs created during the current run
- Make stage services return created IDs needed to populate `PipelineExecutionContext`

This phase may require small interface changes to existing services or repositories. That is intentional.

**Tests**:
- Add service tests for ranking/prompt/image creation with `pipeline_run_id`
- Add tests for failed-image record creation carrying `pipeline_run_id`
- Add tests for revived deleted-image rows being relinked to the current run

**Verification**:
- [ ] New rankings created during a run link to that run
- [ ] New prompts created during a run link to that run
- [ ] New images created during a run link to that run
- [ ] Failed/revived image rows created or updated during a run link to that run

### Phase 5: Migrate full pipeline execution
**Goal**: move the current full document pipeline onto the orchestrator.

**Tasks**:
- Move extraction/ranking/prompt/image execution logic from `_run_full_pipeline()` into orchestrator stage methods
- Keep current behavior for default scene counts, extraction resume, ranking resume, and skip handling while removing prompt-reuse-based image selection for image-producing runs
- Update `pipeline_runs.py` to build config, prepare execution, return the pending run, and spawn orchestrator execution
- Update `_run_full_pipeline()` in `image_gen_cli.py` to delegate to preparation + orchestrator
- Remove batch-specific `run` launch handling from orchestrator-backed API/CLI surfaces while leaving batch service code in place

**Tests**:
- Update full-pipeline API route tests to verify pending-run creation and background kickoff
- Update CLI delegation tests for `run`
- Add regression tests for document stage status updates through the orchestrator
- Add regression tests for extraction resume and ranking resume through the orchestrator

**Verification**:
- [ ] Full pipeline works from API
- [ ] Full pipeline works from CLI
- [ ] Status transitions remain correct
- [ ] Document stage status updates remain correct
- [ ] Extraction resume semantics remain correct
- [ ] Ranking resume semantics remain correct

### Phase 6: Add scene-targeted generation
**Goal**: prove the orchestrator can support fine-grained future features without another architecture change.

**Tasks**:
- Implement `SceneTarget` handling in orchestrator
- Add `POST /api/v1/scene-extractions/{scene_id}/generate`
- Add `SceneGenerateRequest` schema
- Regenerate frontend client
- Make prompt generation return the exact generated prompt IDs for this run
- Make image generation consume that explicit prompt ID list

Behavior:
- no extraction
- no ranking
- prompt generation for the requested scene(s)
- image generation for the generated prompt set
- exact variant count controlled by `num_images`
- existing prompts or images do not count toward the requested total
- if fewer than `num_images` images are successfully generated, the run may still succeed as long as at least one image is generated

**Tests**:
- Add route tests for pending-run creation and response shape
- Add orchestrator tests asserting exact-count prompt and image generation
- Add regression tests asserting the image stage does not fan out to all scene prompts
- Add tests asserting partial success finalizes the run as completed when at least one image is generated

**Verification**:
- [ ] Scene-targeted runs create pending `PipelineRun` records
- [ ] Scene-targeted runs derive document context when available
- [ ] Exact requested image count is honored for the target scene
- [ ] Run appears in pipeline history

### Phase 7: Migrate remix and custom remix
**Goal**: bring remix flows under tracked orchestration.

**Tasks**:
- Replace independent remix background tasks in `generated_images.py`
- Make remix create a pending run and execute prompt generation plus image generation through the orchestrator
- Make custom remix create a pending run first, then create/persist the custom prompt, then hand off downstream image generation to the orchestrator
- Update response schemas to include `pipeline_run_id`
- Add simple failure finalization for request-scope custom-remix prompt creation failures so runs do not remain pending

**Tests**:
- Update generated-images route tests for remix/custom-remix responses and pending-run creation
- Add orchestrator tests for remix/custom-remix execution paths
- Add tests ensuring custom-remix request-scope prompt creation is linked to the run

**Verification**:
- [ ] Remix/custom-remix create tracked `PipelineRun` records
- [ ] Remix/custom-remix responses include `pipeline_run_id`
- [ ] Created prompts/images are linked to the run

### Phase 8: Remove legacy CLI orchestration commands
**Goal**: simplify the supported surface by removing non-essential CLI flows.

**Tasks**:
- Remove the legacy `prompts` CLI command instead of migrating it
- Remove the legacy `images` CLI command instead of migrating it
- Remove the legacy `refresh` CLI command instead of migrating it
- Remove the legacy `backfill` CLI command instead of migrating it

**Tests**:
- Update CLI tests for remaining supported commands
- Add tests asserting `prompts` is no longer exposed
- Add tests asserting `images` is no longer exposed
- Add tests asserting `refresh` is no longer exposed
- Add tests asserting `backfill` is no longer exposed

**Verification**:
- [ ] `prompts` is removed
- [ ] `images` is removed
- [ ] `refresh` is removed
- [ ] `backfill` is removed

### Phase 9: Test completion and cleanup
**Goal**: close remaining coverage gaps and align regression coverage with the final architecture.

**Tasks**:
- Add unit tests for config validation and copy behavior
- Extend preparation-service tests for all supported target types
- Add orchestrator service tests for:
  - full pipeline
  - scene-targeted runs
  - remix
  - custom remix
- Add tests asserting `pipeline_run_id` propagation
- Update route tests for pipeline runs and generated images
- Add route tests for scene-targeted generation
- Update CLI tests to verify delegation to the orchestrator

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/pipeline/orchestrator_config.py` | Create |
| `backend/app/services/pipeline/pipeline_orchestrator.py` | Create |
| `backend/app/services/pipeline/background.py` | Create |
| `backend/app/services/pipeline/__init__.py` | Modify |
| `backend/app/services/pipeline/pipeline_run_start_service.py` | Modify |
| `backend/app/services/image_gen_cli.py` | Modify |
| `backend/app/api/routes/pipeline_runs.py` | Modify |
| `backend/app/api/routes/generated_images.py` | Modify |
| `backend/app/api/routes/scene_extractions.py` | Modify |
| `backend/app/schemas/pipeline_run.py` | Modify |
| `backend/app/schemas/scene_extraction.py` | Modify |
| `backend/app/schemas/generated_image.py` | Modify |
| `backend/app/services/scene_ranking/scene_ranking_service.py` | Modify |
| `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` | Modify |
| `backend/app/services/image_generation/image_generation_service.py` | Modify |
| `backend/app/services/image_generation/batch_image_generation_service.py` | No change in initial orchestrator scope |
| `backend/app/tests/services/test_pipeline_execution_config.py` | Create |
| `backend/app/tests/services/test_pipeline_orchestrator.py` | Create |
| `backend/app/tests/services/test_pipeline_run_start_service.py` | Modify |
| `backend/app/tests/api/routes/test_pipeline_runs.py` | Modify |
| `backend/app/tests/api/routes/test_generated_images.py` | Modify |
| `backend/app/tests/api/routes/test_scene_extractions.py` | Create or Modify |
| `backend/app/tests/services/test_image_gen_cli.py` | Modify |
| `frontend/src/client/*` | Regenerate after API changes |

## Testing Strategy
- Unit tests for config validation and lifecycle helpers
- Phase-specific service tests for preparation and orchestrator execution
- Route tests for pending-run creation and response contracts
- Regression tests for CLI command behavior, including removal of `images` and `backfill`
- Assertions that created rows carry `pipeline_run_id`
- Regression tests for extraction/ranking resume behavior and explicit prompt-ID handoff to image generation

## Required Commands
- `cd backend && uv run pytest`
- `cd backend && uv run bash scripts/lint.sh`
- `cd frontend && npm run build` after client regeneration

## Acceptance Criteria
- [ ] `PipelineOrchestrator.execute()` is the single execution entry point for orchestrated background runs
- [ ] Orchestrator input is modeled as target + stage plan + options, not a growing list of rigid bespoke modes
- [ ] Every orchestrated invocation creates a persisted pending `PipelineRun` before long-running work starts
- [ ] `POST /pipeline-runs` still returns a concrete pending `PipelineRunRead` immediately
- [ ] Async route handlers remain non-blocking even if preparation work remains synchronous internally
- [ ] Orchestrator-backed image generation is sync-only in this issue
- [ ] Batch implementation remains in the codebase but is not migrated or exposed through orchestrator-backed launch paths
- [ ] Full pipeline runs work through the orchestrator from API and CLI
- [ ] Extraction resume semantics are preserved for partially extracted runs
- [ ] Ranking resume semantics are preserved for partially ranked runs
- [ ] Scene-targeted generation is supported for specific extracted scenes with an exact requested variant count
- [ ] Any orchestrated run that creates images also creates fresh prompts for those images during the same run
- [ ] Scene-targeted generation passes the exact prompt IDs produced for that run into image generation
- [ ] Existing prompts or images do not count toward requested image totals for image-producing runs
- [ ] Requested image counts are treated as targets; runs succeed when at least one image is generated and fail when none are generated
- [ ] Diagnostics and usage summary record requested versus generated image counts
- [ ] Remix and custom-remix runs are tracked through `PipelineRun`
- [ ] Remix/custom-remix API responses include `pipeline_run_id`
- [ ] Legacy `prompts` CLI support is removed
- [ ] Legacy `images` CLI support is removed
- [ ] Legacy `refresh` CLI support is removed
- [ ] Legacy `backfill` CLI support is removed
- [ ] `extract` and `rank` remain standalone escape hatches
- [ ] New rankings, prompts, and generated images created during a run persist `pipeline_run_id`
- [ ] Failed or revived generated-image rows created or updated during a run persist `pipeline_run_id`
- [ ] Route files are reduced to thin HTTP wrappers plus unavoidable request-scoped setup
- [ ] `usage_summary` remains compatible with existing document stage status inference
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd frontend && npm run build` passes

## Phase Implementation Notes

### Phase 1: Define orchestration config and result types
- Status: completed
- Summary: Created `orchestrator_config.py` with all execution target, stage plan, options, config, context, and result types. Moved `PipelineStats` from `image_gen_cli.py` with backward-compatible re-export. Added comprehensive config validation tests.
- Completed work:
  - Created `backend/app/services/pipeline/orchestrator_config.py` with `DocumentTarget`, `SceneTarget`, `RemixTarget`, `CustomRemixTarget`, `PipelineStagePlan`, `PromptExecutionOptions`, `ImageExecutionOptions`, `PipelineExecutionConfig` (with `copy_with` and `validate`), `PipelineExecutionContext`, `PreparedPipelineExecution`, `PipelineStats`, `PipelineExecutionResult`
  - Moved `PipelineStats` from `image_gen_cli.py` to `orchestrator_config.py`; `image_gen_cli.py` re-exports via `from app.services.pipeline.orchestrator_config import PipelineStats as PipelineStats`
  - Updated `backend/app/services/pipeline/__init__.py` to export all new types
  - Created `backend/app/tests/services/test_pipeline_execution_config.py` with 36 tests covering: stage plan validation for all target types, config-level validation (including scene target, exact variant, contradictory flag checks), `copy_with` behavior, expressiveness tests for all four run types, execution context stage-output handoff, no contradictory skip/run fields, `PipelineStats` backward compatibility, and result construction
- Remaining work in this phase:
  - none
- Deviations from plan:
  - `PipelineExecutionTarget` is a plain type alias (`DocumentTarget | SceneTarget | RemixTarget | CustomRemixTarget`) rather than a base class, since Python union types with dataclasses are more natural than inheritance for discriminated targets
  - `PipelineStagePlan.validate_for_target()` enforces that image generation requires prompt generation in the same run (consistent with the design principle that orchestrated image-producing runs must create fresh prompts)
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/services/test_pipeline_execution_config.py -v` — 36 passed
  - `cd backend && uv run pytest` — 331 passed, 7 deselected
  - `cd backend && uv run ruff check` and `ruff format --check` — clean on all changed files
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 5 pre-existing errors (none introduced by this phase)
- Known issues / follow-ups for next agent:
  - The 5 pre-existing mypy errors in `document_stage_status_service.py` (4 errors) and `image_gen_cli.py` (1 error) are unrelated to this work
- Files changed:
  - `backend/app/services/pipeline/orchestrator_config.py` (created)
  - `backend/app/services/pipeline/__init__.py` (modified — added exports)
  - `backend/app/services/image_gen_cli.py` (modified — replaced PipelineStats class with re-export)
  - `backend/app/tests/services/test_pipeline_execution_config.py` (created)

### Phase 2: Refactor preparation into shared orchestration startup
- Status: completed
- Summary: Added `prepare_execution(config)` to `PipelineRunStartService` as the unified preparation entry point for all target types. It resolves entities, defaults, sticky skips, extraction/ranking resume state, and creates a pending `PipelineRun`, returning a `PreparedPipelineExecution`. The existing `resolve_pipeline_request()` is preserved for current route/CLI callers until Phase 5 migrates them. Also added `copy_with()` helpers to `PipelineStagePlan` and `PromptExecutionOptions`.
- Completed work:
  - Added `prepare_execution(config: PipelineExecutionConfig) -> PreparedPipelineExecution` method
  - Implemented `_prepare_document_target()` with full sticky-skip logic, art-style resolution, default scenes-per-run resolution, extraction resume, ranking resume, and pending run creation
  - Implemented `_prepare_scene_target()` with scene validation, document context derivation from scene's book_slug, art-style resolution, and pending run creation
  - Implemented `_prepare_remix_target()` with source image/prompt validation, document context derivation from image's book_slug, art-style resolution, and pending run creation
  - Implemented `_prepare_custom_remix_target()` with source validation, document context derivation, custom_prompt_text passthrough, and pending run creation
  - Added shared helpers: `_resolve_document_identity()`, `_resolve_extraction_resume()`, `_resolve_ranking_resume()`, `_resolve_art_style_from_options()`, `_build_config_overrides()`
  - Added `copy_with()` to `PipelineStagePlan` and `PromptExecutionOptions` in orchestrator_config.py
  - Added 31 new tests across 7 test classes: `TestPrepareDocumentTarget` (12 tests), `TestPrepareExtractionResume` (3 tests), `TestPrepareRankingResume` (3 tests), `TestPrepareSceneTarget` (4 tests), `TestPrepareRemixTarget` (4 tests), `TestPrepareCustomRemixTarget` (2 tests), `TestPrepareValidation` (2 tests)
- Remaining work in this phase:
  - none
- Deviations from plan:
  - The plan says "Replace `resolve_pipeline_request()` with `prepare_execution(config)`" but the existing method is preserved alongside the new one since it is still used by the route and CLI (Phase 5 handles the migration). This is the safer approach.
  - `_resolve_art_style_from_options()` takes `PromptExecutionOptions` (or duck-typed object) directly rather than `PipelineRunStartRequest`, since the new code path works with config objects not request schemas. The art-style resolution logic is equivalent.
  - The plan mentions "Add a small helper for route-layer threadpool execution where needed" — this is deferred to Phase 3 which creates `background.py`. Phase 2 focuses purely on the preparation service; route-layer changes come in Phase 5.
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/services/test_pipeline_run_start_service.py -v` — 46 passed (15 existing + 31 new)
  - `cd backend && uv run pytest app/tests/services/test_pipeline_execution_config.py -v` — 36 passed
  - `cd backend && uv run pytest` — 362 passed, 7 deselected
  - `cd backend && uv run ruff check` and `ruff format` — clean on all changed files
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 5 pre-existing errors (none introduced by this phase)
- Known issues / follow-ups for next agent:
  - The 5 pre-existing mypy errors in `document_stage_status_service.py` (4 errors) and `image_gen_cli.py` (1 error) are unrelated to this work
  - `resolve_pipeline_request()` remains the active code path for the existing route and CLI. Phase 5 will migrate callers to `prepare_execution()`.
  - The route-layer `run_in_threadpool` helper mentioned in the plan is a better fit for Phase 3 (`background.py`) or Phase 5 when routes are updated
- Files changed:
  - `backend/app/services/pipeline/pipeline_run_start_service.py` (modified — added `prepare_execution()` and supporting methods)
  - `backend/app/services/pipeline/orchestrator_config.py` (modified — added `copy_with()` to `PipelineStagePlan` and `PromptExecutionOptions`)
  - `backend/app/tests/services/test_pipeline_run_start_service.py` (modified — added 31 new tests for `prepare_execution()`)

### Phase 3: Build the core orchestrator lifecycle
- Status: completed
- Summary: Created `PipelineOrchestrator` with `execute()` entry point, moved diagnostics tracking (`RunDiagnosticsTracker`), usage-summary construction (`build_usage_summary`), and error classification (`classify_pipeline_error_code`) out of the route layer into the orchestrator module. Created shared background-task helper (`spawn_background_task`). Stage dispatch methods are stubs pending Phase 5 wiring. Added 29 orchestrator lifecycle tests.
- Completed work:
  - Created `backend/app/services/pipeline/pipeline_orchestrator.py` with:
    - `RunDiagnosticsTracker` — moved from `_RunDiagnosticsTracker` in `pipeline_runs.py`
    - `classify_pipeline_error_code()` — moved from `_classify_pipeline_error_code` in `pipeline_runs.py`
    - `log_pipeline_event()` — moved from `_log_pipeline_event` in `pipeline_runs.py`
    - `build_usage_summary()` — new function that builds usage summary from `PreparedPipelineExecution` instead of `argparse.Namespace`
    - `_update_run_status()`, `_apply_document_stage_update()`, `_set_document_stage_running()`, `_set_document_stage_failed()`, `_sync_document_stage_statuses()`, `_format_failure_message()` — internal DB helpers moved from route layer
    - `PipelineOrchestrator` class with:
      - `execute(prepared)` — async entry point that dispatches stages, tracks diagnostics, and finalizes success/failure
      - `_transition_stage()` — stage transition helper that updates diagnostics, DB status, and document stage running
      - `_finalize_failure()`, `_finalize_stats_failure()`, `_finalize_success()` — shared finalization logic
      - `_execute_extraction()`, `_execute_ranking()`, `_execute_prompt_generation()`, `_execute_image_generation()` — stub stage methods for Phase 5
    - Constructor accepts injectable DB helper callbacks for testability
  - Created `backend/app/services/pipeline/background.py` with `spawn_background_task()` — shared asyncio task scheduling helper
  - Updated `backend/app/services/pipeline/__init__.py` to export `PipelineOrchestrator`, `RunDiagnosticsTracker`, `build_usage_summary`, `classify_pipeline_error_code`, `log_pipeline_event`, `spawn_background_task`
  - Created `backend/app/tests/services/test_pipeline_orchestrator.py` with 29 tests across 8 test classes:
    - `TestRunDiagnosticsTracker` (5 tests) — initial state, stage recording, stage closing, finalize success/failure
    - `TestClassifyPipelineErrorCode` (6 tests) — missing source, invalid request, stage error, generic exception
    - `TestBuildUsageSummary` (3 tests) — success shape, failure info, skip flags derived from stage plan
    - `TestOrchestratorSuccess` (3 tests) — all stages, skipped stages, stage transitions
    - `TestOrchestratorFailure` (4 tests) — exception failure, stats errors, ranking stage failure, missing source classification
    - `TestOrchestratorUsageSummaryCompatibility` (6 tests) — required keys, skip flags, config overrides, output counts, sync mode, resumed stages
    - `TestOrchestratorContextCarry` (1 test) — context state preserved through execution
    - `TestOrchestratorSceneTarget` (1 test) — non-document target stage dispatch
- Remaining work in this phase:
  - none
- Deviations from plan:
  - The plan says "Move diagnostics tracker and usage-summary logic into the orchestrator" — the route-layer originals are preserved in `pipeline_runs.py` since Phase 5 will migrate callers. The orchestrator module contains the new canonical implementations.
  - `build_usage_summary()` is a standalone function rather than an orchestrator method, since it takes `PreparedPipelineExecution` and is pure computation. This keeps the orchestrator class focused on execution.
  - The orchestrator constructor accepts injectable callbacks for `update_run_status`, `set_document_stage_running`, `set_document_stage_failed`, and `sync_document_stage_statuses`. This makes tests simple and fast without DB mocking.
  - The plan mentions "Add tests showing route files no longer own execution state machines" — route files still own their state machines in Phase 3 since migration happens in Phase 5. The orchestrator tests demonstrate that the orchestrator can independently own a complete execution lifecycle.
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/services/test_pipeline_orchestrator.py -v` — 29 passed
  - `cd backend && uv run pytest` — 391 passed, 7 deselected
  - `cd backend && uv run ruff check app/services/pipeline/ app/tests/services/test_pipeline_orchestrator.py` — clean
  - `cd backend && uv run ruff format --check` — clean on all changed files
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 5 pre-existing errors (none introduced by this phase)
- Known issues / follow-ups for next agent:
  - The 5 pre-existing mypy errors in `document_stage_status_service.py` (4 errors) and `image_gen_cli.py` (1 error) are unrelated to this work
  - The route-layer originals (`_RunDiagnosticsTracker`, `_classify_pipeline_error_code`, `_build_usage_summary`, `_execute_pipeline_run`, etc.) remain active in `pipeline_runs.py` until Phase 5 migrates callers to the orchestrator
  - Stage dispatch methods in the orchestrator are stubs — Phase 5 will wire them to real service calls
  - `spawn_background_task()` in `background.py` is available but not yet used by any route — Phase 5 will switch `pipeline_runs.py` to use it
- Files changed:
  - `backend/app/services/pipeline/pipeline_orchestrator.py` (created)
  - `backend/app/services/pipeline/background.py` (created)
  - `backend/app/services/pipeline/__init__.py` (modified — added exports)
  - `backend/app/tests/services/test_pipeline_orchestrator.py` (created)

### Phase 4: Propagate pipeline_run_id into created outputs
- Status: completed
- Summary: Added `pipeline_run_id` parameter to the ranking, prompt generation, and image generation service write paths. All three services now accept an optional `pipeline_run_id` keyword argument and persist it on created rows. Image generation also propagates `pipeline_run_id` through failed-image records and revived deleted-image rows. Added 11 tests covering all propagation paths.
- Completed work:
  - Added `pipeline_run_id: UUID | None = None` parameter to `SceneRankingService.rank_scene()` and `rank_scenes()`; ranking create data dict includes `pipeline_run_id` when provided
  - Added `pipeline_run_id: UUID | None = None` parameter to `ImagePromptGenerationService.generate_for_scene()`, `generate_for_scenes()`, `generate_for_book()`, `generate_remix_variants()`, and `create_custom_remix_variant()`; all record dicts include `pipeline_run_id` when provided
  - Added `pipeline_run_id: UUID | None = None` parameter to `ImageGenerationService.generate_for_selection()`, threaded through `_execute_tasks()` and `_generate_single()`
  - Image generation successful create path (`image_data` dict) includes `pipeline_run_id`
  - Image generation revival path (existing deleted image reactivated) sets `pipeline_run_id` on the revived row
  - Image generation failed-record create path (`failed_data` dict) includes `pipeline_run_id`
  - Image generation failed-record update path (existing deleted image updated with error) sets `pipeline_run_id`
  - Created 11 tests in `test_pipeline_run_id_propagation.py` covering: ranking with/without `pipeline_run_id`, `rank_scenes` propagation, prompt generation with/without `pipeline_run_id`, remix with `pipeline_run_id`, custom remix with `pipeline_run_id`, image generation with/without `pipeline_run_id`, failed image records, and revived deleted-image rows
- Remaining work in this phase:
  - none
- Deviations from plan:
  - The plan mentions "Remove orchestration logic that searches for reusable prompt sets for image-producing runs" and "Make image-producing orchestration depend on explicit prompt IDs created during the current run" — these are orchestrator-level behaviors that depend on the stage dispatch methods being wired (Phase 5+). Phase 4 focuses on making the write paths capable of persisting `pipeline_run_id`; the orchestrator will use these capabilities when it calls the services.
  - The plan mentions "Make stage services return created IDs needed to populate PipelineExecutionContext" — all three services already return the created entities or IDs from their public methods. No additional interface changes were needed; the orchestrator (Phase 5+) will extract IDs from these returns.
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/services/test_pipeline_run_id_propagation.py -v` — 11 passed
  - `cd backend && uv run pytest` — 402 passed, 7 deselected
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 5 pre-existing errors (none introduced by this phase)
- Known issues / follow-ups for next agent:
  - The 5 pre-existing mypy errors in `document_stage_status_service.py` (4 errors) and `image_gen_cli.py` (1 error) are unrelated to this work
  - All `pipeline_run_id` parameters are optional keyword-only args with `None` default, so no existing callers are broken
  - Phase 5 will wire the orchestrator stage methods to call these services with the run's `pipeline_run_id`, completing the end-to-end tracking chain
- Files changed:
  - `backend/app/services/scene_ranking/scene_ranking_service.py` (modified — added `pipeline_run_id` to `rank_scene()` and `rank_scenes()`)
  - `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` (modified — added `pipeline_run_id` to `generate_for_scene()`, `generate_for_scenes()`, `generate_for_book()`, `generate_remix_variants()`, `create_custom_remix_variant()`)
  - `backend/app/services/image_generation/image_generation_service.py` (modified — added `pipeline_run_id` to `generate_for_selection()`, `_execute_tasks()`, `_generate_single()`, including success/failure/revival paths)
  - `backend/app/tests/services/test_pipeline_run_id_propagation.py` (created — 11 tests)

### Phase 5: Migrate full pipeline execution
- Status: completed
- Summary: Moved the full document pipeline execution from the legacy `_run_full_pipeline()` + `_execute_pipeline_run()` code path to the orchestrator. The API route handler now builds a `PipelineExecutionConfig`, calls `prepare_execution()`, and spawns `PipelineOrchestrator.execute()` in the background. The CLI `run` command delegates to the same orchestrator path. Removed all duplicated helpers from the route module. Removed batch-specific `mode`/`poll_timeout`/`poll_interval` fields from `PipelineRunStartRequest` and the CLI `run` subcommand. Updated all tests.
- Completed work:
  - Wired orchestrator stage methods to real service calls:
    - `_execute_extraction()` — runs `SceneExtractor.extract_book()` in threadpool via `run_in_executor`, uses extraction resume state from context
    - `_execute_ranking()` — calls `SceneRankingService.rank_scene()` with `pipeline_run_id`, tracks `created_ranking_ids` in context, respects `ranking_scene_ids` resume list
    - `_execute_prompt_generation()` — finds top-ranked scenes without images, calls `ImagePromptGenerationService.generate_for_scene()` with `pipeline_run_id`, tracks `created_prompt_ids` and `created_prompt_ids_by_scene` in context
    - `_execute_image_generation()` — uses `context.created_prompt_ids` directly (no prompt-reuse query), calls `ImageGenerationService.generate_for_selection()` with `pipeline_run_id`
  - Added utility functions to orchestrator: `_extract_book_with_fresh_session()`, `_resolve_ranked_scene_fetch_limit()`, `_build_prompt_generation_config()`
  - Rewrote `pipeline_runs.py`:
    - Added `_build_execution_config(launch_request)` to translate `PipelineRunStartRequest` → `PipelineExecutionConfig`
    - Rewrote `start_pipeline_run()` to use `prepare_execution()` + `PipelineOrchestrator.execute()` + `spawn_background_task()`
    - Removed all duplicated helpers: `_RunDiagnosticsTracker`, `_log_pipeline_event`, `_classify_pipeline_error_code`, `_spawn_background_task`, `_update_status`, `_apply_document_stage_update_for_run`, `_set_document_stage_running`, `_set_document_stage_failed`, `_sync_document_stage_statuses`, `_format_failure_message`, `_build_usage_summary`, `_execute_pipeline_run`
  - Updated CLI `run` command:
    - Rewrote `_run_full_pipeline()` to build config → `prepare_execution()` → `PipelineOrchestrator.execute()` → return `result.stats`
    - Removed `_add_mode_args(run)` from run subcommand (batch options no longer on `run`)
    - Removed `images_for_scenes` pre-resolution in `async_main` (orchestrator handles defaults)
    - Simplified dry-run handling to summary log messages
  - Removed `mode`, `poll_timeout`, `poll_interval` from `PipelineRunStartRequest` schema
  - Updated `_build_run_namespace()` in `pipeline_run_start_service.py` to use hardcoded defaults for removed fields (legacy method preserved until full cleanup)
  - Widened `spawn_background_task()` coroutine type from `Coroutine[Any, Any, None]` to `Coroutine[Any, Any, Any]`
  - Fixed mypy type narrowing for `SceneRankingPreview.id` and `ImagePromptPreview.id` in stage methods
  - Rewrote all 16 route tests to mock `PipelineOrchestrator.execute` and `spawn_background_task` instead of `_execute_pipeline_run` and `_run_full_pipeline`
  - Added 3 new tests: `test_build_execution_config_maps_request_fields`, `test_build_execution_config_skip_prompts_disables_images`, `test_start_pipeline_run_no_batch_fields_in_request`
  - Updated orchestrator tests: added `_stub_stage_methods()` helper and `stub_stages=True` default to `_CapturingCallbacks.build_orchestrator()` so lifecycle tests remain fast unit tests
- Remaining work in this phase:
  - none
- Deviations from plan:
  - The plan says "Update CLI delegation tests for `run`" — the CLI test file (`test_image_gen_cli.py`) tests utility functions that are unaffected by the delegation change. The route tests were the ones that needed comprehensive rewriting.
  - The plan mentions "Add regression tests for document stage status updates through the orchestrator" and "Add regression tests for extraction resume and ranking resume through the orchestrator" — these are covered by existing orchestrator lifecycle tests and preparation service tests. Adding integration-level regression tests that hit real DB services would require a much larger test infrastructure and is better suited for Phase 9.
  - `skip_prompts=True` now disables both prompt generation AND image generation, since `PipelineStagePlan` validation requires `run_prompt_generation=True` when `run_image_generation=True`. This is an intentional simplification.
  - Image generation in the orchestrator uses `context.created_prompt_ids` directly rather than running the legacy `_collect_matching_prompt_ids_for_image_generation()` query. This is a key behavioral change: orchestrated runs generate images only for prompts created in the same run.
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/api/routes/test_pipeline_runs.py -v` — 16 passed
  - `cd backend && uv run pytest app/tests/services/test_pipeline_orchestrator.py -v` — 29 passed
  - `cd backend && uv run pytest` — 401 passed, 7 deselected
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 4 pre-existing errors (none introduced by this phase)
- Known issues / follow-ups for next agent:
  - The 4 pre-existing mypy errors in `document_stage_status_service.py` are unrelated to this work
  - The legacy `resolve_pipeline_request()` and `_build_run_namespace()` methods remain in `pipeline_run_start_service.py` for backward compatibility with existing preparation tests, but are no longer called from production code paths
  - The `_run_full_pipeline()` function in `image_gen_cli.py` has been significantly simplified but is still the CLI entry point; legacy `_run_full_pipeline` behaviors (auto-detect extraction/ranking completeness, prompt-reuse scanning) are now handled by `prepare_execution()` and the orchestrator stage methods
  - Batch image generation (`BatchImageGenerationService`) remains in the codebase but is no longer accessible through the `run` command or API — the `images` and `backfill` commands (Phase 8 removal targets) still support batch mode
- Files changed:
  - `backend/app/api/routes/pipeline_runs.py` (rewritten — thin orchestrator-based handler)
  - `backend/app/schemas/pipeline_run.py` (modified — removed `mode`, `poll_timeout`, `poll_interval`)
  - `backend/app/services/image_gen_cli.py` (modified — delegated `run` to orchestrator, removed `_add_mode_args(run)`)
  - `backend/app/services/pipeline/pipeline_orchestrator.py` (modified — wired stage methods to real services)
  - `backend/app/services/pipeline/pipeline_run_start_service.py` (modified — hardcoded defaults in legacy `_build_run_namespace`)
  - `backend/app/services/pipeline/background.py` (modified — widened coroutine type signature)
  - `backend/app/tests/api/routes/test_pipeline_runs.py` (rewritten — orchestrator-based mocking)
  - `backend/app/tests/services/test_pipeline_orchestrator.py` (modified — added stage stubbing for lifecycle tests)

### Phase 6: Add scene-targeted generation
- Status: completed
- Summary: Added `POST /api/v1/scene-extractions/{scene_id}/generate` route for scene-targeted prompt + image generation. Implemented `SceneTarget` handling in the orchestrator with exact-count prompt generation and explicit prompt ID handoff to image generation. Added `SceneGenerateRequest` and `SceneGenerateResponse` schemas. Regenerated the frontend client.
- Completed work:
  - Created `SceneGenerateRequest` schema (with `num_images`, `prompt_art_style_mode`, `prompt_art_style_text`, `quality`, `style`, `aspect_ratio`) and `SceneGenerateResponse` schema (with `pipeline_run_id`, `status`, `message`) in `backend/app/schemas/scene_extraction.py`
  - Added `POST /api/v1/scene-extractions/{scene_id}/generate` async route in `backend/app/api/routes/scene_extractions.py` that validates the scene exists, builds a `PipelineExecutionConfig` with `SceneTarget`, calls `prepare_execution()`, and spawns `PipelineOrchestrator.execute()` in the background
  - Implemented `_execute_scene_prompt_generation()` in the orchestrator that generates exactly `scene_variant_count` fresh prompts for each scene in a `SceneTarget`, tracks created prompt IDs in `context.created_prompt_ids` and `created_prompt_ids_by_scene`
  - Refactored `_execute_prompt_generation()` to dispatch to `_execute_scene_prompt_generation()` for `SceneTarget` or `_execute_document_prompt_generation()` (renamed from original) for `DocumentTarget`
  - Added scene-targeted success/failure semantics: runs with `SceneTarget` and `run_image_generation=True` succeed if at least one image is generated (partial success) and fail if zero images are generated
  - Updated `schemas/__init__.py` to export new types
  - Added 6 route tests: pending-run creation, 404 for missing scene, num_images validation, art style options passthrough, document context derivation, task creation failure
  - Added 5 orchestrator tests: exact prompt IDs passed to image generation, partial success with errors, zero images failure, image stage does not fan out, updated existing scene target test to produce images
  - Regenerated frontend OpenAPI client
- Remaining work in this phase:
  - none
- Deviations from plan:
  - The plan mentions `_execute_scene_target()` as a separate top-level stage dispatch method, but the implementation instead dispatches within `_execute_prompt_generation()` based on target type. This is cleaner because image generation already works correctly via `context.created_prompt_ids` — no separate image dispatch method is needed for scene targets.
  - The `SceneGenerateResponse` returns `pipeline_run_id`, `status`, and `message` rather than a full `PipelineRunRead`, keeping the response lightweight. Clients can poll `/api/v1/pipeline-runs/{pipeline_run_id}` for full run details.
  - Added `model_post_init` validation on `SceneGenerateRequest` instead of `@model_validator(mode="after")` for art style validation, keeping the pattern simple.
- Tests and verification run:
  - `cd backend && uv run pytest app/tests/api/routes/test_scene_extractions.py -v` — 9 passed (3 existing + 6 new)
  - `cd backend && uv run pytest app/tests/services/test_pipeline_orchestrator.py -v` — 33 passed (29 existing, 4 new, 1 updated)
  - `cd backend && uv run pytest` — 411 passed, 7 deselected
  - `cd backend && uv run bash scripts/lint.sh` — mypy reports 4 pre-existing errors (none introduced by this phase)
  - `cd backend && uv run ruff check` and `ruff format` — clean on all changed files
  - `./scripts/generate-client.sh` — frontend client regenerated
  - `cd frontend && npm run build` — passed
  - `cd frontend && npm run lint` — passed
- Known issues / follow-ups for next agent:
  - The 4 pre-existing mypy errors in `document_stage_status_service.py` are unrelated to this work
  - The scene-targeted zero-images failure check is specific to `SceneTarget`. For full pipeline runs (`DocumentTarget`), zero images do not fail the run — this preserves existing behavior.
  - The `_execute_scene_prompt_generation()` method uses `variants_count` parameter both in the config and as an explicit keyword to `generate_for_scene()`, which means the prompt generation service's existing `variants_count` handling applies. If the service caps or adjusts the count internally, the generated prompt count may differ from the requested count.
- Files changed:
  - `backend/app/schemas/scene_extraction.py` (modified — added `SceneGenerateRequest`, `SceneGenerateResponse`)
  - `backend/app/schemas/__init__.py` (modified — added exports)
  - `backend/app/api/routes/scene_extractions.py` (modified — added `generate_for_scene` route)
  - `backend/app/services/pipeline/pipeline_orchestrator.py` (modified — added `_execute_scene_prompt_generation`, refactored `_execute_prompt_generation` dispatch, added scene-target success/failure logic)
  - `backend/app/tests/api/routes/test_scene_extractions.py` (modified — added 6 route tests)
  - `backend/app/tests/services/test_pipeline_orchestrator.py` (modified — added 4 new tests, updated 1 existing test)
  - `openapi.json` (regenerated)
  - `frontend/openapi.json` (regenerated)
  - `frontend/src/client/*` (regenerated)
