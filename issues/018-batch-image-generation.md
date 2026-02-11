# Batch Image Generation via OpenAI Batch API

## Overview
Add a new `BatchImageGenerationService` that generates images using the OpenAI Batch API (`/v1/images/generations`) instead of making synchronous per-image API calls. This cuts image generation costs by 50% with access to a separate pool of higher rate limits. Batch jobs are tracked in a new database table and a background scheduler ensures results are always retrieved even if the CLI times out.

## Problem Statement
- **Current limitation**: Each image is generated via a synchronous OpenAI API call, paying full price per image
- **User impact**: At scale (hundreds of scenes across multiple books), image generation costs add up significantly
- **Business value**: The OpenAI Batch API provides a 50% cost reduction on all image generation, with higher rate limits from a separate pool. Since the pipeline is already CLI-driven and batch-oriented, the asynchronous completion model is acceptable.

## Proposed Solution
- Create a new `BatchImageGenerationService` that reuses the existing task-building and result-saving logic but submits requests via the OpenAI Batch API
- Track batch jobs in a new `image_generation_batches` database table so results can be retrieved even if the CLI process exits
- Add a background scheduler job (following the existing `SocialPostingScheduler` pattern from `backend/app/services/social_posting/scheduler.py`) that periodically checks for pending batches and processes completed results
- CLI submits the batch, polls with a configurable timeout, and processes results if they arrive in time. If the timeout expires, the background job picks it up later.
- Add an `IMAGE_GENERATION_MODE` environment variable (`"batch"` or `"sync"`, defaulting to `"batch"`) to switch between the new batch service and the existing synchronous service
- CLI-only for now -- the REST API endpoint continues using the sync service
- Leave the existing synchronous `ImageGenerationService` fully intact

## Codebase Research Summary

### Existing Patterns
- **Service pattern**: `ImageGenerationService` in `backend/app/services/image_generation/image_generation_service.py` orchestrates all image generation with `_build_tasks()` for task planning and `_generate_single()` for per-image execution
- **Provider pattern**: `GptImageProvider` in `gpt_image_api.py` wraps OpenAI's `client.images.generate()` call with validation and quality mapping (`standard` -> `auto`, `hd` -> `high`)
- **Config pattern**: `ImageGenerationConfig` dataclass holds runtime config; `Settings` in `config.py` holds env vars
- **Idempotency**: `UniqueConstraint` on `(image_prompt_id, variant_index, provider, model, size, quality, style)` prevents duplicate images
- **CLI entry points**: `image_gen_cli.py` (full pipeline orchestrator) and `image_generation/main.py` (standalone image CLI)
- **Background scheduler**: `SocialPostingScheduler` in `backend/app/services/social_posting/scheduler.py` uses APScheduler with `AsyncIOScheduler` + `IntervalTrigger`, started from the FastAPI lifespan in `main.py`. This is the pattern to follow for the batch checker.
- **DB models**: All SQLModel tables live in `backend/models/`. Alembic migrations in `backend/app/alembic/versions/`.

### Files Affected
- `backend/app/services/image_generation/image_generation_service.py` -- reuse `_build_tasks()`, `compute_file_checksum()`, dataclasses
- `backend/app/services/image_generation/gpt_image_api.py` -- reference for quality mapping logic
- `backend/app/core/config.py` -- add `IMAGE_GENERATION_MODE` setting
- `backend/app/services/image_gen_cli.py` -- route to batch or sync service based on mode
- `backend/app/services/image_generation/main.py` -- route to batch or sync service based on mode
- `backend/app/main.py` -- start/stop batch checker scheduler in lifespan
- `backend/models/` -- new `image_generation_batch.py` model

