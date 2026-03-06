# Stabilize OpenAPI Generation and Formatting

## Overview
Fix the OpenAPI generation flow so regenerated specs do not break frontend linting.

## Problem Statement
`scripts/generate-client.sh` writes minified JSON to `openapi.json` and copies it to `frontend/openapi.json`. Frontend lint checks include this file, causing `npm run lint:ci` failures on formatting alone.

## Proposed Solution
Make generated OpenAPI output deterministic and lint-compatible by default:
- emit pretty-printed JSON, and/or
- exclude generated spec artifacts from frontend lint checks.

## Codebase Research Summary

### Current generation path
- `scripts/generate-client.sh` uses:
  - `json.dumps(app.main.app.openapi())` (minified)
  - copy to `frontend/openapi.json`
  - format only `frontend/src/client` (not `frontend/openapi.json`)

### Current lint behavior
- `frontend` lint checks include `frontend/openapi.json`
- Minified one-line JSON fails format checks

## Key Decisions
- Prefer making generated artifacts pass checks without manual formatting steps.
- Keep generation one-command for contributors.
- Preserve existing generated client workflow.

## Implementation Plan

### Phase 1: Update generation output format
**Goal**: Ensure generated spec files are stable and readable.

**Tasks**:
- Update `scripts/generate-client.sh` to pretty-print JSON (`indent=2`, stable key order optional).
- Keep root `openapi.json` and `frontend/openapi.json` in sync.

**Verification**:
- [ ] Generated `frontend/openapi.json` is multi-line formatted JSON

### Phase 2: Align lint scope with generated artifacts
**Goal**: Prevent generated spec formatting from breaking contributor lint runs.

**Tasks**:
- Decide one approach:
  - include `frontend/openapi.json` in formatting flow, or
  - explicitly exclude `frontend/openapi.json` from Biome checks.
- Apply the chosen approach in lint configuration or scripts.

**Verification**:
- [ ] `npm run lint:ci` does not fail solely due to generated OpenAPI formatting

### Phase 3: Validate end-to-end workflow
**Goal**: Confirm generation + lint + client update run cleanly.

**Tasks**:
- Run `./scripts/generate-client.sh`
- Run `cd frontend && npm run lint:ci`
- Verify no unrelated file churn after repeated generation runs

**Verification**:
- [ ] Re-running generation produces stable output
- [ ] Lint passes after generation

## Files to Modify
| File | Action |
|------|--------|
| `scripts/generate-client.sh` | Modify |
| `frontend/biome.json` | Modify (if lint exclusion/config is chosen) |
| `frontend/openapi.json` | Regenerate |
| `openapi.json` | Regenerate |

## Testing Strategy
- `./scripts/generate-client.sh`
- `cd frontend && npm run lint:ci`
- Regenerate twice and confirm no unexpected diff churn

## Acceptance Criteria
- [ ] OpenAPI generation produces lint-compatible output by default
- [ ] `cd frontend && npm run lint:ci` passes after regeneration
- [ ] Client regeneration workflow remains one-command and deterministic

