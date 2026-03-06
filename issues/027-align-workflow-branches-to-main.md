# Align Workflow Branch Triggers to `main`

## Overview
Update GitHub Actions workflow branch filters from `master` to `main` so CI and automation run on the repository's active default branch.

## Problem Statement
The repository's active branch is `main`, but several workflows still trigger on `master`. This causes push-triggered CI checks and automation to silently not run during normal development, creating a false sense of release readiness.

## Proposed Solution
Retarget all affected workflow branch filters to `main`, then validate that expected jobs fire for push and pull request events.

## Codebase Research Summary

### Workflows currently targeting `master`
- `.github/workflows/frontend-ci.yml`
- `.github/workflows/lint-backend.yml`
- `.github/workflows/test-backend.yml`
- `.github/workflows/test-docker-compose.yml`
- `.github/workflows/playwright.yml`
- `.github/workflows/deploy-staging.yml`
- `.github/workflows/latest-changes.yml`

### Impact
- Core required checks in CONTRIBUTING (`Lint Backend`, `Test Backend`, `Frontend CI`) may not run on pushes to `main`.
- Non-critical automation is also misaligned and can remain stale.

## Key Decisions
- Update all branch filters to `main` in one pass for consistency.
- Keep existing `pull_request` triggers unchanged.
- Preserve path filters and draft-PR guards exactly as-is.

## Implementation Plan

### Phase 1: Retarget core CI workflows
**Goal**: Ensure required checks run on `main`.

**Tasks**:
- Update `branches` values from `master` to `main` in:
  - `frontend-ci.yml`
  - `lint-backend.yml`
  - `test-backend.yml`
  - `test-docker-compose.yml`

**Verification**:
- [ ] All four workflows reference `main` under push triggers
- [ ] No accidental changes to path filters

### Phase 2: Retarget non-core workflows
**Goal**: Keep automation behavior aligned with the default branch.

**Tasks**:
- Update `master` references in:
  - `playwright.yml`
  - `deploy-staging.yml`
  - `latest-changes.yml`

**Verification**:
- [ ] No remaining `master` branch filters in `.github/workflows/*.yml`

### Phase 3: Validate workflow behavior
**Goal**: Confirm checks execute as expected.

**Tasks**:
- Open a PR and confirm these jobs appear:
  - `Lint Backend`
  - `Test Backend`
  - `Frontend CI`
- Confirm path-scoped workflow skipping behavior is unchanged.

**Verification**:
- [ ] Required checks appear on new PRs
- [ ] Pushes to `main` trigger path-matching jobs

## Files to Modify
| File | Action |
|------|--------|
| `.github/workflows/frontend-ci.yml` | Modify |
| `.github/workflows/lint-backend.yml` | Modify |
| `.github/workflows/test-backend.yml` | Modify |
| `.github/workflows/test-docker-compose.yml` | Modify |
| `.github/workflows/playwright.yml` | Modify |
| `.github/workflows/deploy-staging.yml` | Modify |
| `.github/workflows/latest-changes.yml` | Modify |

## Testing Strategy
- **Validation in GitHub**: Open a PR touching backend and frontend paths and verify expected checks run.
- **Static verification**: `rg -n "master" .github/workflows`

## Acceptance Criteria
- [ ] No workflow branch filters target `master`
- [ ] Pushes to `main` trigger expected CI checks
- [ ] PR checks for backend/frontend paths run as documented

