# Restore Frontend Build and Typecheck Baseline

## Overview
Fix frontend TypeScript and API usage errors so `cd frontend && npm run build` and `cd frontend && npm run lint:ci` pass consistently.

## Problem Statement
Frontend build currently fails with numerous TypeScript errors across generated images and prompt gallery flows. Many failures indicate API mismatch after library upgrades (Chakra UI, TanStack Query, hooks API shape changes), which blocks external contributors from getting a green baseline.

## Proposed Solution
Apply targeted compatibility fixes across affected components/routes and re-establish a clean frontend quality baseline.

## Codebase Research Summary

### Observed error classes
- Chakra prop/API mismatches (`noOfLines`, `spacing`, `leftIcon`, `rightIcon`, `isLoading`)
- Hook/API changes (`useClipboard` field names)
- Query API mismatch (`keepPreviousData`)
- Promise callback signature mismatches (`Promise<Response>` vs `Promise<void>`)
- Unused imports/parameters and implicit `any`

### Primary failure hotspots
- `frontend/src/components/GeneratedImages/*`
- `frontend/src/components/Prompts/*`
- `frontend/src/routes/_layout/generated-images.tsx`
- `frontend/src/routes/_layout/prompt-gallery.tsx`
- `frontend/src/routes/_layout/scene-prompts.$sceneId.tsx`

## Key Decisions
- Keep changes scoped to compatibility fixes, not UX redesign.
- Align with currently pinned package versions in `frontend/package.json`.
- Favor explicit typing and adapter helpers where API response types differ from UI callback expectations.

## Implementation Plan

### Phase 1: Resolve Chakra component API mismatches
**Goal**: Eliminate invalid prop usage for current Chakra version.

**Tasks**:
- Replace deprecated/invalid props with current equivalents.
- Update button/icon/loading prop usage patterns.
- Normalize stack/grid spacing props for current component API.

**Verification**:
- [ ] No Chakra prop type errors remain

### Phase 2: Resolve hook/query API incompatibilities
**Goal**: Match current hook and query APIs.

**Tasks**:
- Update clipboard usage (`copy`/`copied` style fields).
- Replace unsupported query options (for example `keepPreviousData`) with the supported pattern for current TanStack Query version.
- Add explicit types for state setters/callback params currently inferred as `any`.

**Verification**:
- [ ] No hook/query-related TS errors remain

### Phase 3: Normalize async callback signatures
**Goal**: Ensure component callbacks match declared function contracts.

**Tasks**:
- Adapt handlers returning API payloads to return `void` where required.
- Keep response handling internal to mutation/helpers while preserving UI behavior.

**Verification**:
- [ ] No `Promise<T>` vs `Promise<void>` assignment errors remain

### Phase 4: Validate frontend baseline
**Goal**: Re-establish green frontend checks.

**Tasks**:
- Run `cd frontend && npm run lint:ci`
- Run `cd frontend && npm run build`

**Verification**:
- [ ] Lint passes
- [ ] Build passes

## Files to Modify
| File | Action |
|------|--------|
| `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx` | Modify |
| `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` | Modify |
| `frontend/src/components/GeneratedImages/CropModal.tsx` | Modify |
| `frontend/src/components/Prompts/PromptCard.tsx` | Modify |
| `frontend/src/components/Prompts/PromptDetailDrawer.tsx` | Modify |
| `frontend/src/components/Prompts/PromptList.tsx` | Modify |
| `frontend/src/components/Prompts/SceneContextPanel.tsx` | Modify |
| `frontend/src/routes/_layout/generated-images.tsx` | Modify |
| `frontend/src/routes/_layout/prompt-gallery.tsx` | Modify |
| `frontend/src/routes/_layout/scene-prompts.$sceneId.tsx` | Modify |
| `frontend/src/components/Common/Logo.tsx` | Modify |

## Testing Strategy
- **Type/lint checks**:
  - `cd frontend && npm run lint:ci`
  - `cd frontend && npm run build`
- **Behavior smoke test**:
  - Verify generated images and prompt gallery routes render and actions still work.

## Acceptance Criteria
- [ ] `cd frontend && npm run lint:ci` passes
- [ ] `cd frontend && npm run build` passes
- [ ] No TypeScript errors remain in generated images and prompt gallery flows

