# Restore Backend Lint Baseline

## Overview
Fix backend type and lint failures so `cd backend && uv run bash scripts/lint.sh` passes on a clean checkout.

## Problem Statement
Current backend linting fails with multiple mypy errors, primarily in `document_dashboard_service.py`, plus additional issues in repositories and service modules. This blocks CI reliability and raises contributor friction.

## Proposed Solution
Address the reported type errors directly, minimize `type: ignore` usage, and align SQLModel query typing with mypy expectations.

## Codebase Research Summary

### Current lint command
- `backend/scripts/lint.sh` runs:
  - `mypy app`
  - `ruff check app`
  - `ruff format app --check`

### Current failing areas
- `backend/app/services/document_dashboard_service.py` (majority of mypy errors)
- `backend/app/repositories/generated_image.py` (`unused-ignore`)
- `backend/app/services/image_cleanup/main.py` (missing type params)
- `backend/app/services/scene_ranking/scene_ranking_service.py` (`no-any-return`)
- `backend/app/services/scene_extraction/scene_refinement_tester.py` (constructor arg mismatch)

## Key Decisions
- Prefer proper typing fixes over broad new mypy overrides.
- Keep repository/service boundaries unchanged; this is a baseline-quality issue.
- Treat `mypy` clean state as required for open-source readiness.

## Implementation Plan

### Phase 1: Fix `document_dashboard_service.py` typing
**Goal**: Eliminate SQLModel/mypy type mismatches in dashboard aggregation queries.

**Tasks**:
- Correct SQLAlchemy expressions that are currently inferred as plain Python values.
- Ensure `count()`, `join()`, `group_by()`, and `is_`/`is_not` use typed SQL expressions.
- Fix ordering expressions (`.desc()`) to operate on SQL columns, not Python `datetime`.

**Verification**:
- [ ] No mypy errors remain in `document_dashboard_service.py`

### Phase 2: Fix remaining backend typing/lint issues
**Goal**: Clear residual mypy/ruff failures outside dashboard service.

**Tasks**:
- Remove unused `type: ignore` in `generated_image.py`
- Add missing generic type parameters in `image_cleanup/main.py`
- Ensure explicit return typing in `scene_ranking_service.py`
- Update `scene_refinement_tester.py` constructor call arguments to current `SceneRefiner` signature

**Verification**:
- [ ] No mypy or ruff failures in affected files

### Phase 3: Validate complete lint pipeline
**Goal**: Restore green backend lint baseline.

**Tasks**:
- Run `cd backend && uv run bash scripts/lint.sh`
- Run `cd backend && uv run pytest` for regression safety

**Verification**:
- [ ] Lint script passes end-to-end
- [ ] Tests continue to pass

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/document_dashboard_service.py` | Modify |
| `backend/app/repositories/generated_image.py` | Modify |
| `backend/app/services/image_cleanup/main.py` | Modify |
| `backend/app/services/scene_ranking/scene_ranking_service.py` | Modify |
| `backend/app/services/scene_extraction/scene_refinement_tester.py` | Modify |

## Testing Strategy
- **Primary**: `cd backend && uv run bash scripts/lint.sh`
- **Regression**: `cd backend && uv run pytest`

## Acceptance Criteria
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] No new mypy overrides introduced without justification
- [ ] `cd backend && uv run pytest` passes

