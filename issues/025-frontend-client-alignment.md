# Migrate Frontend API Wrappers to Auto-Generated Client

## Overview
Replace hand-written `fetch()` calls in frontend API wrapper files with the auto-generated OpenAPI SDK service classes. Remove dead code for non-existent backend endpoints.

## Problem Statement
14 of 21 frontend API functions use hand-written `fetch()` calls instead of the auto-generated `@hey-api/openapi-ts` SDK. This creates contract drift risk: when backend endpoints change and the client is regenerated, the hand-written calls silently fall out of sync. The generated SDK already has matching methods for all existing endpoints, making the hand-written versions redundant.

Additionally, `imagePromptGeneration.ts` calls two endpoints (`/api/v1/image-prompt-generation/book/{bookSlug}` and `/scene/{sceneId}`) that don't exist on the backend — dead code that should be removed.

## Proposed Solution
Migrate all hand-written `fetch()` calls to use the generated service classes (e.g., `SettingsService.getSettings()`, `GeneratedImagesService.updateImageApproval()`). Delete `imagePromptGeneration.ts` entirely. Where wrapper files add value (type normalization, sanitization), keep the wrapper but delegate to the SDK internally.

## Codebase Research Summary

### Auto-generated SDK (`frontend/src/client/sdk.gen.ts`):
Generated service classes with methods matching all backend endpoints:
- `SettingsService` — `getSettings()`, `updateSettings()`
- `DocumentsService` — `getDocumentsDashboard()`
- `ImagePromptsService` — `listPromptsForScene()`, `listPromptsForBook()`, `listPrompts()`, `getImagePrompt()`, `generateMetadataVariants()`, `updatePromptMetadata()`
- `GeneratedImagesService` — `listProviders()`, `listGeneratedImages()`, `getGeneratedImage()`, `listGeneratedImagesForScene()`, `updateImageApproval()`, `remixGeneratedImage()`, `customRemixGeneratedImage()`, `queueImageForPosting()`, `getImagePostingStatus()`, `cropImage()`

### Files with direct fetch() calls:
| File | fetch() calls | SDK available |
|------|---------------|---------------|
| `frontend/src/api/settings.ts` | `get()`, `update()` | Yes — `SettingsService` |
| `frontend/src/api/documents.ts` | `getDashboard()` | Yes — `DocumentsService` |
| `frontend/src/api/imagePromptGeneration.ts` | `triggerForBook()`, `triggerForScene()` | No — endpoints don't exist |
| `frontend/src/api/imagePrompts.ts` | `list()`, `generatePromptMetadata()`, `updatePromptMetadata()` | Yes — `ImagePromptsService` |
| `frontend/src/api/generatedImages.ts` | `updateImageApproval()`, `remixImage()`, `customRemixImage()`, `queueForPosting()`, `getPostingStatus()`, `cropImage()` | Yes — `GeneratedImagesService` |

### Reference pattern (files already using SDK):
- `sceneExtractions.ts` and `sceneRankings.ts` use `__request()` from client core
- New migration should use the higher-level generated service classes for full type safety

### Client generation:
- Script: `scripts/generate-client.sh`
- Config: `frontend/openapi-ts.config.ts` (legacy/axios client, SDK plugin with `asClass: true`)

## Key Decisions
- **Use generated service classes** (e.g., `SettingsService.getSettings()`) rather than low-level `__request()`. Simpler, fully type-safe, auto-updates on regeneration.
- **Delete `imagePromptGeneration.ts`** entirely — endpoints don't exist on backend, dead code.
- **Keep wrapper files** where they add value (type normalization like `normalizeContextWindow` in `imagePrompts.ts`, sanitization). Wrappers delegate to SDK internally.
- **Remove hand-written utilities** (`buildUrl()`, `parseErrorBody()`) once no longer needed.

## Implementation Plan

### Phase 1: Delete dead code
**Goal**: Remove `imagePromptGeneration.ts` and all references.

**Tasks**:
- Delete `frontend/src/api/imagePromptGeneration.ts`
- Grep for imports of `imagePromptGeneration` or `ImagePromptGenerationApi` across the frontend and remove all references
- Remove any UI components or buttons that call these dead endpoints

**Verification**:
- [ ] No imports of `imagePromptGeneration` remain in the codebase
- [ ] `npm run lint:ci` passes

### Phase 2: Migrate settings.ts
**Goal**: Replace fetch() calls with `SettingsService`.

**Tasks**:
- Update `frontend/src/api/settings.ts`:
  - Replace `get()` to use `SettingsService.getSettings()`
  - Replace `update(payload)` to use `SettingsService.updateSettings({ requestBody: payload })`
