# Editable Prompt Remix Feature

## Overview
Add an editable prompt text box with a remix button to the image viewing modal (`GeneratedImageModal.tsx`). When users edit the prompt and click remix, create a new prompt variant with the exact user-entered text and generate an image from it in the background (like the existing Remix feature). This provides manual control over prompt iteration alongside the automated AI-powered remix feature.

## Problem Statement
Users viewing images in the modal can see the AI-generated prompt that created the image, but they have no way to make quick manual edits to refine the prompt. Currently, to iterate on a prompt manually, users must:
- Copy the prompt text
- Navigate away from the image viewer
- Create a new prompt through the backend/CLI
- Trigger image generation manually
- Wait and navigate back to view results

**User impact**: Users can't quickly iterate on prompts with manual edits while viewing generated images, slowing down the creative refinement process.

**Business value**: Enables hybrid AI + human prompt iteration, allowing users to combine automated remixing (existing feature) with manual tweaks for faster convergence on ideal prompts.

## Proposed Solution
Extend `GeneratedImageModal` to include:
1. An editable textarea showing the current prompt text
2. A "Remix with Edits" button below the textarea
3. Backend endpoint to create a custom prompt variant and generate an image
4. Fire-and-forget background processing (no real-time feedback, matching existing Remix behavior)

**Architectural approach**:
- New POST endpoint: `/generated-images/{image_id}/custom-remix`
- Accepts custom prompt text in request body
- Creates one new `ImagePrompt` record with user's exact text
- Generates one image from the new prompt
- Preserves metadata (style_tags, attributes) from source prompt
- Increments variant_index like automated remix

**Key components involved**:
- Frontend: `GeneratedImageModal.tsx` (add textarea + button)
- Backend: New API route, new service method in `ImagePromptGenerationService`
- Database: Existing tables (`image_prompts`, `generated_images`)

**Integration with existing systems**:
- Uses existing `ImagePromptRepository` and `ImageGenerationService`
- Follows fire-and-forget pattern from existing `/remix` endpoint
- Preserves scene_extraction_id, prompt_version, and metadata lineage
- Complements (doesn't replace) the automated remix feature

## Codebase Research Summary

**Relevant existing patterns found**:
1. **Automated Remix** (`/generated-images/{image_id}/remix` in `generated_images.py:471-528`): Fire-and-forget async pattern with BackgroundTasks, returns 202 Accepted
2. **Prompt generation service**: `generate_remix_variants()` method (lines 401-544 in `image_prompt_generation_service.py`) creates prompts with incremented variant_index
3. **Modal UI**: `GeneratedImageModal.tsx` already displays prompt text (lines 337-366) in read-only mode with monospace font
4. **Repository bulk_create**: `ImagePromptRepository.bulk_create()` pattern for creating prompt records
5. **Metadata preservation**: Remix preserves `prompt_version`, `context_window`, and adds remix lineage to `raw_response` (lines 468-476)

**Files and components that will be affected**:
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`: Add textarea and remix button
- `backend/app/api/routes/generated_images.py`: New `/custom-remix` endpoint
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`: New method for custom prompt creation
- `backend/app/schemas/generated_image.py`: New request/response schemas
- `frontend/src/api/generatedImages.ts`: New API client method
- `frontend/src/client/`: Auto-generated OpenAPI client (regenerated)

**Similar features that can serve as reference**:
- Automated remix endpoint (`generated_images.py:471-528`) for async background task pattern
- `generate_remix_variants()` service method for variant_index management and metadata preservation
- Modal prompt display section (`GeneratedImageModal.tsx:337-366`) for UI integration point

**Potential risks or conflicts identified**:
- User may edit prompt to be incompatible with original style_tags/attributes (acceptable - metadata is just guidance)
- Need to prevent empty prompt submission
- Text area needs proper sizing to avoid UX issues (multi-line prompts can be 200+ chars)
- Concurrent edits while viewing modal (mitigated by component-local state)

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes to `GeneratedImageModal.tsx` and remix endpoints
4. Look for TODO/FIXME comments in affected files

**Key Decisions Made**:
- **Custom remix count**: Fixed at 1 variant per submission (user controls iteration manually)
- **Prompt text source**: User's edited text becomes exact `prompt_text` value (no LLM processing)
- **Metadata preservation**: Inherit `style_tags`, `attributes`, `context_window` from source prompt (editable text only affects `prompt_text`)
- **Metadata generation**: Title and flavour_text are auto-generated by `PromptMetadataGenerationService` (same as automated remix)
- **Prompt version**: Preserve original `prompt_version` to maintain grouping
- **Variant indexing**: Continue incrementing from max for scene (like automated remix)
- **Async execution**: Fire-and-forget background task (no progress tracking in v1)
- **UI placement**: Textarea + button in right context panel of modal, below existing prompt display
- **Edit tracking**: Add `custom_remix: true` flag to `raw_response` metadata to distinguish from AI-generated variants

**Deviations from standard patterns**:
- No LLM invocation for prompt text generation (user text stored verbatim, unlike standard generation or automated remix)
- Metadata generation (title/flavour_text) still uses LLM (PromptMetadataGenerationService)
- Single variant per request (vs. 2 for automated remix, 4 for standard generation)
- User-provided prompt text stored verbatim (no validation beyond non-empty check)

**Assumptions about the system**:
- Users understand this creates a new variant, not modifying the existing prompt
- Results appear after page refresh (fire-and-forget, like automated remix)
- Modal remains open after submission (user can continue editing/submitting)
- Textarea state resets on successful submission to prevent duplicate clicks

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify all dependencies from previous phases
- [ ] Read the latest version of files you'll modify
- [ ] Ensure database is up and running
- [ ] Verify OpenAI API key is configured (for image generation)

## Implementation Phases

### Phase 1: Backend Service Method for Custom Remix
**Goal**: Create a service method that accepts user-edited prompt text and creates a single prompt variant

**Dependencies**:
- Existing `ImagePromptGenerationService`
- Existing `ImagePromptRepository`
- Existing `_determine_next_variant_indices_for_scene()` helper (from automated remix)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] New method `create_custom_remix_variant()` in `ImagePromptGenerationService`
- [ ] Method accepts source `ImagePrompt` and custom prompt text string
- [ ] Method returns 1 new `ImagePrompt` record with exact user text
- [ ] Variant index continues from existing max for scene
- [ ] Metadata includes `custom_remix: true` flag
- [ ] Title and flavour_text are auto-generated via `PromptMetadataGenerationService`
- [ ] Method includes proper error handling (empty text, missing scene)

