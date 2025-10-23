# Image Remix Feature

## Overview
Add a "Remix" button to each image in the `/generated-images` frontend that triggers generation of 2 new prompt variants based on the clicked image's existing prompt. These new prompts should be subtle refinements of the original, maintaining most details while exploring small variations. For v1, the button triggers backend processing with no frontend feedback beyond the initial click.

## Problem Statement
Users viewing generated images often find ones they like but want to explore variations. Currently, to get variations, users must:
- Manually identify which prompt generated the liked image
- Generate entirely new prompts with different styles (which may deviate too much)
- Wait through the full prompt generation + image generation cycle

**User impact**: Users can't easily explore subtle variations of images they like, limiting creative iteration and refinement.

**Business value**: Enables iterative improvement of image quality, helping users find the perfect visual representation for each scene.

## Proposed Solution
Add a "Remix" button to `GeneratedImageCard` that:
1. Calls a new backend endpoint `/generated-images/{image_id}/remix`
2. Backend creates 2 new prompt variants based on the original prompt using gemini api
3. Backend generates images for both new prompts
4. User can refresh the page after waiting a while to see results

**Architectural approach**:
- New POST endpoint in `backend/app/api/routes/generated_images.py`
- New service method in `ImagePromptGenerationService` for remix-specific prompt generation
- Use Gemini API with special instructions to create subtle variations
- Leverage existing `ImageGenerationService` to generate images from new prompts
- No new database tables needed (use existing `image_prompts` and `generated_images`)

**Key components involved**:
- Frontend: `GeneratedImageCard.tsx`, new API client method
- Backend: New API route, service methods in `ImagePromptGenerationService` and `ImageGenerationService`
- Database: Existing tables (`image_prompts`, `generated_images`)

**Integration with existing systems**:
- Uses existing prompt generation service with custom configuration
- Uses existing image generation service
- Follows existing patterns for async generation (fire-and-forget in v1)

## Codebase Research Summary

**Relevant existing patterns found**:
1. **Image generation endpoint** (`/generated-images/generate`): Fire-and-forget async pattern for bulk generation (lines 341-391 in `generated_images.py`)
2. **Prompt generation service**: `ImagePromptGenerationService.generate_for_scene()` with configurable variants_count and temperature (lines 170-316 in `image_prompt_generation_service.py`)
3. **Repository pattern**: All data access through repository classes (`ImagePromptRepository`, `GeneratedImageRepository`)
4. **API schema pattern**: Pydantic models in `schemas/` with camelCase for JSON keys
5. **Frontend mutation pattern**: TanStack Query mutations with optimistic updates (lines 347-507 in `generated-images.tsx`)

