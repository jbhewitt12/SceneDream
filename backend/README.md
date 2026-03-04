# SceneDream Backend

FastAPI backend for ingestion, extraction, ranking, prompt generation, image generation, and pipeline orchestration.

## Prerequisites

- Python 3.10+
- `uv`
- PostgreSQL (local) or Docker compose `db` service

## Environment Setup

Backend settings are loaded from the repository root `.env` file.

```bash
cp ../.env.example ../.env
```

Set at least:
- `PROJECT_NAME`
- `POSTGRES_SERVER`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Set provider keys only for the stages you run:
- `GEMINI_API_KEY`
- `XAI_API_KEY`
- `OPENAI_API_KEY`

## Run Locally

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

## Tests and Lint

```bash
cd backend
uv run pytest
uv run bash scripts/lint.sh
```

## Migrations

```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Alembic metadata is sourced from SQLModel definitions in `backend/models`.

## Backend Layout

- `app/api/routes/`: API endpoints
- `app/services/`: pipeline stages and provider integrations
- `app/repositories/`: persistence and query layer
- `app/schemas/`: request/response DTOs
- `app/tests/`: backend tests
- `models/`: SQLModel table definitions

## Contributor Notes

- New FastAPI endpoints must be `async` and non-blocking.
- External API calls in tests must be mocked; do not call live providers in unit tests.