**Tasks**:
1. Add `create_custom_remix_variant()` method to `ImagePromptGenerationService` (in `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` around line 550, after `generate_remix_variants()`):
   - Method signature: `create_custom_remix_variant(source_prompt: ImagePrompt | UUID, custom_prompt_text: str, *, dry_run: bool = False) -> ImagePrompt | ImagePromptPreview`
   - Load source prompt from DB if UUID is passed (use existing `_resolve_prompt()` helper)
   - Validate `custom_prompt_text` is non-empty (raise `ImagePromptGenerationServiceError` if empty)
   - Query scene record to get `scene_extraction_id`
   - Call `_determine_next_variant_indices_for_scene(scene_id, 1)` to get next variant_index
   - Build single record dict with user's text and source metadata
   - No LLM invocation needed (direct record creation)

2. Build custom remix metadata:
   - Preserve `style_tags` and `attributes` from source prompt
   - Preserve `context_window` from source prompt
   - Create `raw_response` dict with:
     - `custom_remix: true`
     - `custom_remix_source_prompt_id: str(source_prompt.id)`
     - `custom_remix_timestamp: datetime.now(timezone.utc).isoformat()`
     - `custom_prompt_text: custom_prompt_text` (for audit trail)

3. Handle dry_run mode:
   - If `dry_run=True`:
     - Instantiate preview prompt from record using `_instantiate_prompts_from_records([record])`
     - Call `self._run_metadata_generation(preview_prompts, dry_run=True, autocommit=False)` to generate title/flavour_text
     - Populate `ImagePromptPreview` with metadata results (title and flavour_text)
     - Return `ImagePromptPreview` instance
   - If `dry_run=False`:
     - Use `self._prompt_repo.bulk_create([record], commit=self._config.autocommit, refresh=True)` to create prompt
     - If not autocommit, call `self._session.flush()`
     - Call `self._run_metadata_generation(created, dry_run=False, autocommit=self._config.autocommit)` to populate title and flavour_text fields
     - Return first item from created list

