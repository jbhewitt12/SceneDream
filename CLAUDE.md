# Repository Guidelines

SceneDream orchestrates an end-to-end pipeline that ingests EPUB novels, extracts cinematic scenes, ranks them, develops DALL·E 3-ready prompts, and renders images. Everything runs locally for fast iteration and experimentation.

This project is built with the FastAPI Template.

## Key files

- `backend/app/services/scene_extraction/scene_extraction.py` — core extractor that chunks EPUBs, calls Gemini, and persists scene metadata.
- `backend/app/services/scene_extraction/scene_refinement.py` — optional Grok-powered refinement pass that flags keep/discard decisions and annotates scenes.
- `backend/app/services/scene_ranking/scene_ranking_service.py` — applies weighted multi-model scoring to prioritize scenes ready for prompting.
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` — builds structured DALL·E 3 prompt variants with context windows and style metadata.
- `backend/app/services/image_generation/image_generation_service.py` & `backend/app/services/image_generation/dalle_image_api.py` — orchestrate image creation, storage, and retries; the CLI entrypoint lives in `backend/app/services/image_gen_cli.py`.
- `backend/app/services/langchain/gemini_api.py` & `backend/app/services/langchain/xai_api.py` — LangChain wrappers around Gemini 2.5 Pro and xAI Grok used across extraction, refinement, and ranking.

## Project Structure & Module Organization
- `backend/app` bundles the FastAPI app: `api/routes` exposes REST resources for scenes, rankings, prompts, and generated images; `services/*` holds the pipeline stages plus EPUB tooling; `repositories/` centralize SQLModel persistence; `schemas/` defines DTOs; tests for both API and services live in `backend/app/tests`.
- `backend/models` defines SQLModel tables (`SceneExtraction`, `SceneRanking`, `ImagePrompt`, `GeneratedImage`) consumed by Alembic migrations in `backend/app/alembic`.
- `frontend/src` houses the React + Chakra UI client: `routes/_layout/*` renders dashboards for each pipeline stage, `api/` & `client/` contain the generated OpenAPI SDK, while `components/`, `hooks/`, and `theme/` provide shared UI primitives.
- `documents/` stores source inputs for ingestion (legacy `books/` paths still resolve for backward compatibility); `img/` accumulates generated assets (notably `img/generated/<book>/...`).
- `scripts/` contains automation like `generate-client.sh` and deployment helpers.

## Concurrency Rule
- All new FastAPI endpoints must be implemented as async, non-blocking handlers so concurrent requests stay responsive; offload CPU-bound work to background tasks or executors to avoid blocking the event loop.

## Build, Test, and Development Commands
- `docker compose watch` spins up the full stack with live reload.
- `cd backend && uv run fastapi dev app/main.py` runs the API locally after stopping the compose backend service.
- `cd frontend && npm run dev` serves the Vite app on `5173`; stop the Docker frontend first if running.
- `cd backend && uv run pytest` executes pytest with coverage and HTML reports; pass extra pytest flags at the end.
- Pipeline CLIs: from `backend/`, use `uv run python -m app.services.scene_extraction.main ...`, `uv run python -m app.services.scene_ranking.main rank ...`, and `uv run python -m app.services.image_generation.main ...` for staged or end-to-end runs.

## Coding Style & Naming Conventions
- Python code uses 4-space indentation with linting/type checks enforced by `uv run bash scripts/lint.sh` (runs mypy, ruff check, and ruff format).
- Keep SQLModel classes in PascalCase (`SceneExtraction`, `SceneRanking`, `ImagePrompt`, `GeneratedImage`), repository methods in snake_case, and JSON keys camelCase to match frontend expectations.
- Frontend TypeScript follows Biome (configured in `frontend/biome.json`) with 2-space indentation; run `npm run lint` to format and organize imports.

## Testing Guidelines
- Backend tests live in `backend/app/tests`; prefer unit and service tests that stub external LLM/image calls, and mark any live API smoke tests (e.g. `test_gemini_api_live.py`) with `pytest.mark.integration` so they auto-skip without credentials.
- Never do frontend E2E tests.

## Testing Requirements for New Code
- Every new service must have corresponding unit tests in `backend/app/tests/services/`.
- Every new API route must have corresponding route tests in `backend/app/tests/api/routes/`.
- Every new repository must have corresponding tests in `backend/app/tests/repositories/`.
- All external API calls (LLM, image generation, etc.) must be mocked using `monkeypatch` — never call live services in unit tests.
- Run `cd backend && uv run pytest` after making changes and ensure all tests pass before considering work complete.
- New test data must be cleaned up: use the shared `scene_factory` and `prompt_factory` fixtures from `conftest.py` which handle FK-safe teardown automatically.
- Do not duplicate fixture definitions — reuse the shared factories in `backend/app/tests/conftest.py`.
- For async service tests, use `@pytest.mark.anyio("asyncio")` and define the test as `async def`.
- Follow the existing test patterns in `backend/app/tests/services/test_scene_ranking_service.py` as the reference for service-level unit tests (factory + monkeypatch + assertions + cleanup).
