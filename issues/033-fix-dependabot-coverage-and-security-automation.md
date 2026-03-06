# Fix Dependabot Coverage and Security Automation

## Overview
Correct dependency automation configuration for the repository layout and add baseline secret-scanning automation for public repository hygiene.

## Problem Statement
Dependabot is configured with `pip` at repository root (`directory: /`), while Python dependencies live in `backend/pyproject.toml`. Frontend npm dependency updates are also not configured. This creates blind spots in dependency maintenance for a public repo.

## Proposed Solution
Update Dependabot to match actual package locations and add a lightweight secret scan workflow in CI for pull requests.

## Codebase Research Summary

### Current Dependabot config
- `.github/dependabot.yml` currently has:
  - `github-actions` at `/`
  - `pip` at `/` (likely incorrect for this project layout)
- Frontend dependencies exist in `frontend/package.json`
- Backend dependencies exist in `backend/pyproject.toml`

## Key Decisions
- Configure ecosystems by actual directory boundaries:
  - Python (`pip`) in `/backend`
  - npm in `/frontend`
  - GitHub Actions in `/`
- Add non-blocking secret scanning first, then consider making it required.

## Implementation Plan

### Phase 1: Fix Dependabot directory scopes
**Goal**: Ensure dependency update PRs target real dependency files.

**Tasks**:
- Update `pip` entry to `directory: /backend`
- Add `npm` entry for `directory: /frontend`
- Keep `github-actions` entry at `/`

**Verification**:
- [ ] Dependabot detects backend Python dependencies
- [ ] Dependabot detects frontend npm dependencies

### Phase 2: Add baseline secret scanning workflow
**Goal**: Catch accidental secret commits early.

**Tasks**:
- Add a GitHub Actions workflow for secret scanning on pull requests.
- Choose and configure a lightweight scanner compatible with repository policies.

**Verification**:
- [ ] Secret scan job appears on PRs
- [ ] Scanner runs against tracked content and diffs

### Phase 3: Document and integrate with contribution flow
**Goal**: Make automation visible to contributors.

**Tasks**:
- Update `CONTRIBUTING.md` CI section to mention dependency/security automation.

**Verification**:
- [ ] Contributor docs reflect active automation checks

## Files to Modify
| File | Action |
|------|--------|
| `.github/dependabot.yml` | Modify |
| `.github/workflows/*secret-scan*.yml` | Create |
| `CONTRIBUTING.md` | Modify |

## Testing Strategy
- Validate Dependabot config syntax
- Open a test PR and confirm secret scan workflow runs
- Confirm no regressions in existing CI workflow behavior

## Acceptance Criteria
- [ ] Dependabot tracks backend and frontend dependencies correctly
- [ ] Secret scanning runs automatically on pull requests
- [ ] CONTRIBUTING docs reflect dependency/security automation

