# SceneDream

SceneDream is a local-first pipeline that ingests EPUB novels, extracts cinematic scenes, ranks them, generates structured DALL-E 3 prompts, and renders images.

## Architecture

- Backend: FastAPI + SQLModel + Alembic
- Frontend: React + TypeScript + Chakra UI + TanStack Router
- Storage: PostgreSQL for pipeline metadata and local filesystem for generated assets
- AI providers: Gemini and xAI Grok for extraction/refinement/ranking, DALL-E for image generation

SceneDream is a single-operator system and does not include login/signup/user management flows.

## Pipeline Stages

1. Scene extraction from EPUB chapters
2. Optional scene refinement pass
3. Scene ranking with weighted scoring
4. Image prompt generation (variant prompts and style metadata)
5. Image generation and asset persistence

Key services are under `backend/app/services/`:

- `scene_extraction/`
- `scene_ranking/`
- `image_prompt_generation/`
- `image_generation/`

## Local Development

Start the full stack:

```bash
docker compose watch
```

Run backend locally:

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

Run frontend locally:

```bash
cd frontend
npm install
npm run dev
```

## Validation Commands

```bash
cd backend && uv run pytest
cd backend && uv run bash scripts/lint.sh
./scripts/generate-client.sh
cd frontend && npm run lint
cd frontend && npm run build
```

## Data Directories

- `books/`: EPUB inputs and chapter artifacts
- `img/generated/`: generated images and derivatives

## Additional Docs

- Backend guide: `backend/README.md`
- Frontend guide: `frontend/README.md`
- Deployment guide: `deployment.md`
