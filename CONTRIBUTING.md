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

## Coding Standards

- Keep boundaries clean: API routes handle validation/HTTP, services hold business logic, repositories handle persistence only.
- New FastAPI endpoints must be `async` and non-blocking; move CPU-heavy work to background tasks or executors.
- Keep external side effects (LLM/image/file I/O) behind service adapters with retries, timeouts, and clear error handling.
- Preserve API and schema stability: prefer additive changes and keep backend/frontend contracts aligned.
- Add tests for every behavior change:
  - services -> `backend/app/tests/services/`
  - routes -> `backend/app/tests/api/routes/`
  - repositories -> `backend/app/tests/repositories/`
- Unit tests must mock external APIs with `monkeypatch`; do not call live LLM or image providers.
- Definition of done: code + tests + lint/type checks pass, and behavior changes are documented in the PR.

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
cd frontend && npm run lint:ci
cd frontend && npm run build
```

If your change affects API contracts, regenerate the client:

```bash
./scripts/generate-client.sh
```

## CI Gates (Lightweight Baseline)

Pull requests use a small set of CI checks intended to catch regressions without slowing iteration:
- **Lint Backend** (`.github/workflows/lint-backend.yml`) for backend-only changes.
- **Test Backend** (`.github/workflows/test-backend.yml`) for backend-only changes.
- **Frontend CI** (`.github/workflows/frontend-ci.yml`) for frontend/OpenAPI changes.

These workflows are path-scoped and skip draft pull requests to reduce unnecessary noise.

For branch protection/rulesets, keep required checks limited to this baseline:
- `Lint Backend`
- `Test Backend`
- `Frontend CI`

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

## Sequential Agent Queue (Issues 020-026)

Use this workflow when you want one issue per agent context, with one commit per issue.

1. Check queue state:

```bash
./scripts/issue_queue.sh status
```

2. Get the next pending issue:

```bash
./scripts/issue_queue.sh next
```

3. Generate a handoff prompt for a fresh agent context:

```bash
./scripts/issue_queue.sh prompt
```

4. In that agent context, implement only the shown issue, run required checks, stage files, then commit with:

```bash
./scripts/issue_queue.sh commit "<short summary>"
```

This creates a commit message in the required format: `issue(0NN): <summary>`.

5. Validate ordering (optional but recommended):

```bash
./scripts/issue_queue.sh verify
```

6. Start a new agent context and repeat from step 2 until all issues are complete.

## Reporting Security Issues

Do not open public issues for vulnerabilities. Follow the process in [SECURITY.md](SECURITY.md).

## Code of Conduct

By participating in this project, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
