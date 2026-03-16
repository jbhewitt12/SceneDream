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