### OpenAI Batch API Reference
- **Endpoint**: `POST /v1/batches` with `endpoint="/v1/images/generations"`
- **Input**: `.jsonl` file where each line has `custom_id`, `method`, `url`, `body`
- **Body**: Same params as sync API (`model`, `prompt`, `size`, `quality`, `output_format`)
- **Output**: `.jsonl` file with `custom_id`, `response.body.data[0].b64_json`
- **SDK**: `client.files.create()`, `client.batches.create()`, `client.batches.retrieve()`, `client.files.content()`
- **Limits**: 50,000 requests per file, 200 MB file size, 24h completion window
- **Statuses**: `validating` -> `in_progress` -> `completed` | `failed` | `expired` | `cancelled`

## Key Decisions
- **Architecture**: New standalone `BatchImageGenerationService` class, not integrated into existing service
- **DB tracking**: New `image_generation_batches` table tracks each batch job with its OpenAI batch ID, status, task mapping (JSON), and generation params. One batch -> many generated images.
- **Result retrieval**: Two mechanisms -- (1) CLI polls with a configurable timeout (`--poll-timeout`, default 60 min), (2) background scheduler checks every 5 min for any incomplete batches
- **Background job**: FastAPI startup task using the same APScheduler pattern as `SocialPostingScheduler`
- **Config**: `IMAGE_GENERATION_MODE` env var with values `"batch"` or `"sync"`, defaulting to `"batch"`
- **Scope**: CLI-only for now -- REST API endpoint keeps using sync service
- **Provider**: Hardcoded to GPT Image models only (batch endpoint supports `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`)

## Implementation Plan

### Phase 1: Database Model and Migration

**Goal**: Create the `image_generation_batches` table to track batch jobs.

**Tasks**:

1. Create `backend/models/image_generation_batch.py` with `ImageGenerationBatch` SQLModel:
   - `id`: UUID primary key
   - `openai_batch_id`: str (the ID returned by `client.batches.create()`, indexed)
   - `openai_input_file_id`: str (uploaded `.jsonl` file ID)
   - `openai_output_file_id`: str | None (populated when batch completes)
   - `openai_error_file_id`: str | None (populated if batch has errors)
   - `status`: str (one of: `submitted`, `validating`, `in_progress`, `completed`, `failed`, `expired`, `cancelled`, `processed`). `processed` means we've downloaded and saved all results.
   - `task_mapping`: JSON column -- list of dicts, each mapping `custom_id` to the data needed to save the result: `image_prompt_id`, `scene_extraction_id`, `variant_index`, `book_slug`, `chapter_number`, `scene_number`, `storage_path`, `file_name`, `aspect_ratio`
   - `provider`: str (e.g., `openai_gpt_image`)
   - `model`: str (e.g., `gpt-image-1.5`)
   - `quality`: str
   - `style`: str
   - `size`: str
   - `total_requests`: int
   - `completed_requests`: int (updated when processing results)
   - `failed_requests`: int
   - `book_slug`: str | None (for context/filtering)
   - `error`: str | None (batch-level error message)
   - `created_at`: datetime
   - `updated_at`: datetime
   - `completed_at`: datetime | None

2. Add the model import to `backend/models/__init__.py`

3. Generate Alembic migration: `cd backend && uv run alembic revision --autogenerate -m "add image_generation_batches table"`

4. Run migration: `cd backend && uv run alembic upgrade head`

**Verification**:
- [ ] `image_generation_batches` table exists in the database
- [ ] Migration runs cleanly
- [ ] Lint passes

---

### Phase 2: Batch Repository

**Goal**: Create a repository for CRUD operations on `ImageGenerationBatch`.

**Tasks**:

1. Create `backend/app/repositories/image_generation_batch.py` with `ImageGenerationBatchRepository`:
   - `create(data, commit, refresh) -> ImageGenerationBatch`
   - `get(batch_id: UUID) -> ImageGenerationBatch | None`
   - `get_by_openai_batch_id(openai_batch_id: str) -> ImageGenerationBatch | None`
   - `list_pending() -> list[ImageGenerationBatch]` -- return batches with status in (`submitted`, `validating`, `in_progress`) for the background checker
   - `update_status(batch_id: UUID, status: str, **kwargs) -> ImageGenerationBatch | None` -- update status and optional fields like `openai_output_file_id`, `completed_at`, `error`, `completed_requests`, `failed_requests`

