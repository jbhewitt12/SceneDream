# SceneDream Backend

## Requirements

- Docker
- uv

## Run Locally

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

## Backend Layout

- `app/api/routes/`: API endpoints for scene extraction/ranking/prompts/images
- `app/services/`: pipeline orchestration and provider integrations
- `app/repositories/`: SQLModel persistence layer
- `app/schemas/`: request/response DTOs
- `app/tests/`: backend tests
- `models/`: SQLModel table definitions used by Alembic

## Tests and Lint

```bash
cd backend
uv run pytest
uv run bash scripts/lint.sh
```

## Migrations

Create and apply migrations from the backend directory:

```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Alembic metadata is sourced from the project SQLModel modules in `backend/models`.

## Notes

- SceneDream does not require auth/user bootstrap for local operation.
- When adding new endpoints, use async non-blocking handlers.
