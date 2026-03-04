# Contributing to SceneDream

Thanks for contributing to SceneDream. This guide explains how to propose changes, run checks locally, and open high-signal pull requests.

## Scope

SceneDream is a local-first pipeline for:
- document ingestion and parsing
- scene extraction and ranking
- prompt generation
- image generation orchestration
- dashboard and operator workflows

Contributions across backend, frontend, docs, and tooling are welcome.

## Before You Start

1. Search existing issues and discussions to avoid duplicate work.
2. For large changes, open an issue first to align on approach.
3. Keep changes focused and incremental.

## Development Setup

1. Start services:

```bash
docker compose watch
```

2. Backend local dev:

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

3. Frontend local dev:

```bash
cd frontend
npm install
npm run dev
```

## Required Checks

Run relevant checks before opening a PR.

Backend:

```bash
cd backend && uv run bash scripts/lint.sh
cd backend && uv run pytest
```

Frontend:

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

If your change affects API contracts, regenerate the client:

```bash
./scripts/generate-client.sh
```

## Testing Expectations

- Add or update tests for behavior changes.
- Mock external API calls in unit tests; do not call live provider services.
- Keep tests deterministic and isolated.

## Pull Request Guidelines

1. Use a clear title and description.
2. Link related issues (for example: `Closes #123`).
3. Describe:
   - what changed
   - why it changed
   - how it was tested
4. Include screenshots/GIFs for UI changes.
5. Keep PRs reviewable; prefer smaller PRs over large mixed changes.

## Commit Guidance

- Use descriptive commit messages.
- Keep commits logically grouped.
- Avoid unrelated refactors in feature/fix PRs.

## Reporting Security Issues

Do not open public issues for vulnerabilities. Follow the process in [SECURITY.md](SECURITY.md).

## Code of Conduct

By participating in this project, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
