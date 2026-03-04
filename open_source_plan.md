# Open Source Readiness Plan

## Goal
This project is being prepared for open-source release so it can be used and extended by a broader community. The plan below is a high-level implementation roadmap to make SceneDream public-ready, easier to run, and easier to contribute to.

## Data Preservation Requirement
- There is existing data in the database today, and this data must be preserved throughout the open-source transition.
- Schema and data-model changes must be implemented with non-destructive migrations and backfills; do not delete or truncate existing operational data.
- Every step that changes persistence shape must include data migration verification (before/after checks) to confirm legacy records remain usable.

## Guiding Principles
- Keep core pipeline behavior stable while expanding input and workflow flexibility.
- Make project setup predictable for new contributors.
- Prefer clear defaults with optional per-run overrides.
- Build observability and operational safeguards into first-class features.

## Execution Tracking

Use this section for short agent updates per step.

### Agent Update Template

Copy this block for each step update:

```md
#### Step N - <title>
- Done: no
- Date: YYYY-MM-DD
- What was implemented: <short summary>
- Important implementation details: <key technical choices/files changed>
- Differences from plan: <none or short note>
```

### Step Updates

#### Step 1 - Core Domain Model Consolidation
- Done: yes
- Date: 2026-03-03
- What was implemented: Added canonical `Document`, `PipelineRun`, and `GeneratedAsset` domain models with backward-compatible links to existing scene/ranking/prompt/image records.
- Important implementation details: Added new SQLModel entities and relationships (`backend/models/document.py`, `backend/models/pipeline_run.py`, `backend/models/generated_asset.py`); added optional linkage fields to existing models (`document_id`, `pipeline_run_id`, `generated_asset_id`); added Alembic migration `c3f4b6d8a921` to create new tables, add linkage columns/indexes/FKs, and backfill `documents` from existing `scene_extractions.book_slug`; added repositories and schemas for the three canonical entities (`backend/app/repositories/{document,pipeline_run,generated_asset}.py`, `backend/app/schemas/{document,pipeline_run,generated_asset}.py`); added frontend domain type scaffolding in `frontend/src/types/domain.ts`; added repository/backfill behavior tests in `backend/app/tests/repositories/test_core_domain_repositories.py`; and extended test cleanup in `backend/app/tests/conftest.py` for new table data.
- Differences from plan: Follow-up test stabilization was required for async test backend selection (`anyio_backend="asyncio"`) in batch polling/scheduler tests; after this adjustment, full backend test suite passed.

#### Step 2 - Document Ingestion Abstraction
- Done: yes
- Date: 2026-03-03
- What was implemented: Extended the format-agnostic ingestion layer to support `.txt`, `.md`, and `.docx` inputs in addition to existing EPUB/MOBI support, with normalized chapter/paragraph output compatible with the existing scene extraction pipeline.
- Important implementation details: Added new loaders for plain text, markdown, and DOCX (`backend/app/services/books/{text_loader,markdown_loader,docx_loader}.py`), plus shared plain-text normalization/chapter-splitting utilities (`backend/app/services/books/plain_text_utils.py`); wired extension-based dispatch into `BookContentService` for `.txt`, `.md`, and `.docx` while preserving cache behavior and service-level errors (`backend/app/services/books/book_content_service.py`); expanded ingestion metadata to consistently capture warnings, parse errors, and source metadata across formats (`backend/app/services/books/base.py`); updated CLI/help text to reflect new accepted source formats (`backend/app/services/scene_extraction/scene_extraction.py`, `backend/app/services/scene_extraction/chunk_debug_cli.py`, `backend/app/services/image_gen_cli.py`); added unit tests for each new loader using real files from `example_docs/` and extended service routing tests (`backend/app/tests/services/books/test_{text_loader,markdown_loader,docx_loader}.py`, `backend/app/tests/services/books/test_book_content_service.py`).
- Differences from plan: Added `python-docx` dependency (`backend/pyproject.toml`, `backend/uv.lock`) to improve DOCX parsing robustness per implementation request.

