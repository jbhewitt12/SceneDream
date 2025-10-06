# Repository Guidelines

SceneDream is a project that uses AI to extract scenes from books and generate images and videos inspired by them.

It will be local development only for now.

See `plan.md` for a rough outline of the plan.

This project is built with the FastAPI Template.

## Key files

- `backend/app/services/scene_extraction/scene_extraction.py`
- `backend/app/services/langchain/gemini_api.py`

## Project Structure & Module Organization
- `backend/app` hosts FastAPI services, domain repositories, and `schemas` for DTOs; tests live in `backend/app/tests`.
- `backend/models` stores SQLModel definitions used by Alembic migrations in `backend/app/alembic`.
- `frontend/src` contains React/Chakra UI features, with shared utilities under `src/lib`; browser E2E specs sit in `frontend/tests`.
- `books/` holds EPUB inputs for scene extraction; `scripts/` provides automation for build/test pipelines; static assets live in `img/`.

## Build, Test, and Development Commands
- `docker compose watch` spins up the full stack with live reload.
- `cd backend && uv run fastapi dev app/main.py` runs the API locally after stopping the compose backend service.
- `cd frontend && npm run dev` serves the Vite app on `5173`; stop the Docker frontend first if running.
- `cd backend && uv run bash scripts/test.sh` executes pytest with coverage; add `--keyword <pattern>` to target specific suites.

## Coding Style & Naming Conventions
- Python code follows 4-space indentation with `ruff` and `ruff format`; run `uv run bash scripts/lint.sh` before committing.
- Keep SQLModel classes in `PascalCase`, repository methods in `snake_case`, and JSON keys camelCase to match frontend expectations.
- Frontend TypeScript uses Biome (configured in `frontend/biome.json`) with 2-space indentation; format via `npm run lint`.

## Testing Guidelines
- Only write unit tests for backend logic that doesn't call external APIs.
- Don't do frontend E2E tests.