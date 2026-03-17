# Repository Guidelines

SceneDream orchestrates a local end-to-end pipeline that ingests source documents, extracts cinematic scenes, ranks them, generates structured image prompts, renders images, and optionally queues approved outputs for social posting.

The stack is FastAPI + SQLModel on the backend, React + Chakra UI + TanStack Router on the frontend, PostgreSQL for metadata, and filesystem-backed source/generated assets.

## Key files

- `backend/app/services/scene_extraction/scene_extraction.py` - core extractor that loads supported book/document formats, chunks chapters, calls Gemini/OpenAI-backed LLM routing, and persists scene metadata.
- `backend/app/services/scene_extraction/scene_refinement.py` - optional refinement pass that annotates scenes with keep/discard decisions and extra metadata.
- `backend/app/services/scene_ranking/scene_ranking_service.py` - ranks extracted scenes and persists weighted scoring output.
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` - builds prompt-generation configs, resolves `random_mix` vs `single_style` art-style behavior, and persists prompt variants plus metadata.
- `backend/app/services/image_generation/image_generation_service.py` - synchronous image generation orchestration across registered providers.
- `backend/app/services/image_generation/batch_image_generation_service.py` - OpenAI Batch API image generation flow with persisted batch tracking (kept in codebase but not wired to orchestrator-backed launch surfaces).
- `backend/app/services/pipeline/pipeline_orchestrator.py` - unified execution entry point for all orchestrated pipeline work; handles full-document runs, prompt-plus-image runs, scene-targeted generation, remix, and custom-remix flows.
- `backend/app/services/pipeline/orchestrator_config.py` - typed dataclasses for execution targets (`DocumentTarget`, `SceneTarget`, `RemixTarget`, `CustomRemixTarget`), `PipelineStagePlan`, `PipelineExecutionConfig`, `PipelineExecutionContext`, `PreparedPipelineExecution`, `PipelineStats`, and `PipelineExecutionResult`.
- `backend/app/services/pipeline/background.py` - `spawn_background_task` helper that schedules asyncio tasks and logs unhandled exceptions.
- `backend/app/services/pipeline/exceptions.py` - domain exceptions (`PipelineValidationError`, `DocumentNotFoundError`, `SourceDocumentMissingError`) raised during launch validation.
- `backend/app/services/pipeline/pipeline_run_start_service.py` - resolves launch requests into `PreparedPipelineExecution` and delegates to the orchestrator; no longer contains execution logic.
- `backend/app/services/pipeline/document_stage_status_service.py` - computes and synchronizes document-level extraction/ranking statuses (`pending`, `running`, `completed`, `failed`, `stale`).
- `backend/app/services/document_dashboard_service.py` - builds the Documents dashboard payload by merging filesystem discovery, canonical documents, counts, and stage status metadata.
- `backend/app/services/art_style/art_style_catalog_service.py` - transactional sync service for DB-backed recommended/other art-style lists managed from Settings.
- `backend/app/services/social_posting/social_posting_service.py` - queues and posts approved images to configured social services.
- `frontend/src/routes/_layout/documents.tsx` - Documents dashboard with adaptive launch CTA and per-document art-style controls.
- `frontend/src/routes/_layout/settings.tsx` - Settings page for pipeline defaults and editable art-style lists.
- `frontend/src/components/Common/PromptArtStyleControl.tsx` - shared frontend control for `Random Style Mix` vs `Single art style`.

## Project Structure & Module Organization

- `backend/app/api/routes` exposes the current API surface: `documents`, `pipeline-runs`, `settings`, `scene-extractions`, `scene-rankings`, `image-prompts`, and `generated-images`.
- `backend/app/services` holds business logic for books/document loading, extraction, ranking, prompt generation, image generation, analytics, pipeline orchestration, art-style management, image cleanup, prompt metadata, and social posting.
- `backend/app/repositories` is the persistence boundary around SQLModel entities. Keep business rules out of repositories.
- `backend/models` defines the canonical SQLModel tables, including `Document`, `PipelineRun`, `GeneratedAsset`, `SceneExtraction`, `SceneRanking`, `ImagePrompt`, `GeneratedImage`, `ArtStyle`, `AppSettings`, `ImageGenerationBatch`, and `SocialMediaPost`.
- `backend/app/schemas` defines API payloads. The current API contract is snake_case, and the generated frontend client expects snake_case fields.
- `backend/app/tests` contains route, service, repository, book-loader, and integration-smoke tests.
- `frontend/src/api` wraps the generated OpenAPI client in `frontend/src/client`. Prefer updating/regenerating the client rather than writing ad hoc fetch code.
- `frontend/src/routes/_layout` contains the main app screens for documents, extracted scenes, rankings, prompt gallery, generated images, and settings.
- `frontend/src/components` contains shared UI, prompt/image presentation, and dashboard controls.
- `documents/` is the canonical source directory scanned by the dashboard. Legacy `books/` paths still resolve for compatibility.
- `img/generated/` stores generated image outputs; `img/` is also mounted by the backend for serving local assets.
- `issues/` contains implementation plans and architectural change notes for major shipped features; review relevant issues before large refactors.

## Orchestrator Architecture

The pipeline uses a two-phase model: **preparation** then **execution**.

1. `pipeline_run_start_service.py` resolves a launch request into a `PreparedPipelineExecution` (persists a pending `PipelineRun`, resolves document/scene context, validates the stage plan) and hands it off to `PipelineOrchestrator`.
2. `PipelineOrchestrator` owns all status transitions (`pending` → `running` → `completed`/`failed`), diagnostics, and stage dispatch. It is the single execution entry point for all orchestrated work.

**Execution targets** (`orchestrator_config.py`):
- `DocumentTarget` — full-document pipeline run (extraction → ranking → prompts → images).
- `SceneTarget` — scene-specific prompt/image generation with an exact variant count.
- `RemixTarget` — remix an existing generated image.
- `CustomRemixTarget` — custom-remix with user-supplied prompt text.

**Stage plan** (`PipelineStagePlan`): explicit booleans for `run_extraction`, `run_ranking`, `run_prompt_generation`, `run_image_generation`. Validated against the target type before execution starts.

**Batch image generation** is intentionally not wired to orchestrator-backed launch surfaces. The `batch_image_generation_service.py` stays in the codebase for future reintroduction.

## Concurrency Rule

- All new FastAPI endpoints must be async and non-blocking. Offload CPU-bound or blocking filesystem/network work to background tasks, executors, or threadpool helpers so concurrent requests stay responsive.

## Build, Test, and Development Commands

- `docker compose watch` starts the full stack with live reload.
- `docker compose up -d db` starts only Postgres for local backend/frontend development.
- `cd backend && uv sync` installs backend dependencies.
- `cd backend && uv run alembic upgrade head` applies database migrations.
- `cd backend && uv run fastapi dev app/main.py` runs the backend locally.
- `cd frontend && npm install` installs frontend dependencies.
- `cd frontend && npm run dev` starts the Vite frontend on port `5173`.
- `cd backend && uv run pytest` runs the backend test suite. Integration-marked live tests are excluded by default.
- `cd backend && uv run bash scripts/lint.sh` runs backend mypy, Ruff check, and Ruff format.
- `cd frontend && npm run lint` runs Biome formatting/lint fixes.
- `cd frontend && npm run build` runs the frontend TypeScript build and Vite production build.
- `./scripts/generate-client.sh` regenerates `openapi.json`, `frontend/openapi.json`, and the frontend OpenAPI client.

## Pipeline and CLI Commands

- Run from `backend/`.
- `uv run python -m app.services.scene_extraction.main --help` for extraction commands (`extract` — standalone escape hatch for re-running extraction on completed documents).
- `uv run python -m app.services.scene_ranking.main rank --help` for ranking commands (`rank` — standalone escape hatch for re-running ranking on completed documents).
- `uv run python -m app.services.image_gen_cli run --help` for the end-to-end pipeline CLI (delegates to the orchestrator for all orchestrated runs).
- `uv run python -m app.services.prompt_metadata.main --help` for prompt-metadata tooling.
- Legacy CLI commands `prompts`, `images`, `refresh`, and `backfill` have been removed.

## Coding Style & Naming Conventions

- Python uses 4-space indentation. Run `uv run bash scripts/lint.sh` before finishing backend work.
- TypeScript uses Biome formatting with 2-space indentation. Run `npm run lint` in `frontend/`.
- Keep SQLModel classes in PascalCase and repository/service methods in snake_case.
- Preserve snake_case API/schema fields unless you are intentionally changing the OpenAPI contract and regenerating the frontend client in the same change.
- Keep route handlers thin: HTTP validation/translation in routes, orchestration in services, persistence in repositories.
- Prefer DB-backed runtime configuration over hardcoded catalogs when touching art-style or settings behavior.
- Prompt art-style mode values are `random_mix` and `single_style`; keep backend schemas, frontend state, and pipeline launch payloads aligned.

## Testing Guidelines

- Backend tests live in `backend/app/tests`.
- Prefer unit/service/route tests that mock external LLM, image-generation, and posting APIs with `monkeypatch`.
- Live smoke tests such as `test_gemini_api_live.py` and `test_gpt_image_api_live.py` must stay marked with `pytest.mark.integration`.
- Never add frontend E2E tests to this repository.
- If you change the OpenAPI contract or generated frontend client usage, run both `cd frontend && npm run lint` and `cd frontend && npm run build`.

## Testing Requirements for New Code

- Every new service needs service-level tests under `backend/app/tests/services/`.
- Every new API route needs route tests under `backend/app/tests/api/routes/`.
- Every new repository needs repository tests under `backend/app/tests/repositories/`.
- Mock all external API calls in unit tests. Do not hit live LLM, image, or social APIs in normal test runs.
- Run `cd backend && uv run pytest` after backend changes and ensure the suite passes before considering the work complete.
- Reuse shared fixtures from `backend/app/tests/conftest.py`, especially `scene_factory` and `prompt_factory`, instead of redefining fixture stacks.
- For async service tests, use `@pytest.mark.anyio("asyncio")` and `async def`.
- Follow the established service-test style in files such as `backend/app/tests/services/test_scene_ranking_service.py`, `backend/app/tests/services/test_pipeline_run_start_service.py`, and `backend/app/tests/services/test_image_prompt_generation_service.py`.