4. Add proper error handling:
   - Raise `ImagePromptGenerationServiceError` if `custom_prompt_text` is empty or whitespace-only
   - Raise `ImagePromptGenerationServiceError` if source prompt or scene not found
   - Log creation success with prompt ID and variant_index

### Phase 2: Backend API Endpoint for Custom Remix
**Goal**: Create a REST endpoint that accepts custom prompt text and triggers background generation

**Dependencies**:
- Phase 1 completed
- Existing `/remix` endpoint pattern in `generated_images.py`

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] New POST endpoint `/generated-images/{image_id}/custom-remix`
- [ ] Endpoint validates image exists and has associated prompt
- [ ] Endpoint validates custom_prompt_text is non-empty
- [ ] Endpoint triggers async generation (prompt + image)
- [ ] Returns 202 Accepted with job metadata
- [ ] Proper error handling for missing/invalid inputs

**Tasks**:
1. Create Pydantic schemas in `backend/app/schemas/generated_image.py`:
   - `GeneratedImageCustomRemixRequest`:
     - Field: `custom_prompt_text: str` (required, min_length=1)
   - `GeneratedImageCustomRemixResponse`:
     - Field: `custom_prompt_id: str` (UUID of created prompt)
     - Field: `status: str` (always "accepted")
     - Field: `estimated_completion_seconds: int`

2. Add POST route in `backend/app/api/routes/generated_images.py` (around line 530, after existing `/remix` endpoint):
   - Route path: `@router.post("/{image_id}/custom-remix", response_model=GeneratedImageCustomRemixResponse, status_code=status.HTTP_202_ACCEPTED)`
   - Parameters: `session: SessionDep`, `background_tasks: BackgroundTasks`, `image_id: UUID`, `request: GeneratedImageCustomRemixRequest`
   - Load image from `GeneratedImageRepository.get(image_id)` (raise 404 if not found)
   - Load associated prompt from `ImagePromptRepository.get(image.image_prompt_id)` (raise 404 if not found)
   - Validate `request.custom_prompt_text` is not empty/whitespace (raise 400 if invalid)
   - Instantiate services (defensive try/except like existing remix endpoint)
   - Add background task `_execute_custom_remix_generation()`
   - Return 202 response with estimated completion time (60 seconds for 1 image)

3. Create background task function `_execute_custom_remix_generation()` (in same file, after existing `_execute_remix_generation()`):
   - Parameters: `source_image_id: UUID`, `source_prompt_id: UUID`, `custom_prompt_text: str`, `dry_run: bool = False`
   - Open new session (follow pattern from `_execute_remix_generation()`)
   - Instantiate `ImagePromptGenerationService(session)`
   - Call `create_custom_remix_variant(source_prompt_id, custom_prompt_text, dry_run=dry_run)`
   - Instantiate `ImageGenerationService(session)`
   - Call `generate_for_selection(prompt_ids=[new_prompt.id])` with new prompt ID
   - Log errors but don't raise (fire-and-forget)
   - Close session in finally block

4. Add proper error responses:
   - 404 if image not found
   - 404 if associated prompt not found
   - 400 if `custom_prompt_text` is empty or whitespace-only
   - 500 if service initialization fails

### Phase 3: Frontend Editable Prompt UI in Modal
**Goal**: Add an editable textarea and "Remix with Edits" button to the modal's prompt section

**Dependencies**:
- Phase 2 completed
- Existing `GeneratedImageModal.tsx` component
- Existing modal layout with right context panel

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] Textarea replaces read-only prompt text display
- [ ] Textarea is populated with current prompt text on modal open
- [ ] "Remix with Edits" button appears below textarea
- [ ] Button shows loading state during API call
- [ ] Button disabled when textarea is empty or unchanged
- [ ] Textarea resets to original prompt text after successful remix
- [ ] Success/error toast notifications

**Tasks**:
1. Update prompt display section in `GeneratedImageModal.tsx` (lines 337-366):
   - Import `Textarea` from Chakra UI and `FiEdit3` icon from react-icons
   - Add local state: `const [editedPromptText, setEditedPromptText] = useState<string>("")`
   - Add local state: `const [isRemixing, setIsRemixing] = useState(false)`
   - Initialize `editedPromptText` when `currentImage.prompt` changes: `useEffect(() => { if (currentImage?.prompt?.prompt_text) setEditedPromptText(currentImage.prompt.prompt_text) }, [currentImage?.prompt?.prompt_text])`
   - Replace read-only `<Text>` with `<Textarea>` component
   - Textarea props:
     - `value={editedPromptText}`
     - `onChange={(e) => setEditedPromptText(e.target.value)}`
     - `fontSize="sm"`
     - `fontFamily="mono"`
     - `minH="200px"` (support multi-line prompts)
     - `resize="vertical"`
     - `whiteSpace="pre-wrap"`