#### Step 3 - Content Directory Generalization (`books` to `documents`)
- Done: yes
- Date: 2026-03-03
- What was implemented: Switched content path behavior to treat `documents/` as the canonical directory while preserving full backward compatibility for legacy `books/` paths, and added a non-destructive path backfill migration for persisted records.
- Important implementation details: Extended `BookContentService` path resolution and normalization (`backend/app/services/books/book_content_service.py`) with `documents/` canonicalization plus `books/` fallback; updated scene extraction path defaults and persistence normalization (`backend/app/services/scene_extraction/scene_extraction.py`) so new `source_book_path` values are stored as project-relative `documents/...` paths; updated pipeline/default CLI examples to use `documents/...` (`backend/app/services/image_gen_cli.py`, `scripts/mobi_preview.py`); added Alembic migration `f0c9f8a2b321` to normalize `documents.source_path` and `scene_extractions.source_book_path` to `documents/...`, strip absolute prefixes, and preserve original values in JSON metadata (`backend/app/alembic/versions/f0c9f8a2b321_generalize_content_paths_to_documents.py`); updated compatibility/default-path tests and fixtures (`backend/app/tests/services/books/test_book_content_service.py`, `backend/app/tests/services/books/test_{epub,mobi,backward_compatibility}.py`, `backend/app/tests/services/test_image_prompt_generation_service.py`, `backend/app/tests/conftest.py`, `backend/app/tests/repositories/test_image_prompt_repository.py`, `backend/app/tests/api/routes/test_generated_images.py`); and added explicit backfill verification coverage for path normalization/legacy metadata (`backend/app/tests/repositories/test_core_domain_repositories.py`).
- Differences from plan: Filesystem directories were not renamed on disk in this step; runtime now defaults to `documents/` and transparently falls back to `books/` so existing installs continue to work during transition.

#### Step 4 - Settings System and User Defaults
- Done: yes
- Date: 2026-03-03
- What was implemented: Added persistent settings and art-style catalog support with seeded defaults, async settings APIs, and a new frontend settings page for managing global defaults.
- Important implementation details: Added new SQLModel entities for `ArtStyle` and singleton `AppSettings` (`backend/models/art_style.py`, `backend/models/app_settings.py`) with repository + schema layers (`backend/app/repositories/art_style.py`, `backend/app/repositories/app_settings.py`, `backend/app/schemas/art_style.py`, `backend/app/schemas/app_settings.py`); added Alembic migration `b7a3c1d9e5f2` to create `art_styles`/`app_settings`, seed style catalog entries, seed global defaults (`default_scenes_per_run=5`), and run seed verification checks; added async settings routes (`GET/PATCH /api/v1/settings`, `GET /api/v1/settings/art-styles`) in `backend/app/api/routes/settings.py` and registered router wiring; updated prompt-style sampling to read DB-backed styles with fallback behavior and default-style prioritization via `StyleSampler(preferred_style=...)` (`backend/app/services/image_prompt_generation/image_prompt_generation_service.py`, `backend/app/services/image_prompt_generation/core/style_sampler.py`); updated pipeline CLI `run` defaults to read scenes-per-run from persisted app settings when `--images-for-scenes` is omitted (`backend/app/services/image_gen_cli.py`); and added backend test coverage for new repositories, routes, and style-sampling behavior (`backend/app/tests/repositories/test_settings_repositories.py`, `backend/app/tests/api/routes/test_settings.py`, `backend/app/tests/services/test_image_prompt_generation_service.py`).
- Differences from plan: Added `GET /api/v1/settings/art-styles` as a convenience endpoint and connected defaults to existing runtime behavior immediately (style sampling priority + CLI default resolution) so settings changes have direct operational impact before pipeline orchestration endpoints are introduced.

