# Clean Up GitHub Template Leftovers

## Overview
Remove or retarget upstream template leftovers in `.github` so project metadata and automation reflect SceneDream ownership and workflow.

## Problem Statement
Several `.github` files still reference unrelated upstream values (`fastapi`, `tiangolo`, upstream project URL). This can confuse contributors and create non-functional automation.

## Proposed Solution
Audit `.github` metadata/workflows and either:
- retarget values to SceneDream-maintained equivalents, or
- remove workflows/features that are intentionally not used.

## Codebase Research Summary

### Identified leftovers
- `.github/FUNDING.yml` points to `tiangolo`
- `.github/workflows/add-to-project.yml` points to `https://github.com/orgs/fastapi/projects/2`
- `.github/workflows/issue-manager.yml` is gated by `github.repository_owner == 'fastapi'`
- deploy workflows include comments/conditions aimed at template behavior

## Key Decisions
- Keep only automation that is actively maintained for this repo.
- Prefer explicit disable/removal over dormant, confusing workflows.
- Preserve useful issue/PR templates and path-scoped CI.

## Implementation Plan

### Phase 1: Metadata cleanup
**Goal**: Ensure organization/user metadata is correct.

**Tasks**:
- Update or remove `FUNDING.yml` entry.
- Review `.github/ISSUE_TEMPLATE/config.yml` contact links for final canonical repo location.

**Verification**:
- [ ] No unrelated maintainer/org identifiers remain in `.github` metadata files

### Phase 2: Workflow cleanup
**Goal**: Remove non-functional automation and clarify intentional workflows.

**Tasks**:
- For `add-to-project.yml`, either retarget to SceneDream project board or remove workflow.
- For `issue-manager.yml`, either retarget to current owner context or remove workflow.
- Review deploy workflow comments/conditions to ensure they match current deployment strategy.

**Verification**:
- [ ] All remaining workflows have clear ownership and purpose
- [ ] No workflow references upstream template resources

### Phase 3: Contributor-facing validation
**Goal**: Ensure repo automations appear intentional and understandable.

**Tasks**:
- Confirm issue templates, PR template, and workflows shown in Actions tab are relevant.

**Verification**:
- [ ] Contributors can understand active automation from repository files alone

## Files to Modify
| File | Action |
|------|--------|
| `.github/FUNDING.yml` | Modify or delete |
| `.github/workflows/add-to-project.yml` | Modify or delete |
| `.github/workflows/issue-manager.yml` | Modify or delete |
| `.github/workflows/deploy-staging.yml` | Review/modify as needed |
| `.github/workflows/deploy-production.yml` | Review/modify as needed |
| `.github/ISSUE_TEMPLATE/config.yml` | Review/modify as needed |

## Testing Strategy
- **Static check**: `rg -n "fastapi|tiangolo" .github`
- **Manual check**: Review Actions tab for only intended workflows.

## Acceptance Criteria
- [ ] No stale upstream template identifiers remain in `.github`
- [ ] All remaining workflows are intentional and maintainable
- [ ] Contributor-facing metadata points to the correct SceneDream resources

