<img src="img/assets/banner/The-Gilded-Unfurl.png" width="19%"><img src="img/assets/banner/The-God-Scar.png" width="19%"><img src="img/assets/banner/Obsidian-Eyed-Muse.png" width="19%"><img src="img/assets/banner/Petals-of-Iron-Ink.png" width="19%"><img src="img/assets/banner/Angelic-Zenith.png" width="19%">

<h1 align="center">SceneDream</h1>

<img src="img/assets/banner/Aria-of-Impact.png" width="19%"><img src="img/assets/banner/Ink-Stained-Singularity.png" width="19%"><img src="img/assets/banner/Baroque-Breach.png" width="19%"><img src="img/assets/banner/Command-of-the-Depths.png" width="19%"><img src="img/assets/banner/Diamond-Sky.png" width="19%">

SceneDream is a project for automatically turning text based stories into AI images. You put in a story, and it comes out as a bunch of images!

It's set up as a pipeline you run on your own computer that ingests source text, extracts cinematic scenes, ranks them, creates image generation prompts, and generates images.

All you'll need to get it working is an OpenAI API key and a text based story. You don't need to be technically savvy to use it, because it's all done through a web interface.

## The Interface

<table>
<tr>
<td width="50%">
<img src="img/assets/documents-frontend.png" width="100%">
<b>Documents Dashboard</b> —  Launch the pipeline from here. See how many scenes were extracted, how many have been ranked, how many prompts and images have been generated, and kick off a new run with one click.
</td>
<td width="50%">
<img src="img/assets/generated-scenes-frontend.png" width="100%">
<b>Generated Images</b> — Browse every image generated across all your documents. Filter by book, provider, or approval status. Click on an image to see the prompt that was used to generate it and the raw scene text that was used to create it.
</td>
</tr>
</table>

## Pipeline Overview

1. Ingest source documents (`.epub`, `.mobi`, `.txt`, `.md`, `.docx`)
2. Extract cinematic scenes
3. Discard any scenes that are not suitable for generation
4. Rank scenes for generation priority
5. Generate prompt variants
6. Generate images (Default to gpt-image-1.5)

## Architecture

- Backend: FastAPI + SQLModel + Alembic
- Frontend: React + TypeScript + Chakra UI + TanStack Router
- Database: PostgreSQL (pipeline metadata)
- Filesystem: `documents/` for source text files, `img/generated/` for outputs
- AI providers: Gemini/OpenAI (LLM tasks with automatic fallback) and OpenAI (image generation)

## Quickstart (Docker, Recommended)

1. Create local environment config:

```bash
cp .env.example .env
```

2. Add your OpenAI key in `.env`:
- `OPENAI_API_KEY` is sufficient for first-run extraction, ranking, prompt generation, and image generation.
- `GEMINI_API_KEY` is optional; when present, Gemini models remain the configured defaults with automatic OpenAI fallback.
- `XAI_API_KEY` remains optional for any xAI experiments.

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