#### Step 5 - Pipeline Orchestration and Job Model
- Done: yes
- Date: 2026-03-03
- What was implemented: Added async pipeline-run orchestration endpoints that create/poll `PipelineRun` records and execute the existing end-to-end pipeline in a background task with persisted stage/status transitions.
- Important implementation details: Added `POST /api/v1/pipeline-runs` and `GET /api/v1/pipeline-runs/{run_id}` (`backend/app/api/routes/pipeline_runs.py`) and wired the router (`backend/app/api/main.py`, `backend/app/api/routes/__init__.py`); added launch request schema with runtime override fields (`backend/app/schemas/pipeline_run.py`, `backend/app/schemas/__init__.py`); implemented background task spawning/error handling consistent with existing async route patterns; resolved launch context from `document_id` or `book_slug` with optional `book_path` fallback to canonical `documents.source_path`; persisted effective overrides in `pipeline_runs.config_overrides`; updated CLI orchestration to support optional stage callbacks and API-driven defaults by extending `_run_full_pipeline(..., stage_callback=...)` and adding `_emit_stage_update` hooks for `extracting`, `ranking`, `generating_prompts`, and `generating_images` (`backend/app/services/image_gen_cli.py`); and added route tests for scheduling, error handling, document default resolution, validation, and polling (`backend/app/tests/api/routes/test_pipeline_runs.py`).
- Differences from plan: Kept a lightweight two-endpoint surface (`start` + `poll`) as planned, and explicitly marked `current_stage` as `failed`/`completed` terminal states to simplify polling semantics for the initial release.

#### Step 6 - Document Dashboard and Status Tracking
- Done: yes
- Date: 2026-03-04
- What was implemented: Added a document-centric dashboard API and frontend page that lists source files, computes per-stage pipeline status/counts, and surfaces latest run outcomes (including failure details) per document.
- Important implementation details: Added dashboard schemas (`DocumentDashboard*`) and response wiring (`backend/app/schemas/document.py`, `backend/app/schemas/__init__.py`); implemented merged filesystem+database aggregation with legacy slug fallback and stage-count rollups across `scene_extractions`, `scene_rankings`, `image_prompts`, and `generated_images` plus latest-run resolution from `pipeline_runs` (`backend/app/services/document_dashboard_service.py`); added async non-blocking route `GET /api/v1/documents/dashboard` using threadpool execution and router registration (`backend/app/api/routes/documents.py`, `backend/app/api/main.py`, `backend/app/api/routes/__init__.py`); added backend coverage for service + route behavior (`backend/app/tests/services/test_document_dashboard_service.py`, `backend/app/tests/api/routes/test_documents.py`); added frontend dashboard client + route and navigation entry (`frontend/src/api/documents.ts`, `frontend/src/routes/_layout/documents.tsx`, `frontend/src/components/Common/Navbar.tsx`, `frontend/src/routes/_layout/index.tsx`, `frontend/src/routeTree.gen.ts`); verified via `cd backend && uv run pytest` (full suite pass), `cd frontend && npm run lint`, and manual browser validation with agent-browser on `http://localhost:5173/documents` (dashboard render, search filter, and cross-route navigation).
- Differences from plan: The API includes canonical `documents/` filesystem scan plus persisted document rows so previously ingested records still appear even when source files are currently missing on disk (`file_exists=false`), improving operational visibility during migration/open-source transition.

#### Step 7 - One-Click Pipeline Launch with Runtime Overrides
- Done: yes
- Date: 2026-03-04
- What was implemented: Added one-click pipeline launch controls to the Documents dashboard with per-run scenes override and optional prompt art-style override, plus live polling of run status until completion/failure.
- Important implementation details: Added frontend pipeline-runs client methods for start/poll (`frontend/src/api/pipelineRuns.ts`) and integrated launch UI/state in the dashboard (`frontend/src/routes/_layout/documents.tsx`) including per-document scenes input, art-style selector sourced from settings, launch button, and active-run status polling via `GET /api/v1/pipeline-runs/{id}`; extended launch request schema with optional `art_style_id` (`backend/app/schemas/pipeline_run.py`); updated launch route preflight to resolve/validate active art styles, persist resolved prompt-style overrides, and support resume when source files are missing but extraction data already exists (`backend/app/api/routes/pipeline_runs.py`); threaded runtime prompt art-style override through orchestration (`prompt_art_style`) and prompt-generation config (`preferred_style`) so per-run overrides take precedence over global defaults (`backend/app/services/image_gen_cli.py`, `backend/app/services/image_prompt_generation/models.py`, `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`); and added backend tests covering style-override validation, missing-source resume/fail-fast behavior, and runtime style precedence (`backend/app/tests/api/routes/test_pipeline_runs.py`, `backend/app/tests/services/test_image_prompt_generation_service.py`).
- Differences from plan: Resume handling was explicitly hardened at API launch preflight (auto-skip extraction only when prior extracted scenes exist; otherwise fail early with a clear error) to prevent background runs from failing later due to missing source files.