**Files and components that will be affected**:
- `backend/app/api/routes/generated_images.py`: New `/remix` endpoint
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`: New remix method
- `backend/app/schemas/generated_image.py`: New request/response schemas
- `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx`: New Remix button
- `frontend/src/api/generatedImages.ts`: New API client method
- `frontend/src/client/`: Auto-generated OpenAPI client (regenerated)

**Similar features that can serve as reference**:
- `/generated-images/generate` endpoint (async image generation)
- `ImagePromptGenerationService.generate_for_scene()` (prompt generation with variants)
- Approval update mutation in `generated-images.tsx` (frontend mutation pattern)

**Potential risks or conflicts identified**:
- Remix should preserve `prompt_version` to maintain consistency
- Need to handle variant_index carefully (should continue incrementing from existing variants)
- LLM may produce variations that are too different or too similar
- No user feedback mechanism in v1 (acceptable per requirements)

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes
4. Look for TODO/FIXME comments in affected files

**Key Decisions Made**:
- **Remix prompt count**: Fixed at 2 variants per remix (configurable via REMIX_VARIANTS_COUNT constant in `image_prompt_generation_service.py`)
- **LLM approach**: Use Gemini API with custom system instruction emphasizing subtle variations
- **Prompt version**: Preserve original `prompt_version` but add metadata to track remix lineage
- **Variant indexing**: Find max variant_index for scene and continue from there (not reset to 0)
- **Async execution**: Fire-and-forget pattern (no progress tracking or notifications in v1)
- **Temperature**: Use higher temperature (0.7) for remix vs. standard generation (0.4) to ensure variation
- **Style preservation**: Inherit style_tags and attributes from source prompt, only vary composition/lighting/minor details

**Deviations from standard patterns**:
- Custom prompt template for remix (different from standard scene extraction prompt)
- Higher temperature setting to encourage variation while maintaining coherence

**Assumptions about the system**:
- Users understand v1 has no real-time feedback
- Images will appear after page refresh (after waiting a while)
- Remix should be idempotent (can click multiple times, each creates 2 new variants)

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify all dependencies from previous phases
- [ ] Read the latest version of files you'll modify
- [ ] Ensure database is up and running
- [ ] Verify OpenAI API key is configured

## Implementation Phases

### Phase 1: Backend Service Method for Remix Prompt Generation
**Goal**: Create a service method that generates remix variants based on an existing prompt

**Dependencies**:
- Existing `ImagePromptGenerationService`
- Existing `ImagePromptRepository` and `GeneratedImageRepository`

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] New method `generate_remix_variants()` in `ImagePromptGenerationService`
- [ ] Method accepts source `ImagePrompt` and returns 2 new `ImagePrompt` records
- [ ] Prompts contain subtle variations (verified by logging)
- [ ] Variant indices continue from existing max for the scene
- [ ] Method includes proper error handling

**Tasks**:
1. Add `generate_remix_variants()` method to `ImagePromptGenerationService` (in `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`)
   - Method signature: `generate_remix_variants(source_prompt: ImagePrompt | UUID, *, variants_count: int = 2, dry_run: bool = False) -> list[ImagePrompt] | list[ImagePromptPreview]`
   - Load source prompt from DB if UUID is passed
   - Query max variant_index for the scene from `ImagePromptRepository`
   - Build custom remix prompt using `_build_remix_prompt()` helper method
   - Call Gemini API with temperature=0.7 (higher than standard 0.4)
   - Parse response and create new ImagePrompt records with incremented variant_index
   - Preserve `prompt_version` from source but add remix metadata to `raw_response`

2. Add `_build_remix_prompt()` private helper method
   - Takes source prompt and config as parameters
   - Constructs LLM prompt instructing subtle variations
   - Include source prompt text, style_tags, and attributes
   - Emphasize maintaining core composition while varying lighting, camera angle, or minor details
   - Example instruction: "Create 2 subtle variations of this prompt, keeping the subject, mood, and style consistent but exploring different lighting conditions or camera angles. Change only 2-3 elements maximum."

3. Add `_determine_next_variant_indices()` helper method
   - Query `ImagePromptRepository.list_for_scene()` to get all existing prompts for scene
   - Find max variant_index, return list of next N indices (e.g., if max is 3, return [4, 5] for 2 variants)

4. Update method to add remix lineage metadata
   - In `raw_response` field, include: `{"remix_source_prompt_id": "<source_id>", "remix_generation_timestamp": "<timestamp>"}`

### Phase 2: Backend API Endpoint for Remix
**Goal**: Create a REST endpoint that triggers remix generation

**Dependencies**:
- Phase 1 completed
- Existing FastAPI route patterns in `generated_images.py`

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] New POST endpoint `/generated-images/{image_id}/remix`
- [ ] Endpoint validates image exists and has associated prompt
- [ ] Endpoint triggers async generation (prompt + image)
- [ ] Returns 202 Accepted with remix job metadata
- [ ] Proper error handling for missing/invalid image_id

**Tasks**:
1. Create Pydantic schemas in `backend/app/schemas/generated_image.py`:
   - `GeneratedImageRemixRequest`: Empty body (or optional config overrides)
   - `GeneratedImageRemixResponse`: Contains `remix_prompt_ids: list[UUID]`, `status: str`, `estimated_completion_seconds: int`

2. Add POST route in `backend/app/api/routes/generated_images.py`:
   - Route path: `@router.post("/{image_id}/remix", response_model=GeneratedImageRemixResponse)`
   - Load image from `GeneratedImageRepository.get(image_id)`
   - Load associated prompt from `ImagePromptRepository.get(image.image_prompt_id)`
   - Validate prompt exists (raise 404 if not)
   - Call service method in background task (use FastAPI's `BackgroundTasks`)
   - Return 202 response with prompt IDs (empty initially, since async)

3. Create background task function `_execute_remix_generation()`:
   - Instantiate `ImagePromptGenerationService`
   - Call `generate_remix_variants(source_prompt)`
   - Instantiate `ImageGenerationService`
   - Call `generate_for_selection(prompt_ids=[...])` with new prompt IDs
   - Log errors but don't raise (fire-and-forget)

4. Add proper error responses:
   - 404 if image not found
   - 404 if associated prompt not found
   - 500 if service initialization fails

### Phase 3: Frontend Remix Button UI
**Goal**: Add a Remix button to the image card component

**Dependencies**:
- Phase 2 completed
- Existing `GeneratedImageCard` component

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Remix button visible on hover or always visible (design choice)
- [ ] Button triggers API call to remix endpoint
- [ ] Button shows loading state during API call
- [ ] Button disabled after successful click (prevent duplicate clicks)
- [ ] Error toast if API call fails

**Tasks**:
1. Add Remix button to `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx`:
   - Import `FiShuffle` or similar icon from `react-icons/fi`
   - Add new `IconButton` next to approval buttons (or in separate HStack)
   - Button label: "Remix" with shuffle icon
   - Wire up `onClick` handler to call new prop `onRemix(imageId)`

2. Update `GeneratedImageCardProps` interface:
   - Add optional prop: `onRemix?: (imageId: string) => void`

3. Add loading state management:
   - Use local state `isRemixing` to track button state
   - Show spinner on button when `isRemixing === true`
   - Disable button when `isRemixing === true`

### Phase 4: Frontend API Integration
**Goal**: Connect the Remix button to the backend endpoint

**Dependencies**:
- Phase 2 and 3 completed
- Existing API client patterns

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] API client method in `frontend/src/api/generatedImages.ts`
- [ ] TanStack mutation in `generated-images.tsx`
- [ ] Mutation wired to `GeneratedImageCard` component
- [ ] Success/error toast notifications
- [ ] Auto-generated client types refreshed

**Tasks**:
1. Create API client method in `frontend/src/api/generatedImages.ts`:
   - Function signature: `export const remixImage = async (imageId: string): Promise<GeneratedImageRemixResponse>`
   - Make POST request to `/api/generated-images/{imageId}/remix`
   - Return parsed response

2. Add mutation in `frontend/src/routes/_layout/generated-images.tsx`:
   - Use `useMutation` from TanStack Query
   - Mutation function calls `remixImage(imageId)`
   - On success: Show toast "Remix started! Refresh in 2-3 minutes to see results"
   - On error: Show error toast with message
   - No optimistic updates needed (fire-and-forget)

3. Wire mutation to card component:
   - Create `handleRemix` callback that calls `remixMutation.mutate(imageId)`
   - Pass callback to `GeneratedImageCard` as `onRemix` prop

4. Regenerate OpenAPI client types:
   - Run `cd frontend && ./scripts/generate-client.sh`
   - Commit updated types

## System Integration Points

**Database Tables**:
- **Read**: `generated_images` (to get source image and prompt ID)
- **Read**: `image_prompts` (to get source prompt details)
- **Write**: `image_prompts` (new remix prompt variants)
- **Write**: `generated_images` (new generated images from remix prompts)

**External APIs**:
- **Gemini API**: Generate remix prompt variants (via `gemini_api.json_output()`)
- **OpenAI DALL-E 3 API**: Generate images from remix prompts (via `dalle_image_api.generate_images()`)

**Message Queues**: None (direct async execution via FastAPI BackgroundTasks)

**WebSockets**: None

**Cron Jobs**: None

**Cache Layers**: None (but consider invalidating TanStack Query cache for scene after remix completes - future enhancement)

## Technical Considerations

**Performance**:
- Remix generates 2 prompts + 2 images per click (~30-60 seconds total)
- Uses existing concurrency controls in `ImageGenerationService` (default 3 concurrent)
- No impact on page load (async background task)

**Security**:
- Validate image ownership if user auth is added later (not needed for local dev)
- Rate limiting could be added to prevent abuse (future enhancement)

**Database**:
- No schema changes needed
- Variant indices must be unique per scene (handled by incrementing logic)
- No migrations required

**API Design**:
- RESTful endpoint: `POST /generated-images/{image_id}/remix`
- 202 Accepted response (async processing)
- Response includes estimated completion time for UX clarity

**Error Handling**:
- 404 if image or prompt not found
- LLM failures logged but don't crash (fire-and-forget)
- DALL-E failures create error records in `generated_images` table (existing pattern)
- Frontend shows toast on API errors

**Monitoring**:
- Log remix requests with source image ID and timestamp
- Log remix prompt generation success/failure
- Log remix image generation success/failure
- Use existing logging infrastructure (Python `logging` module)

## Acceptance Criteria
- [ ] Code follows project conventions (Python: 4 spaces, snake_case; TypeScript: 2 spaces, camelCase)
- [ ] Backend linting passes (`uv run bash scripts/lint.sh`)
- [ ] Frontend linting passes (`npm run lint`)
- [ ] Remix button appears on image cards
- [ ] Clicking Remix triggers backend generation (fire-and-forget)
- [ ] Error cases handled gracefully (404 for missing image, toast on API error)
- [ ] No console errors in browser

## Quick Reference Commands
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run full stack**: `docker compose watch`
- **Backend linting**: `cd backend && uv run bash scripts/lint.sh`
- **Frontend linting**: `cd frontend && npm run lint`
- **Regenerate OpenAPI client**: `cd frontend && ./scripts/generate-client.sh`
- **View backend logs**: `docker compose logs -f backend`
- **Test remix endpoint**: `curl -X POST http://localhost:8000/api/generated-images/{image_id}/remix`
- **Check database**: `docker compose exec db psql -U postgres -d app`

## Inter-Instance Communication

### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes Structure:
Each phase should document:
- Completion status
- Date completed
- Key findings or learnings
- Any deviations from the original plan and rationale
- Warnings or gotchas for future work

---

**Phase 1 Notes**:
<!-- To be filled by implementing instance -->

**Phase 2 Notes**:
<!-- To be filled by implementing instance -->

**Phase 3 Notes**:
<!-- To be filled by implementing instance -->

**Phase 4 Notes**:
<!-- To be filled by implementing instance -->
