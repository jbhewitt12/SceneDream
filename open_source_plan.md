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
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 3 - Content Directory Generalization (`books` to `documents`)
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 4 - Settings System and User Defaults
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 5 - Pipeline Orchestration and Job Model
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 6 - Document Dashboard and Status Tracking
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 7 - One-Click Pipeline Launch with Runtime Overrides
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 8 - Cost and Safety Guardrails
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 9 - Observability and Diagnostics
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 10 - Contributor and Community Standards
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 11 - Public Developer Experience
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 12 - CI Quality Gates for Public Contributions
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

#### Step 13 - Open-Source License Finalization
- Done: no
- Date:
- What was implemented:
- Important implementation details:
- Differences from plan:

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
Add basic limits and protections for open-source users:
- Configurable max scenes per run.
- Basic request/rate throttling for heavy endpoints.
- Clear reporting of model/image usage by run.

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
