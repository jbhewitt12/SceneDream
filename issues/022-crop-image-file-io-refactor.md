# Extract File I/O from crop_image Route

## Overview
Move direct file read/write operations out of the `crop_image` route handler in `generated_images.py` into a service method, keeping the route as a thin HTTP adapter.

## Problem Statement
The `crop_image` endpoint performs `await file.read()` and `file_path.write_bytes()` directly in the route handler (lines 974-982). This violates the boundary rule that external side effects (file I/O) should be behind service adapters. The file operations are untestable without HTTP context and lack the abstraction that would allow swapping storage backends.

## Proposed Solution
Add a `save_cropped_image(image_id, file_contents)` method to the existing `ImageGenerationService` (or a focused helper on the generated images route module), moving file path resolution, existence checks, and write operations behind a service interface.

## Codebase Research Summary

### Current violation in `backend/app/api/routes/generated_images.py`:
- **Lines 946-990** (`crop_image` endpoint):
  - Line 959: `repository = GeneratedImageRepository(session)` — route creates repo
  - Lines 963-966: `record = repository.get(image_id)` — route queries DB
  - Lines 967-972: `file_path = _resolve_image_file(record)` + existence check — business logic in route
  - Lines 974-976: `contents = await file.read()` + `file_path.write_bytes(contents)` — direct file I/O
  - Lines 977-986: Error handling and logging for file write

### Existing patterns:
- `ImageGenerationService` in `backend/app/services/image_generation/image_generation_service.py` already uses `loop.run_in_executor()` for file I/O (lines 723-744)
- `_resolve_image_file()` helper (line 437 in generated_images.py) resolves file paths from image records

### Related route helper:
- `_resolve_image_file(record)` (line 437) — used by both `stream_generated_image_file` and `crop_image`; this can move to the service

## Key Decisions
- **Extend ImageGenerationService** rather than creating a new service class, since it already handles image file operations.
- **Move `_resolve_image_file`** into the service as well, since it's used for file operations (not HTTP concerns).

## Implementation Plan

### Phase 1: Add `save_cropped_image` to ImageGenerationService
**Goal**: Service method handles file resolution and write.

**Tasks**:
- Add `save_cropped_image(self, image_id: UUID, file_contents: bytes) -> None` to `ImageGenerationService` in `backend/app/services/image_generation/image_generation_service.py`
- Method should: look up the image record via `self._image_repo.get()`, resolve the file path, validate the file exists, write the new contents using `run_in_executor` for non-blocking I/O
- Raise a domain exception (e.g., `ImageNotFoundError`, `ImageFileError`) on failures instead of `HTTPException`

**Verification**:
- [ ] Method exists on `ImageGenerationService`
- [ ] Uses `run_in_executor` for file write (matching existing pattern at lines 723-744)
- [ ] No HTTP concerns in the method

### Phase 2: Simplify the route handler
**Goal**: Route delegates to service.

**Tasks**:
- Update `crop_image()` in `backend/app/api/routes/generated_images.py` to:
  1. Read the uploaded file: `contents = await file.read()`
  2. Instantiate service: `service = ImageGenerationService(session)`
  3. Call `await service.save_cropped_image(image_id, contents)`
  4. Catch domain exceptions and map to `HTTPException`
- Remove `_resolve_image_file()` from the route if no other route methods still need it (check `stream_generated_image_file` — if it also uses this helper, move it to the service and update both callers)

**Verification**:
- [ ] Route handler has no `write_bytes()` calls
- [ ] Route handler has no file path resolution logic
- [ ] `stream_generated_image_file` still works

### Phase 3: Add tests
**Goal**: Unit test for the new service method.

**Tasks**:
- Add test for `save_cropped_image` in `backend/app/tests/services/test_image_generation_service.py`
- Mock the repository `get()` call and file system operations
- Test success path and error paths (image not found, file write failure)

**Verification**:
- [ ] Tests pass with `cd backend && uv run pytest`

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/image_generation/image_generation_service.py` | Modify — add `save_cropped_image` method |
| `backend/app/api/routes/generated_images.py` | Modify — simplify `crop_image` handler |
| `backend/app/tests/services/test_image_generation_service.py` | Modify — add test for new method |

## Testing Strategy
- **Unit Tests**: Mock repo and file system, test success and error paths
- **Manual Verification**: Upload a cropped image via the UI and confirm the file is saved correctly

## Acceptance Criteria
- [ ] No direct `file.read()` / `write_bytes()` in the route handler
- [ ] File I/O delegated to `ImageGenerationService.save_cropped_image()`
- [ ] Service uses `run_in_executor` for non-blocking file writes
- [ ] Unit tests for new method
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
