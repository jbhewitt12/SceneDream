# Pipeline Runs Route Boundary Refactor

## Overview
Extract ~126 lines of orchestration, validation, and config resolution logic from the `start_pipeline_run` route handler into a new `PipelineRunStartService`, keeping the route as a thin HTTP adapter.

## Problem Statement
The `start_pipeline_run` endpoint in `pipeline_runs.py` contains complex business logic: document resolution, extraction skip decision trees, config override assembly, and argument namespace construction. This violates the boundary rule that routes should only handle HTTP validation and delegate to services. The logic is untestable without spinning up a full HTTP context.

## Proposed Solution
Create a `PipelineRunStartService` that encapsulates all resolution and validation logic. The service raises domain-specific exceptions (not `HTTPException`), and the route catches and translates them to HTTP responses.

## Codebase Research Summary

### Current violation in `backend/app/api/routes/pipeline_runs.py`:
- **Lines 569-654** (~85 lines): Document resolution, extraction skip decision tree, config override assembly
- **Lines 634-654**: Argument namespace construction with `_build_run_namespace()`
- Route directly creates 4 repositories (`ArtStyleRepository`, `DocumentRepository`, `PipelineRunRepository`, `SceneExtractionRepository`)

### Helper functions already in the route file:
- `_source_path_exists()` (line 31) — checks if source document exists on disk
- `_resolve_default_scenes_per_run()` (line 45) — resolves default config
- `_build_run_namespace()` (line 58) — builds argparse Namespace for CLI
- `_execute_pipeline_run()` (line 93) — background task that runs the pipeline
- `_run_full_pipeline()` (line 127) — subprocess execution of CLI commands

### Reference service pattern (`SceneRankingService`):
- Constructor takes `Session`, creates repos
- Methods return domain objects
- Raises domain exceptions, not HTTP exceptions

## Key Decisions
- **Domain exceptions**: The service will raise custom exceptions (e.g., `DocumentNotFoundError`, `PipelineValidationError`) that the route translates to `HTTPException`. This keeps the service HTTP-agnostic.
- **Helper functions**: `_source_path_exists`, `_resolve_default_scenes_per_run`, and `_build_run_namespace` move into the service since they're business logic, not HTTP concerns.
- **Background task** (`_execute_pipeline_run`): Stays in the route file since it's the bridge between the HTTP layer and the async execution, but the service prepares all its inputs.

## Implementation Plan

### Phase 1: Define domain exceptions
**Goal**: Create exception types for the service to raise.

**Tasks**:
- Add `PipelineValidationError`, `DocumentNotFoundError`, and `SourceDocumentMissingError` exception classes in a new module `backend/app/services/pipeline/exceptions.py` (or in the service file itself if minimal)

**Verification**:
- [ ] Exception classes are importable

### Phase 2: Create PipelineRunStartService
**Goal**: Extract orchestration logic into a service.

**Tasks**:
- Create `backend/app/services/pipeline/pipeline_run_start_service.py`
- Constructor takes `session: Session`, creates `DocumentRepository`, `ArtStyleRepository`, `SceneExtractionRepository`, `PipelineRunRepository`
- Move `_source_path_exists()`, `_resolve_default_scenes_per_run()`, `_build_run_namespace()` into the service as private methods
- Create `resolve_pipeline_request(launch_request: PipelineRunStartRequest) -> PipelineRunResolution` that returns a dataclass/NamedTuple with resolved args, config overrides, and the created `PipelineRun` record
- Raise domain exceptions instead of `HTTPException`

**Verification**:
- [ ] Service encapsulates all resolution logic
- [ ] No `HTTPException` imports in the service
- [ ] Service follows constructor injection pattern

### Phase 3: Simplify the route handler
**Goal**: Route becomes a thin HTTP adapter.

**Tasks**:
- Update `start_pipeline_run()` in `backend/app/api/routes/pipeline_runs.py` to:
  1. Instantiate `PipelineRunStartService(session)`
  2. Call `service.resolve_pipeline_request(launch_request)`
  3. Catch domain exceptions and map to `HTTPException`
  4. Spawn background task with resolved params
- Remove helper functions that moved to the service
- Keep `_execute_pipeline_run` and `_run_full_pipeline` in the route (or move to a background tasks module)

**Verification**:
- [ ] Route handler is under 30 lines
- [ ] All business logic lives in the service

### Phase 4: Add tests
**Goal**: Unit tests for the new service.

**Tasks**:
- Create `backend/app/tests/services/test_pipeline_run_start_service.py`
- Test document resolution (found, not found, by slug, by ID)
- Test extraction skip decision tree (all branches)
- Test config override assembly
- Test domain exceptions are raised correctly
- Mock repository calls with monkeypatch

**Verification**:
- [ ] All decision branches covered
- [ ] `cd backend && uv run pytest` passes

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/pipeline/pipeline_run_start_service.py` | Create — new service |
| `backend/app/services/pipeline/__init__.py` | Create — package init |
| `backend/app/services/pipeline/exceptions.py` | Create — domain exceptions |
| `backend/app/api/routes/pipeline_runs.py` | Modify — simplify route handler |
| `backend/app/tests/services/test_pipeline_run_start_service.py` | Create — unit tests |

## Testing Strategy
- **Unit Tests**: Test all resolution/validation branches with monkeypatched repositories
- **Manual Verification**: Start a pipeline run via the API and confirm it behaves identically

## Acceptance Criteria
- [ ] `start_pipeline_run` route handler is under 30 lines of logic
- [ ] All orchestration/validation logic lives in `PipelineRunStartService`
- [ ] Service raises domain exceptions, not `HTTPException`
- [ ] Route catches domain exceptions and maps to HTTP responses
- [ ] Unit tests cover all decision branches
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
- [ ] Existing `backend/app/tests/api/routes/test_pipeline_runs.py` tests still pass
