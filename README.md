# SceneDream

SceneDream is a local-first pipeline for turning text based stories into generated scene artwork. It ingests source text, extracts cinematic scenes, ranks them, creates image generation prompts, and renders images.

## Pipeline Overview

1. Ingest source documents (`.epub`, `.mobi`, `.txt`, `.md`, `.docx`)
2. Extract cinematic scenes
3. Optionally refine scenes
4. Rank scenes for generation priority
5. Generate prompt variants
6. Generate images and persist assets

## Architecture

- Backend: FastAPI + SQLModel + Alembic
- Frontend: React + TypeScript + Chakra UI + TanStack Router
- Database: PostgreSQL (pipeline metadata)
- Filesystem: `documents/` for source files, `img/generated/` for outputs
- AI providers: Gemini/xAI (extraction + ranking) and OpenAI (image generation)

## Quickstart (Docker, Recommended)

1. Create local environment config:

```bash
cp .env.example .env
```

2. Update provider keys in `.env` only for features you plan to run:
- `GEMINI_API_KEY` for extraction/ranking
- `XAI_API_KEY` for optional refinement/ranking
- `OPENAI_API_KEY` for image generation

3. Start the stack:

```bash
docker compose watch
```

4. Open the app:
- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs

## Quickstart (Run Backend/Frontend Directly)

1. Start only Postgres in Docker:

```bash
docker compose up -d db
```

2. Start backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

3. Start frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

## First Workflow

1. Add source files under `documents/` (nested folders supported).
2. Open `/documents` in the dashboard.
3. Launch a pipeline run for a document.
4. Review generated artifacts under `img/generated/<book_slug>/`.

Note: legacy `books/` paths are still supported for backward compatibility.

## Common Development Commands

```bash
cd backend && uv run pytest
cd backend && uv run bash scripts/lint.sh
cd frontend && npm run lint
cd frontend && npm run build
./scripts/generate-client.sh
```

## Pipeline CLI Commands

Run from `backend/`:

```bash
uv run python -m app.services.scene_extraction.main --help
uv run python -m app.services.scene_ranking.main rank --help
uv run python -m app.services.image_generation.main --help
```

## License

SceneDream is licensed under the [MIT License](LICENSE).

## Additional Documentation

- Backend details: `backend/README.md`
- Frontend details: `frontend/README.md`
- Contribution guide: `CONTRIBUTING.md`
- Deployment notes: `deployment.md`