#### Step 8 - Cost and Safety Guardrails
- Done: yes
- Date: 2026-03-04
- What was implemented: Added persisted per-run usage summaries so each pipeline run records key runtime inputs, output counts, timing, and error details for clear cost/operation visibility.
- Important implementation details: Added `pipeline_runs.usage_summary` JSONB field with non-destructive migration + verification checks (`backend/models/pipeline_run.py`, `backend/app/alembic/versions/a9b8e7c4d112_add_pipeline_run_usage_summary.py`); updated pipeline run schemas and repository status updates to carry usage payloads (`backend/app/schemas/pipeline_run.py`, `backend/app/repositories/pipeline_run.py`); added usage summary construction/persistence in pipeline execution terminal states (success + failure) and passed resolved config overrides through background execution (`backend/app/api/routes/pipeline_runs.py`); surfaced usage summary on document dashboard latest-run payloads (`backend/app/schemas/document.py`, `backend/app/services/document_dashboard_service.py`); updated frontend API types and dashboard UI to display last-run usage metrics (`frontend/src/api/{pipelineRuns,documents}.ts`, `frontend/src/routes/_layout/documents.tsx`); and added backend coverage for usage summary API/service behavior (`backend/app/tests/api/routes/test_pipeline_runs.py`, `backend/app/tests/api/routes/test_documents.py`, `backend/app/tests/services/test_document_dashboard_service.py`).
- Differences from plan: none

#### Step 9 - Observability and Diagnostics
- Done: yes
- Date: 2026-03-04
- What was implemented: Added pipeline-run diagnostics instrumentation that records structured stage events, per-stage durations, and normalized failure codes/messages in persisted run summaries, with structured run/stage logs for easier production triage.
- Important implementation details: Extended pipeline background execution diagnostics in `backend/app/api/routes/pipeline_runs.py` by adding `_RunDiagnosticsTracker` to capture `usage_summary.diagnostics.stage_events`, `usage_summary.diagnostics.stage_durations_ms`, and `usage_summary.diagnostics.error` (code/message/stage) for terminal failed runs; added `_classify_pipeline_error_code(...)` to normalize failure categories (`missing_source`, `invalid_request`, `stage_error`, `pipeline_exception`); extended `usage_summary.errors` to include `code` while preserving existing shape (`count`/`messages`); added `_log_pipeline_event(...)` JSON-structured log emissions for `run_started`, `stage_started`, `stage_completed`, `run_completed`, and `run_failed`; and added/updated route tests in `backend/app/tests/api/routes/test_pipeline_runs.py` to validate persisted diagnostics fields, stage timing capture, and failure-code classification. Verified with `cd backend && uv run pytest` (143 passed, 7 deselected).
- Differences from plan: No schema migration was required because diagnostics and error codes were added to the existing non-destructive `pipeline_runs.usage_summary` JSONB payload.

#### Step 10 - Contributor and Community Standards
- Done: yes
- Date: 2026-03-04
- What was implemented: Added core open-source governance documentation and contribution templates for contributors, maintainers, and security reporting workflows.
- Important implementation details: Added contributor workflow guide (`CONTRIBUTING.md`) with setup, test/lint, and PR expectations; added Contributor Covenant code of conduct with project maintainer enforcement contact (`CODE_OF_CONDUCT.md`); replaced template-era security policy with SceneDream-specific private disclosure/reporting process (`SECURITY.md`); replaced legacy issue intake with structured bug + feature templates and updated issue contact links to this repository (`.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`); removed obsolete privileged template tied to upstream FastAPI template workflow (`.github/ISSUE_TEMPLATE/privileged.yml`); added a pull request template with required validation checklist (`.github/pull_request_template.md`); and simplified/retargeted discussion question intake copy for SceneDream contributors (`.github/DISCUSSION_TEMPLATE/questions.yml`).
- Differences from plan: Expanded scope slightly to update the discussion template and remove an obsolete upstream-only issue template so all contributor-facing entry points align with the new standards.