2. Add "Remix with Edits" button below textarea:
   - Use Chakra `Button` component with `FiEdit3` icon
   - Button text: "Remix with Edits"
   - Button props:
     - `size="sm"`
     - `colorPalette="purple"`
     - `variant="outline"`
     - `isLoading={isRemixing}`
     - `isDisabled={isRemixing || !editedPromptText.trim() || editedPromptText === currentImage?.prompt?.prompt_text}`
     - `onClick={handleCustomRemix}` (defined in next step)
   - Place in `HStack` with gap={2} for icon + text layout

3. Add `handleCustomRemix` callback function (before return statement):
   - Function signature: `const handleCustomRemix = async () => { ... }`
   - Guard: `if (!currentImage?.image?.id || !editedPromptText.trim()) return`
   - Set `isRemixing(true)` at start
   - Call new prop `onCustomRemix(currentImage.image.id, editedPromptText)`
   - On success: reset `editedPromptText` to original prompt text
   - On error: keep edited text (allow retry)
   - Set `isRemixing(false)` in finally block

4. Update `GeneratedImageModalProps` interface (lines 30-38):
   - Add optional prop: `onCustomRemix?: (imageId: string, customPromptText: string) => Promise<void>`

### Phase 4: Frontend API Integration
**Goal**: Connect the modal's custom remix button to the backend endpoint

**Dependencies**:
- Phase 2 and 3 completed
- Existing API client patterns

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] API client method in `frontend/src/api/generatedImages.ts`
- [ ] TanStack mutation in `generated-images.tsx`
- [ ] Mutation wired to `GeneratedImageModal` component
- [ ] Success/error toast notifications
- [ ] Auto-generated client types refreshed

**Tasks**:
1. Add type definitions in `frontend/src/api/generatedImages.ts` (after existing types):
   - `GeneratedImageCustomRemixRequest`:
     - Property: `custom_prompt_text: string`
   - `GeneratedImageCustomRemixResponse`:
     - Property: `custom_prompt_id: string`
     - Property: `status: string`
     - Property: `estimated_completion_seconds: number`

2. Create API client function in `frontend/src/api/generatedImages.ts` (after `remixImage()` function, around line 265):
   - Function signature: `export const customRemixImage = async (imageId: string, customPromptText: string): Promise<GeneratedImageCustomRemixResponse>`
   - Build URL: `const url = buildUrl(\`/api/v1/generated-images/\${encodeURIComponent(imageId)}/custom-remix\`)`
   - Make POST request with body: `{ custom_prompt_text: customPromptText }`
   - Handle errors (throw with descriptive message)
   - Return parsed response

3. Add mutation in `frontend/src/routes/_layout/generated-images.tsx` (after existing `remixMutation`, around line 525):
   - Use `useMutation` from TanStack Query
   - Mutation function signature: `mutationFn: ({ imageId, customPromptText }: { imageId: string, customPromptText: string }) => customRemixImage(imageId, customPromptText)`
   - On success: Show toast "Custom remix started! Refresh in 1-2 minutes to see results."
   - On error: Show error toast with error message
   - No optimistic updates needed (fire-and-forget)

4. Wire mutation to modal component (in `GeneratedImagesGalleryPage` component):
   - Create callback: `const handleCustomRemix = useCallback((imageId: string, customPromptText: string) => customRemixMutation.mutateAsync({ imageId, customPromptText }), [customRemixMutation])`
   - Pass callback to `GeneratedImageModal` as `onCustomRemix` prop (line 657-668)

5. Regenerate OpenAPI client types:
   - Run: `cd frontend && ./scripts/generate-client.sh`
   - Verify no TypeScript errors
   - Commit updated types

## System Integration Points
Document all external systems/services this feature touches:
- **Database Tables**:
  - **Read**: `generated_images` (to get source image and prompt ID)
  - **Read**: `image_prompts` (to get source prompt details and metadata)
  - **Read**: `scene_extractions` (to validate scene exists)
  - **Write**: `image_prompts` (new custom remix prompt variant)
  - **Write**: `generated_images` (new generated image from custom prompt)