2. Add to `backend/app/repositories/__init__.py`

**Verification**:
- [ ] Repository methods work against the database
- [ ] Lint passes

---

### Phase 3: Configuration

**Goal**: Add the `IMAGE_GENERATION_MODE` setting.

**Tasks**:

1. Add `IMAGE_GENERATION_MODE` setting to `backend/app/core/config.py`:
   - Type: `str`, default: `"batch"`
   - Accepted values: `"batch"` or `"sync"`

**Verification**:
- [ ] `settings.IMAGE_GENERATION_MODE` loads from env and defaults to `"batch"`
- [ ] Lint passes

---

### Phase 4: Batch Service Core

**Goal**: Create `BatchImageGenerationService` that builds `.jsonl` input, submits batches, polls, and processes results.

**Tasks**:

1. Create `backend/app/services/image_generation/batch_image_generation_service.py`:
   - Constructor accepts same args as `ImageGenerationService`: `session`, `config` (optional `ImageGenerationConfig`), `api_key` (optional)
   - Instantiate repos: `GeneratedImageRepository`, `ImagePromptRepository`, `SceneExtractionRepository`, `SceneRankingRepository`, `ImageGenerationBatchRepository`
   - Instantiate OpenAI client: `OpenAI(api_key=self._api_key)`

2. Implement `generate_for_selection()` with the same signature as `ImageGenerationService.generate_for_selection()`:
   - Reuse `_fetch_prompts()` and `_build_tasks()` logic (either call them from the existing service or extract to shared functions). The simplest approach: instantiate `ImageGenerationService` internally just to call its prompt-fetching and task-building methods, or copy the logic. Prefer extracting `_fetch_prompts()` and `_build_tasks()` into module-level functions in `image_generation_service.py` that both services can call.
   - After building tasks: call `_build_jsonl()`, `_submit_batch()`, create DB record, then `_poll_batch()` with timeout, then `_process_results()` if completed

3. Implement `_build_jsonl(tasks, config) -> str`:
   - For each task, create a JSON line: `{"custom_id": "<prompt_id>_v<variant_index>", "method": "POST", "url": "/v1/images/generations", "body": {"model": config.model, "prompt": task.prompt.prompt_text, "size": task.size, "quality": <mapped_quality>, "output_format": "png"}}`
   - Apply the same quality mapping as `GptImageProvider`: `standard` -> `auto`, `hd` -> `high`
   - Return the `.jsonl` content as a string

4. Implement `_submit_batch(jsonl_content, tasks, config) -> ImageGenerationBatch`:
   - Upload `.jsonl` via `client.files.create(file=BytesIO(jsonl_content.encode()), purpose="batch")`
   - Create batch via `client.batches.create(input_file_id=..., endpoint="/v1/images/generations", completion_window="24h")`
   - Build `task_mapping` list from tasks (each entry: `custom_id`, `image_prompt_id`, `scene_extraction_id`, `variant_index`, `book_slug`, `chapter_number`, `scene_number`, `storage_path`, `file_name`, `aspect_ratio`)
   - Create `ImageGenerationBatch` DB record with status `submitted`
   - Return the batch record

5. Implement `_poll_batch(batch: ImageGenerationBatch, timeout_seconds: int = 3600, poll_interval: int = 30) -> ImageGenerationBatch`:
   - Poll `client.batches.retrieve(batch.openai_batch_id)` every `poll_interval` seconds
   - Update batch status in DB on each poll
   - Log progress (OpenAI batch object has `request_counts.completed`, `request_counts.failed`, `request_counts.total`)
   - If terminal status (`completed`, `failed`, `expired`, `cancelled`): update DB and return
   - If timeout reached: log warning with batch ID, return batch (status still `in_progress` -- background job will pick it up)

