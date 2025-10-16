# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SceneDream is an AI-powered system that extracts visually compelling scenes from sci-fi books (EPUBs), ranks them, generates optimized image prompts, and creates images/videos. The workflow: EPUB → Scene Extraction → Scene Ranking → Image Prompt Generation → Image Generation.

**Local development only.** See `plan.md` for the roadmap.

## Architecture

Built on the FastAPI full-stack template with:
- **Backend**: FastAPI + SQLModel (ORM) + PostgreSQL + Alembic migrations
- **Frontend**: React + TypeScript + Vite + TanStack Router/Query + Chakra UI
- **AI Integration**: Gemini (extraction/prompts), Grok (refinement/ranking), DALL-E 3 (image generation)

### Directory Structure

```
backend/
  models/              # SQLModel table definitions (scene_extraction, scene_ranking, image_prompt, generated_image)
  app/
    models.py          # Core User/Item models
    alembic/           # Database migrations
    repositories/      # Data access layer (scene_extraction, scene_ranking, image_prompt, generated_image)
    services/          # Business logic
      scene_extraction/       # EPUB parsing, Gemini extraction, scene refinement
      scene_ranking/          # Grok-based ranking (visual/AI potential)
      image_prompt_generation/ # Gemini prompt generation with DALL-E 3 optimization guides
      image_generation/       # DALL-E 3 API wrapper
      langchain/              # gemini_api.py, xai_api.py
      image_gen_cli.py        # CLI for orchestrating generation workflows
    api/routes/        # FastAPI endpoints (scene_extractions, scene_rankings, image_prompts, generated_images)
    schemas/           # Pydantic DTOs for API contracts

frontend/
  src/
    routes/            # TanStack Router pages (_layout/, scene-rankings.tsx, extracted-scenes.tsx, etc.)
    client/            # Auto-generated OpenAPI client
    components/        # Reusable UI components
    hooks/             # React custom hooks

books/                 # EPUB inputs
img/generated/         # Generated images (structured by book/chapter/scene)
scripts/               # Build/test/deployment automation
```

### Key Data Flow

1. **Scene Extraction** (`backend/app/services/scene_extraction/scene_extraction.py`):
   - `SceneExtractor` chunks EPUB chapters (~12k chars with paragraph overlap)
   - Gemini 2.5 Pro extracts scenes via `gemini_api.json_output()` with `SCENE_EXTRACTION_SCHEMA_TEXT`
   - Optional refinement via Grok (`scene_refinement.py`) marks scenes as keep/discard
   - Persists to `scene_extractions` table via `SceneExtractionRepository`
   - CLI: `uv run python -m app.services.scene_extraction.main preview-excession <N> [--refine]`

2. **Scene Ranking** (`backend/app/services/scene_ranking/`):
   - Scores scenes on visual potential, AI feasibility, uniqueness
   - Uses Gemini Flash or Grok models
   - Stores in `scene_rankings` table with composite scores

3. **Image Prompt Generation** (`backend/app/services/image_prompt_generation/`):
   - Converts ranked scenes into multiple prompt variants (default: 4)
   - Uses `dalle3_multi_genre_prompting_cheatsheet.md` as embedded guidelines
   - Includes 3 paragraphs before + 1 after scene for context (loaded from EPUB, not stored)
   - Persists to `image_prompts` table with structured metadata (style_tags, attributes: camera/lens/composition/aspect_ratio)

4. **Image Generation** (`backend/app/services/image_generation/`):
   - `dalle_image_api.py` wraps OpenAI DALL-E 3 API
   - Reads prompts from DB via `ImagePromptRepository`
   - Saves images to `img/generated/<book_slug>/chapter-<N>/scene-<M>-v<variant>.png`
   - Persists metadata to `generated_images` table

### Model Relationships

- `SceneExtraction` ← many `SceneRanking`, many `ImagePrompt`, many `GeneratedImage`
- `ImagePrompt` → many `GeneratedImage`
- Unique constraints prevent duplicate runs (e.g., `(scene_extraction_id, model_name, prompt_version, variant_index)` for `image_prompts`)

## Development Commands

### Full Stack with Docker Compose
```bash
docker compose watch            # Start all services with live reload
docker compose logs backend     # View backend logs
docker compose logs frontend    # View frontend logs
docker compose stop <service>   # Stop a specific service
```