- **External APIs**:
  - **OpenAI DALL-E 3 API**: Generate image from custom prompt (via `dalle_image_api.generate_images()`)
- **Message Queues**: None (direct async execution via FastAPI BackgroundTasks)
- **WebSockets**: None
- **Cron Jobs**: None
- **Cache Layers**: None (consider invalidating TanStack Query cache for scene after custom remix - future enhancement)

## Technical Considerations
- **Performance**:
  - Custom remix generates 1 prompt + 1 image per submission (~30-60 seconds)
  - No LLM call for prompt generation (faster than automated remix)
  - Uses existing concurrency controls in `ImageGenerationService`
  - No impact on modal rendering (textarea is simple controlled input)
- **Security**:
  - No LLM injection risk (user text goes directly to DALL-E, which has own safety filters)
  - Validate prompt text is non-empty to prevent wasted API calls
  - Future: rate limiting to prevent abuse (not needed for local dev)
- **Database**:
  - No schema changes needed
  - Variant indices must be unique per scene (handled by incrementing logic)
  - No migrations required
- **API Design**:
  - RESTful endpoint: `POST /generated-images/{image_id}/custom-remix`
  - 202 Accepted response (async processing)
  - Request body includes custom prompt text
- **Error Handling**:
  - 404 if image or prompt not found
  - 400 if prompt text is empty/whitespace
  - DALL-E failures create error records in `generated_images` table (existing pattern)
  - Frontend shows toast on API errors
  - Backend logs custom remix requests with source image ID and text length
- **Monitoring**:
  - Log custom remix requests with source image ID, prompt ID, and custom text length
  - Log custom prompt creation success/failure
  - Log custom remix image generation success/failure
  - Use existing logging infrastructure (Python `logging` module)

## Testing Strategy
1. **Unit Tests**:
   - Test `create_custom_remix_variant()` with valid inputs (verify prompt record created)
   - Test `create_custom_remix_variant()` with empty text (verify error raised)
   - Test variant_index incrementing (verify continues from max for scene)
2. **Integration Tests**:
   - Test `/custom-remix` endpoint with valid image ID and text (verify 202 response)
   - Test `/custom-remix` endpoint with invalid image ID (verify 404)
   - Test `/custom-remix` endpoint with empty text (verify 400)
3. **Manual Verification** (5 minutes):
   - Open modal for a generated image
   - Edit prompt text in textarea
   - Click "Remix with Edits" button
   - Verify toast appears with success message
   - Refresh page after 1 minute
   - Verify new variant appears with edited prompt text

## Acceptance Criteria
- [ ] All automated tests pass
- [ ] Code follows project conventions (Python: 4 spaces, snake_case; TypeScript: 2 spaces, camelCase)
- [ ] Backend linting passes (`cd backend && uv run bash scripts/lint.sh`)
- [ ] Frontend linting passes (`cd frontend && npm run lint`)
- [ ] Textarea appears in modal with current prompt text
- [ ] "Remix with Edits" button appears below textarea
- [ ] Clicking button triggers backend generation (fire-and-forget)
- [ ] Button disabled when text is empty or unchanged
- [ ] Success toast shows "Custom remix started!" message
- [ ] Error cases handled gracefully (404, 400, toast on error)
- [ ] No console errors in browser
- [ ] Existing automated remix feature still works (no regression)

## Quick Reference Commands
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run full stack**: `docker compose watch`
- **Backend linting**: `cd backend && uv run bash scripts/lint.sh`
- **Frontend linting**: `cd frontend && npm run lint`
- **Regenerate OpenAPI client**: `cd frontend && ./scripts/generate-client.sh`
- **View backend logs**: `docker compose logs -f backend`
- **Test custom remix endpoint**: `curl -X POST http://localhost:8000/api/v1/generated-images/{image_id}/custom-remix -H "Content-Type: application/json" -d '{"custom_prompt_text": "Your edited prompt here"}'`
- **Check database**: `docker compose exec db psql -U postgres -d app`
- **Query prompts for scene**: `SELECT variant_index, prompt_text FROM image_prompts WHERE scene_extraction_id = '<scene_id>' ORDER BY variant_index;`

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