6. Implement `process_completed_batch(batch: ImageGenerationBatch) -> list[GenerationResult]`:
   - **Make this a public method** so the background scheduler can also call it
   - Download output `.jsonl` via `client.files.content(batch.openai_output_file_id)`
   - Parse each line: extract `custom_id` and `response.body.data[0].b64_json`
   - Match `custom_id` back to task mapping from `batch.task_mapping`
   - For each result: decode base64, save image to disk at `storage_path/file_name`, compute SHA256 checksum, create `GeneratedImage` DB record using `GeneratedImageRepository.create()`
   - If `openai_error_file_id` exists: download, parse, and log errors. Create failed `GeneratedImage` records.
   - Update batch status to `processed`, set `completed_requests` and `failed_requests` counts
   - Return list of `GenerationResult`

**Verification**:
- [ ] `BatchImageGenerationService` class exists with `generate_for_selection()` method
- [ ] `.jsonl` builder produces valid batch input format
- [ ] `process_completed_batch()` is public for scheduler use
- [ ] Lint passes

---

### Phase 5: Background Batch Checker

**Goal**: Add a background scheduler job that checks for pending batches and processes completed results.

**Tasks**:

1. Create `backend/app/services/image_generation/batch_scheduler.py` following the pattern in `backend/app/services/social_posting/scheduler.py`:
   - Create `BatchImageScheduler` class with `start()`, `stop()`, `_check_batches_job()` methods
   - Use `AsyncIOScheduler` with `IntervalTrigger(minutes=5)` -- check every 5 minutes
   - `_check_batches_job()`:
     - Open a DB session
     - Query `ImageGenerationBatchRepository.list_pending()` for batches with status in (`submitted`, `validating`, `in_progress`)
     - For each pending batch: call `client.batches.retrieve()` to get current status
     - If status changed: update in DB
     - If `completed`: call `BatchImageGenerationService.process_completed_batch()` to download and save results
     - If `failed`/`expired`/`cancelled`: update status and log error
   - Add module-level `start_batch_scheduler()` and `stop_batch_scheduler()` functions
   - Add misfire handling like the social posting scheduler

2. Update `backend/app/main.py` lifespan:
   - Import `start_batch_scheduler`, `stop_batch_scheduler` from the new module
   - Call `start_batch_scheduler()` on startup and `stop_batch_scheduler()` on shutdown
   - Place alongside existing `start_scheduler()` / `stop_scheduler()` calls

**Verification**:
- [ ] Scheduler starts with the FastAPI app
- [ ] Pending batches are checked every 5 minutes
- [ ] Completed batches have their results downloaded and saved
- [ ] Lint passes

---

### Phase 6: CLI Integration

**Goal**: Wire both CLI entry points to use the batch service when `IMAGE_GENERATION_MODE=batch`.

**Tasks**:

1. Update `backend/app/services/image_generation/main.py`:
   - Import `BatchImageGenerationService` and `settings.IMAGE_GENERATION_MODE`
   - Add `--mode` CLI arg with choices `["batch", "sync"]` defaulting to `settings.IMAGE_GENERATION_MODE`
   - Add `--poll-timeout` CLI arg (default: 3600 seconds / 60 minutes)
   - Add `--poll-interval` CLI arg (default: 30 seconds)
   - In `_handle_generate()`: if mode is `"batch"`, use `BatchImageGenerationService`; if `"sync"`, use existing `ImageGenerationService`
   - Both services have the same `generate_for_selection()` signature so the rest of the code stays the same

2. Update `backend/app/services/image_gen_cli.py`:
   - In the image generation step (wherever `ImageGenerationService` is created), add the same mode-based routing
   - Add `--mode` arg to the `images` subcommand and the `run` subcommand
   - Default to `settings.IMAGE_GENERATION_MODE`

**Verification**:
- [ ] `uv run python -m app.services.image_generation.main --book <slug> --top-scenes 1 --dry-run --mode batch` works
- [ ] `uv run python -m app.services.image_generation.main --book <slug> --top-scenes 1 --dry-run --mode sync` works
- [ ] Default mode comes from `IMAGE_GENERATION_MODE` env var
- [ ] Lint passes