### Backend (Python/FastAPI)
```bash
cd backend
uv sync                          # Install dependencies
source .venv/bin/activate        # Activate venv (or use 'uv run')
uv run fastapi dev app/main.py   # Run backend locally (stop Docker backend first)
uv run bash scripts/lint.sh      # Run ruff + ruff format
```

### Frontend (React/TypeScript)
```bash
cd frontend
npm install                      # Install dependencies
npm run dev                      # Run Vite dev server (stop Docker frontend first)
npm run build                    # Build for production
npm run lint                     # Run Biome formatter/linter
./scripts/generate-client.sh     # Regenerate OpenAPI TypeScript client
```

When you create a new route, regenerate the route tree:
```bash
docker compose build frontend && docker compose up -d frontend --force-recreate
```

### Database Migrations
```bash
uv run alembic upgrade head                              # Apply migrations
```

### Scene Extraction CLI
```bash
cd backend
uv run python -m app.services.scene_extraction.main preview-excession 3 --refine
uv run python -m app.services.scene_extraction.main extract-excession --refine
```

### Image Generation CLI
Main orchestration CLI in `backend/app/services/image_gen_cli.py` (see file for usage examples).

## Code Style and Conventions

### Backend (Python)
- **Indentation**: 4 spaces
- **Linting**: `ruff` + `ruff format` (run via `uv run bash scripts/lint.sh`)
- **Naming**:
  - SQLModel classes: `PascalCase` (e.g., `SceneExtraction`, `ImagePrompt`)
  - Repository methods: `snake_case` (e.g., `get_by_id`, `list_for_scene`)
  - Database table names: `snake_case` (auto-derived from model class name with underscores)
- **Models**: Define in `backend/models/<domain>.py` (e.g., `scene_extraction.py`, `image_prompt.py`)
- **Repositories**: One per model in `backend/app/repositories/`, inherit common patterns
- **API Schemas**: Pydantic models in `backend/app/schemas/`, use camelCase for JSON keys to match frontend
- **JSON keys**: Use camelCase in API responses (configure with Pydantic `alias_generator`)

### Frontend (TypeScript)
- **Indentation**: 2 spaces
- **Linting**: Biome (config: `frontend/biome.json`)
- **Format command**: `npm run lint`
- **Naming**: camelCase for variables/functions, PascalCase for components
- **Client**: Auto-generated from OpenAPI schema (`frontend/src/client/`)

## Testing Guidelines

### Backend
- **Unit tests only** for logic that doesn't call external APIs (LLM services, etc.)
- **Location**: `backend/app/tests/`
- **Run**: `uv run pytest`
- **Coverage report**: Generated at `htmlcov/index.html`
- Use transactional DB fixtures or in-memory sessions for repository tests

### Frontend
- **No E2E tests** (skip Playwright for this project)

## Environment Variables

Key variables in `.env`:
- `OPENAI_API_KEY`: DALL-E 3 generation
- `XAI_API_KEY`: Grok for refinement/ranking
- `GEMINI_API_KEY`: Scene extraction and prompt generation
- `POSTGRES_PASSWORD`: Database access
- `SECRET_KEY`: FastAPI session security
- `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`: Admin account

## Important Implementation Notes

### Scene Extraction
- Chunks overlap paragraphs to prevent scene truncation
- Paragraph numbering is 1-indexed
- Deduplicates scenes within and across chunks
- Refinement is optional (pass `--refine` flag)

### Image Prompt Generation
- **Context loading**: Reopens EPUB to get 3 paragraphs before + 1 after scene for composition details
- **Do NOT persist copyrighted text**: Store only `context_window` metadata (paragraph spans)
- **Cheat sheet**: `dalle3_multi_genre_prompting_cheatsheet.md` is embedded verbatim in LLM prompt
- **Variants**: Default 4 per scene, explore different styles/compositions
- **Unique constraint**: `(scene_extraction_id, model_name, prompt_version, variant_index)`

### Image Generation
- Aspect ratio mapping: "1:1" → 1024x1024, "9:16" → 1024x1792, "16:9" → 1792x1024
- Default quality: `standard` (use `hd` for finals)
- Response format: `b64_json` (or `url`)
- File naming: `scene-<sceneNumber>-v<variant>.png`
- Persist metadata to `generated_images` table with checksums

### Database
- All IDs are UUIDs
- Timestamps: `created_at`, `updated_at` (auto-managed)
- JSONB columns for structured metadata (`attributes`, `raw_response`, `context_window`)
- Foreign keys enforce referential integrity (e.g., `scene_extraction_id` → `scene_extractions.id`)

## URLs

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