- Remove `buildUrl()` and `parseErrorBody()` imports if no longer used in this file

**Verification**:
- [ ] Settings page loads and saves correctly
- [ ] No direct `fetch()` calls in `settings.ts`

### Phase 3: Migrate documents.ts
**Goal**: Replace fetch() calls with `DocumentsService`.

**Tasks**:
- Update `frontend/src/api/documents.ts`:
  - Replace `getDashboard()` to use `DocumentsService.getDocumentsDashboard()`
- Remove unused utility imports

**Verification**:
- [ ] Documents dashboard loads correctly
- [ ] No direct `fetch()` calls in `documents.ts`

### Phase 4: Migrate imagePrompts.ts fetch() calls
**Goal**: Replace the 3 remaining fetch() calls while keeping the wrapper's normalization logic.

**Tasks**:
- Update `frontend/src/api/imagePrompts.ts`:
  - Replace `list(params)` to use `ImagePromptsService.listPrompts({ query: params })`
  - Replace `generatePromptMetadata(promptId, variantsCount)` to use `ImagePromptsService.generateMetadataVariants({ path: { prompt_id: promptId }, body: { variants_count: variantsCount } })`
  - Replace `updatePromptMetadata(promptId, metadata)` to use `ImagePromptsService.updatePromptMetadata({ path: { prompt_id: promptId }, body: metadata })`
- Keep `normalizeContextWindow()` and the type-safe wrapper interface

**Verification**:
- [ ] Prompt listing, metadata generation, and metadata update work correctly
- [ ] No direct `fetch()` calls in `imagePrompts.ts`

### Phase 5: Migrate generatedImages.ts fetch() calls
**Goal**: Replace the 6 remaining fetch() calls while keeping the wrapper's interface.

**Tasks**:
- Update `frontend/src/api/generatedImages.ts`:
  - Replace `updateImageApproval(imageId, approved)` to use `GeneratedImagesService.updateImageApproval({ path: { image_id: imageId }, body: { approved } })`
  - Replace `remixImage(imageId, payload)` to use `GeneratedImagesService.remixGeneratedImage({ path: { image_id: imageId }, body: payload })`
  - Replace `customRemixImage(imageId, customPromptText)` to use `GeneratedImagesService.customRemixGeneratedImage({ path: { image_id: imageId }, body: { custom_prompt_text: customPromptText } })`
  - Replace `queueForPosting(imageId)` to use `GeneratedImagesService.queueImageForPosting({ path: { image_id: imageId } })`
  - Replace `getPostingStatus(imageId)` to use `GeneratedImagesService.getImagePostingStatus({ path: { image_id: imageId } })`
  - Replace `cropImage(imageId, file)` to use `GeneratedImagesService.cropImage({ path: { image_id: imageId }, body: { file } })` — verify FormData handling works with the generated client

**Verification**:
- [ ] Image approval, remix, custom remix, posting, and crop all work correctly
- [ ] No direct `fetch()` calls in `generatedImages.ts`

### Phase 6: Clean up shared utilities
**Goal**: Remove unused helper functions.

**Tasks**:
- Check if `buildUrl()` and `parseErrorBody()` utilities are still used anywhere after migration
- If unused, remove them from whatever utility module defines them
- Run `npm run lint:ci` to catch any dead imports

**Verification**:
- [ ] No dead utility functions remain
- [ ] `npm run lint:ci` passes
- [ ] `npm run build` passes

## Files to Modify
| File | Action |
|------|--------|
| `frontend/src/api/imagePromptGeneration.ts` | Delete |
| `frontend/src/api/settings.ts` | Modify — use `SettingsService` |
| `frontend/src/api/documents.ts` | Modify — use `DocumentsService` |
| `frontend/src/api/imagePrompts.ts` | Modify — replace 3 fetch() calls |
| `frontend/src/api/generatedImages.ts` | Modify — replace 6 fetch() calls |
| Any files importing `imagePromptGeneration` | Modify — remove dead references |

## Testing Strategy
- **Unit Tests**: N/A (no frontend E2E tests per project guidelines)
- **Manual Verification**: Verify each migrated endpoint works by using the corresponding UI feature (settings page, documents dashboard, prompt metadata, image approval/remix/crop)

## Acceptance Criteria
- [ ] `imagePromptGeneration.ts` deleted and all references removed
- [ ] Zero direct `fetch()` calls remain in API wrapper files
- [ ] All API wrappers delegate to generated service classes
- [ ] `npm run lint:ci` passes
- [ ] `npm run build` passes
- [ ] All UI features backed by migrated endpoints still work