---

### Phase 7: Testing

**Goal**: Add unit tests and do a live smoke test.

**Tasks**:

1. Create `backend/app/tests/services/test_batch_image_generation_service.py`:
   - Test `_build_jsonl()` produces valid `.jsonl` with correct `custom_id`, `method`, `url`, `body` structure
   - Test quality mapping (`standard` -> `auto`, `hd` -> `high`) is applied in the batch request body
   - Test `process_completed_batch()` correctly matches `custom_id` back to task mapping and creates DB records
   - Test error handling when batch status is `failed` or `expired`
   - Test poll timeout behavior (returns batch without processing when timeout reached)
   - Mock the OpenAI client (`client.files.create`, `client.batches.create`, `client.batches.retrieve`, `client.files.content`)

2. Create `backend/app/tests/services/test_batch_scheduler.py`:
   - Test `_check_batches_job()` processes completed batches
   - Test that batches still in progress are left alone
   - Mock OpenAI client and DB

3. Manual smoke test:
   - Set `IMAGE_GENERATION_MODE=batch` in `.env`
   - Run `cd backend && uv run python -m app.services.image_generation.main --book <slug> --top-scenes 1` with a real API key
   - Verify batch is submitted, tracked in DB, polled, and results are saved to disk and database
   - Verify `image_generation_batches` row shows status `processed`

**Verification**:
- [ ] All tests pass (`cd backend && uv run pytest`)
- [ ] Lint passes (`uv run bash scripts/lint.sh`)
- [ ] Live smoke test generates an image via batch mode

## Files to Modify
| File | Action |
|------|--------|
| `backend/models/image_generation_batch.py` | Create -- new SQLModel table |
| `backend/models/__init__.py` | Modify -- add import |
| `backend/app/alembic/versions/<hash>_add_image_generation_batches.py` | Create -- Alembic migration (autogenerated) |
| `backend/app/repositories/image_generation_batch.py` | Create -- batch repository |
| `backend/app/repositories/__init__.py` | Modify -- add import |
| `backend/app/core/config.py` | Modify -- add `IMAGE_GENERATION_MODE` setting |
| `backend/app/services/image_generation/batch_image_generation_service.py` | Create -- new batch service |
| `backend/app/services/image_generation/batch_scheduler.py` | Create -- background batch checker |
| `backend/app/main.py` | Modify -- start/stop batch scheduler in lifespan |
| `backend/app/services/image_generation/main.py` | Modify -- add mode routing and batch CLI args |
| `backend/app/services/image_gen_cli.py` | Modify -- add mode routing |
| `backend/app/tests/services/test_batch_image_generation_service.py` | Create -- unit tests |
| `backend/app/tests/services/test_batch_scheduler.py` | Create -- scheduler tests |

## Testing Strategy
- **Unit Tests**: Test `.jsonl` building, quality mapping, result processing, poll timeout, scheduler logic -- all with mocked OpenAI client
- **Manual Verification**: Submit a real batch with 1 image, verify end-to-end flow including DB tracking

## Acceptance Criteria
- [ ] `BatchImageGenerationService` generates images via the OpenAI Batch API
- [ ] Batch jobs are tracked in the `image_generation_batches` table
- [ ] Background scheduler checks for pending batches every 5 minutes and processes completed results
- [ ] CLI polls with configurable timeout; if timeout expires, background job picks up the batch
- [ ] `IMAGE_GENERATION_MODE=batch` (default) uses batch service in CLI
- [ ] `IMAGE_GENERATION_MODE=sync` falls back to existing synchronous service
- [ ] CLI `--mode` flag overrides the env var
- [ ] Generated images are saved to the same file paths and DB records as the sync service
- [ ] Idempotency checks work the same as the sync service
- [ ] All tests pass
- [ ] Lint passes