#### Step 11 - Public Developer Experience
- Done: yes
- Date: 2026-03-04
- What was implemented: Expanded developer onboarding documentation with a full quickstart path, architecture/workflow context, and a clear environment template for local setup.
- Important implementation details: Rewrote root README onboarding (`README.md`) to include Docker-first quickstart, direct local backend/frontend startup, first workflow steps, and updated `documents/` terminology; added root `.env.example` with required core/database/compose variables plus optional provider/integration settings grouped by feature; aligned backend/frontend docs with the new setup flow and command expectations (`backend/README.md`, `frontend/README.md`); and validated referenced startup paths/commands via `docker compose config` and file existence checks for key scripts/entrypoints.
- Differences from plan: Expanded scope slightly to include explicit backend/frontend README alignment so command references remain consistent across all onboarding entry points.

#### Step 12 - CI Quality Gates for Public Contributions
- Done: yes
- Date: 2026-03-04
- What was implemented: Added lightweight CI quality gates for public contributions by path-scoping backend checks, adding a frontend lint/build workflow, and documenting the baseline required checks for merge protection.
- Important implementation details: Updated backend lint/test workflows to run on broader PR lifecycle events while skipping draft PRs and using path filters/concurrency cancellation to reduce unnecessary runs (`.github/workflows/lint-backend.yml`, `.github/workflows/test-backend.yml`); added new frontend CI workflow that installs dependencies via `npm ci` and runs non-mutating lint plus build checks (`.github/workflows/frontend-ci.yml`); added a dedicated non-mutating frontend lint command for CI (`frontend/package.json` script `lint:ci`); and documented the lightweight baseline check policy and check names in contributor docs (`CONTRIBUTING.md`).
- Differences from plan: Intentionally kept gates minimal and non-restrictive by using path-scoped triggers and draft-PR skipping rather than adding additional heavy/full-repo checks.

#### Step 13 - Open-Source License Finalization
- Done: yes
- Date: 2026-03-04
- What was implemented: Finalized MIT license readiness by normalizing repository license text and adding explicit MIT references in root docs and project metadata.
- Important implementation details: Updated repository `LICENSE` to MIT with project-specific copyright attribution (`LICENSE`); added a dedicated README license section linking to the license file (`README.md`); added Python package metadata for MIT (`backend/pyproject.toml` `project.license` plus MIT classifier); and added frontend package license metadata (`frontend/package.json` `license: "MIT"`).
- Differences from plan: none

#### Step 14 - Existing Data Migration and Backfill Verification
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

## Feature Roadmap (Ordered)

### 1) Core Domain Model Consolidation
Define and standardize core entities across backend and UI:
- `Document`: canonical record for each source file (path, type, metadata, ingestion state).
- `PipelineRun`: one execution instance for a document (status enum tracks current stage; see item 5).
- `GeneratedAsset`: generated prompts/images and storage metadata.

This creates a stable foundation for all upcoming UI, API, and process features.

### 2) Document Ingestion Abstraction
Introduce a format-agnostic ingestion layer so extraction is no longer EPUB-only:
- Add support for .txt, .md, DOCX
- Normalize extracted text into one internal format used by scene extraction.
- Capture source metadata and parsing errors consistently.

This keeps downstream services independent of input file type.

### 3) Content Directory Generalization (`books` to `documents`)
Generalize input storage from book-specific to document-generic:
- Rename the default folder from `books/` to `documents/`.
- Track files in subfolders with relative paths.
- Add backward compatibility so existing `books/` users are not broken immediately.
- Add non-destructive migration/backfill logic so existing persisted references continue to resolve under the new `documents` structure.

This aligns product language and behavior with broader open-source use cases.

### 4) Settings System and User Defaults
Implement persistent app settings and expose them in the UI:
- Add `art_style` catalog table.
- Add `app_settings` table for global defaults.
- Seed default art styles and default scenes-per-run (5) in migration.
- Build a settings page to manage defaults.

This removes hardcoded configuration and makes behavior user-configurable.

### 5) Pipeline Orchestration and Job Model
Add a lightweight HTTP-triggered pipeline using existing patterns already in the codebase (`asyncio.create_task()` for background work, sequential stage chaining from `image_gen_cli.py`):

