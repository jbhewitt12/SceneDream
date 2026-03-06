# Scene Extraction Service Boundary Refactor

## Overview
Refactor `SceneExtractor` to follow the established service pattern: receive a `Session` via constructor, delegate all persistence to `SceneExtractionRepository`, and eliminate direct session/transaction management inside the service.

## Problem Statement
`SceneExtractor` violates the clean boundary rule by creating `Session` objects directly (`Session(engine)`), instantiating repositories ad-hoc, and managing transactions (commit/rollback) inside business logic methods. This makes the service hard to test, breaks the repository abstraction, and diverges from the pattern used by `SceneRankingService`, `ImageGenerationService`, and `ImagePromptGenerationService`.

## Proposed Solution
Refactor `SceneExtractor` to accept a `Session` in its constructor (matching the `SceneRankingService` pattern), instantiate `SceneExtractionRepository` once in `__init__`, and delegate all create/update/transaction logic to the repository layer.

## Codebase Research Summary

### Current violations in `backend/app/services/scene_extraction/scene_extraction.py`:
- **Lines 539-544** (`_existing_processed_chunks`): Creates `Session(engine)` and `SceneExtractionRepository` inline
- **Lines 584-748** (`_persist_chapter_scenes`): 165 lines of persistence logic with manual `session.commit()` / `session.rollback()`
- **Lines 925-1050** (`_cmd_refine_pending`): CLI command creates sessions and manages persistence directly

### Reference pattern (`SceneRankingService.__init__` lines 234-240):
- Takes `session: Session` in constructor
- Stores `self._session = session`
- Creates repos once: `self._scene_repo = SceneExtractionRepository(session)`

### Existing repository methods that can be leveraged:
- `SceneExtractionRepository.create()` with `commit`/`refresh` flags
- `SceneExtractionRepository.update()` with `commit`/`refresh` flags
- `SceneExtractionRepository.get_by_identity()` for book/chapter/scene lookup
- `SceneExtractionRepository.upsert_by_identity()` for combined create/update
- `SceneExtractionRepository.chunk_indexes_for_chapter()` for existing chunk queries

## Key Decisions
- **Full constructor injection**: `SceneExtractor` will receive `Session` in its constructor like other services, not just extract a persistence helper.
- **CLI entrypoints** (`main.py`) will create the Session and pass it to the constructor.
- **Transaction management** stays outside the service — the caller or a unit-of-work pattern manages commit/rollback.

## Implementation Plan

### Phase 1: Refactor SceneExtractor constructor
**Goal**: Align constructor with the established service pattern.

**Tasks**:
- Add `session: Session` parameter to `SceneExtractor.__init__()` in `backend/app/services/scene_extraction/scene_extraction.py`
- Store `self._session` and create `self._scene_repo = SceneExtractionRepository(session)` in constructor
- Remove `engine` import/usage for session creation

**Verification**:
- [ ] Constructor matches `SceneRankingService` pattern
- [ ] No `Session(engine)` calls remain in the class

### Phase 2: Extract persistence from `_persist_chapter_scenes`
**Goal**: Replace 165 lines of inline persistence with repository delegation.

**Tasks**:
- Refactor `_persist_chapter_scenes()` to use `self._scene_repo` instead of creating sessions
- Leverage `SceneExtractionRepository.upsert_by_identity()` to replace the manual get/create/update pattern
- Move transaction boundary (commit) to the caller or use the repository's `commit` flag
- Keep business logic (model resolution, payload construction, refinement metadata) in the service but delegate persistence calls

**Verification**:
- [ ] No `Session(engine)` in `_persist_chapter_scenes`
- [ ] No manual `session.commit()` or `session.rollback()` in the method
- [ ] All persistence goes through `self._scene_repo`

### Phase 3: Refactor `_existing_processed_chunks`
**Goal**: Eliminate inline session creation in chunk lookup.

**Tasks**:
- Replace `Session(engine)` block in `_existing_processed_chunks()` (lines 539-544) with `self._scene_repo.chunk_indexes_for_chapter()`

**Verification**:
- [ ] Method uses `self._scene_repo` directly

### Phase 4: Update CLI entrypoints
**Goal**: CLI commands create Session and pass to SceneExtractor.

**Tasks**:
- Update `backend/app/services/scene_extraction/main.py` to create Session and pass to `SceneExtractor(session=session, ...)`
- Update `_cmd_refine_pending` to use the service's repository instead of creating sessions
- Update any other callers (check with grep for `SceneExtractor(`)

**Verification**:
- [ ] All `SceneExtractor` instantiation sites pass a `Session`
- [ ] CLI commands work end-to-end

### Phase 5: Add tests
**Goal**: Unit tests for the refactored service.

**Tasks**:
- Create `backend/app/tests/services/test_scene_extraction_service.py`
- Test `_persist_chapter_scenes` with monkeypatched repository methods
- Test `_existing_processed_chunks` with monkeypatched repository
- Use `scene_factory` from conftest for test data

**Verification**:
- [ ] Tests pass with `cd backend && uv run pytest`
- [ ] External calls are mocked

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/scene_extraction/scene_extraction.py` | Modify — refactor constructor, persistence methods |
| `backend/app/services/scene_extraction/main.py` | Modify — pass Session to SceneExtractor |
| `backend/app/tests/services/test_scene_extraction_service.py` | Create — unit tests |

## Testing Strategy
- **Unit Tests**: Test persistence delegation with monkeypatched `SceneExtractionRepository` methods
- **Manual Verification**: Run `uv run python -m app.services.scene_extraction.main ...` against a test book

## Acceptance Criteria
- [ ] `SceneExtractor` receives `Session` in constructor
- [ ] No `Session(engine)` calls inside `SceneExtractor` methods
- [ ] No manual `session.commit()` / `session.rollback()` in the service
- [ ] All persistence delegated to `SceneExtractionRepository`
- [ ] Unit tests pass
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
