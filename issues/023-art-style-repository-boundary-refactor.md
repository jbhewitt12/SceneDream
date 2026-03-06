# Move Business Logic from ArtStyleRepository to Service

## Overview
Move the `list_for_sampling()` method's categorization logic (splitting styles into recommended vs. other) out of `ArtStyleRepository` and into a service, keeping the repository as a pure persistence layer.

## Problem Statement
`ArtStyleRepository.list_for_sampling()` (lines 43-47 in `art_style.py`) transforms data by splitting active styles into "recommended" and "other" lists. This is business logic — repositories should return raw entities, and services should apply business rules and transformations. While the method is small, it sets a precedent that erodes the boundary convention.

## Proposed Solution
Create an `ArtStyleService` with a `get_sampling_distribution()` method that calls `ArtStyleRepository.list_active()` and applies the categorization. Remove `list_for_sampling()` from the repository. Update all callers.

## Codebase Research Summary

### Current violation in `backend/app/repositories/art_style.py`:
- **Lines 43-47** (`list_for_sampling`):
  ```python
  def list_for_sampling(self) -> tuple[list[str], list[str]]:
      styles = self.list_active()
      recommended = [style.display_name for style in styles if style.is_recommended]
      other = [style.display_name for style in styles if not style.is_recommended]
      return recommended, other
  ```

### Existing repository methods:
- `list_active()` — returns all active `ArtStyle` records ordered by display_name
- `list_all()` — returns all records
- `get()`, `create()`, `update()` — standard CRUD

### Callers of `list_for_sampling()`:
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` — uses the recommended/other split for prompt variant generation
- Potentially the settings route or other services (need to grep to confirm)

## Key Decisions
- **New service class**: Create `ArtStyleService` rather than inlining the logic in `ImagePromptGenerationService`, since style sampling may be used by multiple consumers.
- **Keep it simple**: The service is small but maintains the architectural boundary.

## Implementation Plan

### Phase 1: Create ArtStyleService
**Goal**: Service encapsulates the categorization logic.

**Tasks**:
- Create `backend/app/services/art_style/art_style_service.py`
- Create `backend/app/services/art_style/__init__.py`
- Constructor takes `session: Session`, creates `self._art_style_repo = ArtStyleRepository(session)`
- Add `get_sampling_distribution() -> tuple[list[str], list[str]]` method that calls `self._art_style_repo.list_active()` and applies the recommended/other split

**Verification**:
- [ ] Service follows the constructor injection pattern
- [ ] Method returns the same tuple[list[str], list[str]] as the old repository method

### Phase 2: Update callers
**Goal**: All consumers use the new service instead of the repository method.

**Tasks**:
- Grep for `list_for_sampling` across the codebase to find all callers
- Update `ImagePromptGenerationService` to use `ArtStyleService.get_sampling_distribution()` instead of `ArtStyleRepository.list_for_sampling()`
- Update any other callers found

**Verification**:
- [ ] No code references `list_for_sampling` except the repository (which we'll remove)

### Phase 3: Remove repository method
**Goal**: Clean up the repository.

**Tasks**:
- Remove `list_for_sampling()` from `backend/app/repositories/art_style.py`

**Verification**:
- [ ] Repository only has persistence methods (`list_active`, `list_all`, `get`, `create`, `update`)

### Phase 4: Add tests
**Goal**: Unit test for the new service.

**Tasks**:
- Create `backend/app/tests/services/test_art_style_service.py`
- Test `get_sampling_distribution()` with mocked repository returning a mix of recommended and non-recommended styles
- Verify the split is correct

**Verification**:
- [ ] Tests pass with `cd backend && uv run pytest`

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/art_style/art_style_service.py` | Create — new service |
| `backend/app/services/art_style/__init__.py` | Create — package init |
| `backend/app/repositories/art_style.py` | Modify — remove `list_for_sampling()` |
| `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` | Modify — use `ArtStyleService` |
| `backend/app/tests/services/test_art_style_service.py` | Create — unit tests |

## Testing Strategy
- **Unit Tests**: Mock `ArtStyleRepository.list_active()` to return known styles, verify the split
- **Manual Verification**: Run prompt generation and confirm art style sampling still works

## Acceptance Criteria
- [ ] `list_for_sampling()` removed from `ArtStyleRepository`
- [ ] `ArtStyleService.get_sampling_distribution()` encapsulates the logic
- [ ] All callers updated to use the service
- [ ] Unit tests pass
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
- [ ] Existing tests in `backend/app/tests/repositories/test_settings_repositories.py` still pass