**A single `PipelineRun` table** with a status enum that progresses through stages:
- `pending → extracting → ranking → generating_prompts → generating_images → completed | failed`
- Fields: `book_slug`, `started_at`, `completed_at`, `current_stage`, `error_message`, and config overrides (scenes count, art style).

**One POST endpoint** to start a run:
- Creates a `PipelineRun` record with status `pending`.
- Spawns the work via `asyncio.create_task()` (same pattern as the existing remix endpoints).
- Returns the run ID immediately with HTTP 202.
- The background task reuses the existing service-layer logic from `image_gen_cli.py` — extraction, ranking, prompt generation, and image generation called in sequence with existing skip/resume logic. Updates the `PipelineRun` row as it transitions between stages and catches failures.

**One GET endpoint** to poll status:
- Returns the `PipelineRun` record (current stage, progress, errors).
- Frontend polls on interval (every few seconds) to update the dashboard.

**Deliberately out of scope for initial release:**
- No separate `StageResult` table — the status enum plus `error_message` is enough. Per-stage results can be added later if there's demand.
- No retry/cancellation system — if a run fails, the user starts a new one (existing resume logic handles picking up where it left off).
- No WebSocket/SSE for real-time updates — polling a GET endpoint is fine at this scale.
- No external job queue (Celery, Redis, etc.) — the pipeline runs infrequently and the work is I/O-bound (LLM/image API calls), so it sits on the async event loop without blocking.

This provides HTTP-triggered pipeline execution with status visibility, without introducing new infrastructure dependencies.

### 6) Document Dashboard and Status Tracking
Create a dashboard focused on source files and lifecycle visibility:
- Show all files in `documents/`, including nested folders.
- Display pipeline state per file (extracted, ranked, prompts generated, images generated).
- Surface last run outcome and failure reasons.

This becomes the central operator view for the full pipeline.

### 7) One-Click Pipeline Launch with Runtime Overrides
From the dashboard, allow users to run end-to-end processing per file:
- Let users choose scenes-to-generate at launch time.
- Default to settings value (5) unless overridden.
- (Optional) allow art style override while still honoring defaults.
- If a file has been partially processed, allow users to resume and auto detect where to resume from.

This balances ease of use (defaults) with experimentation (overrides).

### 8) Cost and Safety Guardrails
Add clear usage reporting for open-source users:
- Persist model/image usage details by run.
- Include runtime input/output counts and timing in run summaries.
- Surface usage summaries in polling/dashboard views.

This reduces accidental overuse and improves trust in operation.

### 9) Observability and Diagnostics
Improve debugging and supportability:
- Structured logs for each pipeline stage.
- Per-stage duration tracking.
- Persisted error codes/messages for failed runs.

This makes issue triage practical for maintainers and contributors.

### 10) Contributor and Community Standards
Add open-source governance files and templates:
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md` review/update
- GitHub issue and PR templates

This sets clear expectations for contributions and responsible disclosure.

### 11) Public Developer Experience
Improve first-run and contributor onboarding:
- Update README with fast local setup, architecture overview, and quickstart workflow.
- Provide clear `.env.example` with required and optional keys.
- Document common development commands and test/lint flow.

This reduces onboarding friction and improves project approachability.

### 12) CI Quality Gates for Public Contributions
Add/expand CI checks for pull requests:
- Backend lint/type/test checks.
- Frontend lint/build checks.
- Required checks before merge.

This protects code quality once external contributions begin.

### 13) Open-Source License Finalization
Adopt the MIT License for the public release:
- Confirm repository `LICENSE` uses MIT text.
- Reference license choice in README and project metadata.

This completes legal readiness with a highly permissive license.

### 14) Existing Data Migration and Backfill Verification
Apply this to every database/model/data-structure change introduced in the roadmap:
- Write forward migrations plus backfills so existing rows map to new entities/fields.
- Preserve existing operational data (no destructive delete/truncate migrations for transition work).
- Add explicit verification checks (row counts, nullability expectations, FK integrity, spot checks) before marking each migration complete.
- Keep compatibility fields only as long as needed, then remove them in a later, explicit cleanup migration after reads/writes are fully migrated.

This ensures open-source readiness work does not break or discard current project data.
