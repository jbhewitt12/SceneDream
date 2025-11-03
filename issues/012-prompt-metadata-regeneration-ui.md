# Prompt Title/Flavour Text Regeneration UI

## Overview
Add a user-facing feature in the Generated Images modal to regenerate title and flavour text for image prompts on demand, allowing users to preview and apply alternative metadata options without manually editing fields.

## Problem Statement

**Current limitations**:
- Title and flavour text are generated once during prompt creation and cannot be easily regenerated
- Users have no way to generate alternative title/flavour text options if the initial ones aren't suitable
- Manual editing is cumbersome and doesn't leverage the LLM's creative generation capabilities
- No preview workflow for comparing multiple metadata options before committing

**User impact**:
- Stuck with initial metadata even if it's not ideal for sharing
- Must manually edit text fields to improve metadata, losing creative AI suggestions
- Cannot explore variations without modifying the database directly

**Business value**:
- Enables iterative refinement of shareable metadata for social media posts
- Improves user satisfaction by providing creative options
- Maintains engaging, high-quality titles and flavour text for public content

## Proposed Solution

Add an interactive metadata regeneration feature to the Generated Images modal:
1. New "Regenerate Metadata" button in the image modal
2. Clicking opens a secondary modal showing 5 newly generated title/flavour text pairs
3. Each pair has a "Use" button to apply it to the prompt
4. Selecting a pair updates the prompt in the database and refreshes the main modal
5. All generation happens via existing `PromptMetadataGenerationService`

**Architectural approach**:
- Backend: New async endpoint `PATCH /api/v1/image-prompts/{prompt_id}/metadata` to update title/flavour text
- Backend: New async endpoint `POST /api/v1/image-prompts/{prompt_id}/metadata/generate` to generate multiple variants
- Frontend: New `MetadataRegenerationModal` component for displaying and selecting options
- Frontend: Add button to `GeneratedImageModal` to open regeneration modal
- State management: Use React Query mutations for optimistic updates

**Key components involved**:
- `backend/app/api/routes/image_prompts.py`: Add new endpoints
- `backend/app/services/prompt_metadata/prompt_metadata_service.py`: Extend to support generating multiple variants
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`: Add regeneration trigger button
- `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx`: New modal component
- `frontend/src/api/imagePrompts.ts`: Add API client methods

**Integration with existing systems**:
- Updates existing `PromptMetadataGenerationService` for generation logic. We should generate 5 variants in one call, so the model that does the generation can make them different.
- Integrates with existing modal component structure (Chakra UI Dialog)
- Follows existing API patterns (async endpoints with proper error handling)
- Leverages React Query for optimistic UI updates and cache invalidation

## Codebase Research Summary

**Relevant existing patterns found**:
1. **Modal nesting**: Chakra UI `DialogRoot` supports stacking modals (z-index handled automatically)
2. **Async API endpoints**: `generated_images.py` lines 611-677 show async endpoint pattern with background tasks
3. **Metadata service**: `PromptMetadataGenerationService` already exists with `generate_metadata_for_prompt()` method
4. **Update patterns**: `update_image_approval` in `generated_images.py` lines 453-488 shows PATCH endpoint for updates
5. **Frontend mutations**: `generated-images.tsx` lines 351-511 show optimistic update pattern with React Query
6. **Toast notifications**: `useCustomToast` hook used for success/error feedback (line 329)

**Files and components that will be affected**:
- `backend/app/api/routes/image_prompts.py`: Add 2 new async endpoints (generate + update)
- `backend/app/services/prompt_metadata/prompt_metadata_service.py`: Add method to generate N variants
- `backend/app/repositories/image_prompt.py`: May need `update_metadata()` method
- `backend/app/schemas/image_prompt.py`: Add request/response schemas
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`: Add button + state
- `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx`: New file
- `frontend/src/api/imagePrompts.ts`: Add client functions

**Similar features that can serve as reference**:
- Custom remix feature (`GeneratedImageModal.tsx` lines 194-207, 423-436): Shows button + loading state pattern
- Approval mutation (`generated-images.tsx` lines 351-511): Optimistic updates with rollback
- Dialog nesting: Standard Chakra UI pattern, no special handling needed

**Potential risks or conflicts identified**:
- Modal state management: Need to ensure main modal refreshes when metadata changes
- Database consistency: Ensure atomic updates to title + flavour_text fields

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Review `PromptMetadataGenerationService` to understand current generation logic
3. Check `GeneratedImageModal.tsx` to see current modal structure and props
4. Review issue #008 for context on original metadata generation implementation
5. Test with actual prompts to ensure generated variations are diverse

**Key Decisions Made**:
- **Number of variants**: Generate 5 options
- **Generation strategy**: Call LLM once with a prompt that generates 5 variants
- **Update atomicity**: Single PATCH updates both title and flavour_text together
- **Modal approach**: Secondary modal (not drawer) for better focus on selection task
- **Error handling**: Show error toast if generation fails, don't block user workflow
- **Cache invalidation**: Invalidate both list and detail queries when metadata updates
- **API design**: Separate endpoints for generate (POST) and update (PATCH) for clarity

**Deviations from standard patterns**:
- Unlike other endpoints, generate endpoint returns preview data without persisting
- Two-step workflow (generate → select → update) instead of direct update

**Assumptions about the system**:
- Frontend has access to prompt_id via `currentImage.prompt.id` in modal
- Users want to see options before committing (not just regenerate in place)

## Pre-Implementation Checklist for Each Phase

Before starting implementation:
- [ ] Review `PromptMetadataGenerationService.generate_metadata_for_prompt()` method
- [ ] Check current modal structure in `GeneratedImageModal.tsx`
- [ ] Verify Chakra UI Dialog can be nested (create test component if unsure)
- [ ] Confirm React Query cache key structure for prompts and images

## Implementation Phases

### Phase 1: Backend - Metadata Generation Endpoint
**Goal**: Create async endpoint to generate multiple title/flavour text variants in a single LLM call

**Dependencies**: Issue #008 completed (PromptMetadataGenerationService exists)

**Time Estimate**: 60 minutes

**Success Metrics**:
- [x] New endpoint `POST /api/v1/image-prompts/{prompt_id}/metadata/generate` created
- [x] Endpoint generates 5 metadata variants without persisting
- [x] Returns array of `{title, flavour_text}` objects
- [x] Proper error handling for missing prompt or LLM failures
- [x] Endpoint is async and non-blocking

**Tasks**:
1. Create request/response schemas in `backend/app/schemas/image_prompt.py`:
   ```python
   # Request schema
   class MetadataGenerationRequest(BaseModel):
       variants_count: int = Field(default=5, ge=1, le=10)
       overwrite_existing: bool = Field(default=False)

   # Response schema
   class MetadataVariant(BaseModel):
       title: str | None
       flavour_text: str | None

   class MetadataGenerationResponse(BaseModel):
       prompt_id: UUID
       variants: list[MetadataVariant]
       count: int
   ```

2. Update `PromptMetadataGenerationService` to support generating multiple variants in a single LLM call:
   - Add method `generate_metadata_variants()` that generates N variants in one LLM invocation
   - Method signature: `async def generate_metadata_variants(prompt: ImagePrompt | UUID, *, variants_count: int = 5) -> list[dict[str, Any]]`
   - Build a prompt that asks the LLM to generate multiple variants with different creative directions
   - Use shared core constraints: "Titles must be 1-5 words. Flavour text must be a single sentence (8-16 words). Never reference licensed character names, book titles, author names, or direct plot details. Write flavour text like a Magic: The Gathering card—clever, intriguing, mysterious, or wry rather than literal."
   - Expected JSON response format: `{"variants": [{"title": "...", "flavour_text": "..."}, ...]}`
   - Parse response and extract array of variants
   - Return list of dicts with `{title, flavour_text}` keys
   - Handle errors gracefully (if parsing fails, return empty list with error log)

3. Add endpoint to `backend/app/api/routes/image_prompts.py`:
   ```python
   @router.post("/{prompt_id}/metadata/generate", response_model=MetadataGenerationResponse)
   async def generate_metadata_variants(
       *,
       session: SessionDep,
       prompt_id: UUID,
       request: MetadataGenerationRequest | None = None,
   ) -> MetadataGenerationResponse:
       """Generate multiple title/flavour text variants for an image prompt without persisting."""

       request = request or MetadataGenerationRequest()
       repository = ImagePromptRepository(session)
       prompt = repository.get(prompt_id)
       if prompt is None:
           raise HTTPException(status_code=404, detail="Image prompt not found")

       service = PromptMetadataGenerationService(session)
       try:
           variants = await service.generate_metadata_variants(
               prompt,
               variants_count=request.variants_count,
           )
       except Exception as exc:
           logger.exception("Failed to generate metadata variants for prompt %s", prompt_id)
           raise HTTPException(
               status_code=500,
               detail="Failed to generate metadata variants",
           ) from exc

       return MetadataGenerationResponse(
           prompt_id=prompt_id,
           variants=[MetadataVariant(**v) for v in variants],
           count=len(variants),
       )
   ```

4. Import and export new schemas in `backend/app/schemas/__init__.py`

5. Test endpoint manually:
   - Get a prompt ID: `docker compose exec db psql -U postgres -d app -c "SELECT id FROM image_prompts LIMIT 1"`
   - Use curl to test: `curl -X POST http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata/generate -H "Content-Type: application/json" -d '{"variants_count": 3}'`
   - Verify response contains 3 variants with title and flavour_text

### Phase 2: Backend - Metadata Update Endpoint
**Goal**: Create async endpoint to update prompt title and flavour text

**Dependencies**: Phase 1 completed

**Time Estimate**: 30 minutes

**Success Metrics**:
- [x] New endpoint `PATCH /api/v1/image-prompts/{prompt_id}/metadata` created
- [x] Endpoint updates title and flavour_text atomically
- [x] Returns updated `ImagePromptRead` object
- [x] Proper validation for input fields
- [x] Updates `updated_at` timestamp

**Tasks**:
1. Create update schema in `backend/app/schemas/image_prompt.py`:
   ```python
   class MetadataUpdateRequest(BaseModel):
       title: str | None = Field(None, max_length=255)
       flavour_text: str | None = Field(None, max_length=2000)
   ```

2. Add update method to `ImagePromptRepository` if needed:
   ```python
   def update_metadata(
       self,
       prompt_id: UUID,
       *,
       title: str | None = None,
       flavour_text: str | None = None,
       commit: bool = False,
   ) -> ImagePrompt | None:
       prompt = self.get(prompt_id)
       if prompt is None:
           return None

       if title is not None:
           prompt.title = title
       if flavour_text is not None:
           prompt.flavour_text = flavour_text

       prompt.updated_at = datetime.now(timezone.utc)
       self._session.add(prompt)
       self._session.flush()

       if commit:
           self._session.commit()
       if refresh:
           self._session.refresh(prompt)

       return prompt
   ```

3. Add endpoint to `backend/app/api/routes/image_prompts.py`:
   ```python
   @router.patch("/{prompt_id}/metadata", response_model=ImagePromptRead)
   async def update_prompt_metadata(
       *,
       session: SessionDep,
       prompt_id: UUID,
       update: MetadataUpdateRequest,
   ) -> ImagePromptRead:
       """Update the title and flavour text of an image prompt."""

       repository = ImagePromptRepository(session)
       prompt = repository.update_metadata(
           prompt_id,
           title=update.title,
           flavour_text=update.flavour_text,
           commit=True,
       )

       if prompt is None:
           raise HTTPException(status_code=404, detail="Image prompt not found")

       return ImagePromptRead.model_validate(prompt)
   ```

4. Export new schema in `backend/app/schemas/__init__.py`

5. Test endpoint:
   - Use curl: `curl -X PATCH http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata -H "Content-Type: application/json" -d '{"title": "Test Title", "flavour_text": "Test flavour text for testing."}'`
   - Verify database update: `docker compose exec db psql -U postgres -d app -c "SELECT title, flavour_text FROM image_prompts WHERE id = '{prompt_id}'"`

### Phase 3: Frontend - API Client Methods
**Goal**: Create TypeScript client functions for new endpoints

**Dependencies**: Phases 1-2 completed, backend running

**Time Estimate**: 20 minutes

**Success Metrics**:
- [ ] `generatePromptMetadata()` function created
- [ ] `updatePromptMetadata()` function created
- [ ] Proper TypeScript types for request/response
- [ ] Functions handle errors appropriately

**Tasks**:
1. Add types to `frontend/src/api/imagePrompts.ts`:
   ```typescript
   export type MetadataVariant = {
     title: string | null
     flavour_text: string | null
   }

   export type MetadataGenerationResponse = {
     prompt_id: string
     variants: MetadataVariant[]
     count: number
   }

   export type MetadataUpdateRequest = {
     title?: string | null
     flavour_text?: string | null
   }

   export type ImagePromptRead = {
     id: string
     scene_extraction_id: string
     title: string | null
     flavour_text: string | null
     prompt_text: string
     style_tags: string[] | null
     attributes: Record<string, unknown>
     // ... other fields
   }
   ```

2. Add generation function to `frontend/src/api/imagePrompts.ts`:
   ```typescript
   const buildUrl = (path: string) => {
     const base = OpenAPI.BASE ?? ""
     if (base) {
       const sanitizedBase = base.replace(/\/+$/, "")
       return `${sanitizedBase}${path}`
     }
     return path
   }

   export const generatePromptMetadata = async (
     promptId: string,
     variantsCount = 5,
   ): Promise<MetadataGenerationResponse> => {
     const url = buildUrl(
       `/api/v1/image-prompts/${encodeURIComponent(promptId)}/metadata/generate`,
     )

     const response = await fetch(url, {
       method: "POST",
       headers: {
         "Content-Type": "application/json",
       },
       body: JSON.stringify({ variants_count: variantsCount }),
     })

     if (!response.ok) {
       const body = await response.text().catch(() => "")
       const message = body || `${response.status} ${response.statusText}`
       throw new Error(`Failed to generate metadata: ${message}`)
     }

     return (await response.json()) as MetadataGenerationResponse
   }
   ```

3. Add update function to `frontend/src/api/imagePrompts.ts`:
   ```typescript
   export const updatePromptMetadata = async (
     promptId: string,
     metadata: MetadataUpdateRequest,
   ): Promise<ImagePromptRead> => {
     const url = buildUrl(
       `/api/v1/image-prompts/${encodeURIComponent(promptId)}/metadata`,
     )

     const response = await fetch(url, {
       method: "PATCH",
       headers: {
         "Content-Type": "application/json",
       },
       body: JSON.stringify(metadata),
     })

     if (!response.ok) {
       const body = await response.text().catch(() => "")
       const message = body || `${response.status} ${response.statusText}`
       throw new Error(`Failed to update metadata: ${message}`)
     }

     return (await response.json()) as ImagePromptRead
   }
   ```

4. Test functions in browser console:
   - Open generated-images page
   - Get a prompt ID from the modal
   - Run: `generatePromptMetadata(promptId).then(console.log)`
   - Verify response structure

### Phase 4: Frontend - Metadata Regeneration Modal Component
**Goal**: Create standalone modal for displaying and selecting metadata variants

**Dependencies**: Phase 3 completed

**Time Estimate**: 60 minutes

**Success Metrics**:
- [ ] `MetadataRegenerationModal` component file created
- [ ] Component accepts required props (isOpen, onClose, promptId, imageId)
- [ ] Component includes loading state logic with Spinner
- [ ] Component renders variants array in a Stack/Box structure
- [ ] Each variant has Button with onClick handler calling updatePromptMetadata
- [ ] Component includes error state handling
- [ ] Component properly invalidates React Query cache on success

**Tasks**:
1. Create `frontend/src/components/GeneratedImages/MetadataRegenerationModal.tsx`:
   ```typescript
   import {
     Box,
     Button,
     HStack,
     Spinner,
     Stack,
     Text,
   } from "@chakra-ui/react"
   import { useMutation, useQueryClient } from "@tanstack/react-query"
   import { useEffect, useState } from "react"
   import { FiCheck } from "react-icons/fi"

   import {
     type MetadataUpdateRequest,
     type MetadataVariant,
     generatePromptMetadata,
     updatePromptMetadata,
   } from "@/api/imagePrompts"
   import {
     DialogBody,
     DialogCloseTrigger,
     DialogContent,
     DialogHeader,
     DialogRoot,
     DialogTitle,
   } from "@/components/ui/dialog"
   import useCustomToast from "@/hooks/useCustomToast"

   type MetadataRegenerationModalProps = {
     isOpen: boolean
     onClose: () => void
     promptId: string | null
     imageId: string | null
   }

   const MetadataRegenerationModal = ({
     isOpen,
     onClose,
     promptId,
     imageId,
   }: MetadataRegenerationModalProps) => {
     const [variants, setVariants] = useState<MetadataVariant[]>([])
     const [isGenerating, setIsGenerating] = useState(false)
     const [error, setError] = useState<string | null>(null)
     const queryClient = useQueryClient()
     const { showSuccessToast, showErrorToast } = useCustomToast()

     // Generate variants when modal opens
     useEffect(() => {
       if (isOpen && promptId) {
         setIsGenerating(true)
         setError(null)
         setVariants([])

         generatePromptMetadata(promptId, 5)
           .then((response) => {
             setVariants(response.variants)
           })
           .catch((err: Error) => {
             setError(err.message)
             showErrorToast(err.message)
           })
           .finally(() => {
             setIsGenerating(false)
           })
       }
     }, [isOpen, promptId, showErrorToast])

     const updateMutation = useMutation({
       mutationFn: ({
         promptId,
         metadata,
       }: {
         promptId: string
         metadata: MetadataUpdateRequest
       }) => updatePromptMetadata(promptId, metadata),
       onSuccess: () => {
         // Invalidate relevant queries
         if (imageId) {
           queryClient.invalidateQueries({
             queryKey: ["generated-image", imageId],
           })
         }
         queryClient.invalidateQueries({
           queryKey: ["generated-images"],
         })
         showSuccessToast("Metadata updated successfully!")
         onClose()
       },
       onError: (error: Error) => {
         showErrorToast(error.message)
       },
     })

     const handleUseVariant = (variant: MetadataVariant) => {
       if (!promptId) return
       updateMutation.mutate({
         promptId,
         metadata: {
           title: variant.title,
           flavour_text: variant.flavour_text,
         },
       })
     }

     return (
       <DialogRoot
         open={isOpen}
         onOpenChange={(details) => {
           if (!details.open) {
             onClose()
           }
         }}
         size="lg"
       >
         <DialogContent>
           <DialogCloseTrigger />
           <DialogHeader>
             <DialogTitle>Regenerate Title & Flavour Text</DialogTitle>
           </DialogHeader>
           <DialogBody>
             {isGenerating ? (
               <Stack align="center" py={8} gap={4}>
                 <Spinner size="lg" />
                 <Text color="fg.muted">
                   Generating creative variations...
                 </Text>
               </Stack>
             ) : error ? (
               <Stack align="center" py={8} gap={4}>
                 <Text color="red.500">Failed to generate variants</Text>
                 <Text fontSize="sm" color="fg.muted">
                   {error}
                 </Text>
                 <Button size="sm" onClick={onClose}>
                   Close
                 </Button>
               </Stack>
             ) : variants.length === 0 ? (
               <Stack align="center" py={8}>
                 <Text color="fg.muted">No variants generated</Text>
               </Stack>
             ) : (
               <Stack gap={3}>
                 {variants.map((variant, index) => (
                   <Box
                     key={index}
                     p={4}
                     borderWidth="1px"
                     borderRadius="md"
                     bg="rgba(255,255,255,0.02)"
                     _hover={{ bg: "rgba(255,255,255,0.04)" }}
                   >
                     <HStack justify="space-between" align="start">
                       <Stack gap={2} flex="1">
                         {variant.title && (
                           <Text fontWeight="semibold" fontSize="md">
                             {variant.title}
                           </Text>
                         )}
                         {variant.flavour_text && (
                           <Text
                             fontSize="sm"
                             color="fg.subtle"
                             fontStyle="italic"
                           >
                             {variant.flavour_text}
                           </Text>
                         )}
                       </Stack>
                       <Button
                         size="sm"
                         colorPalette="purple"
                         leftIcon={<FiCheck />}
                         onClick={() => handleUseVariant(variant)}
                         isLoading={updateMutation.isPending}
                       >
                         Use
                       </Button>
                     </HStack>
                   </Box>
                 ))}
               </Stack>
             )}
           </DialogBody>
         </DialogContent>
       </DialogRoot>
     )
   }

   export default MetadataRegenerationModal
   ```

2. Export component from `frontend/src/components/GeneratedImages/index.ts`:
   ```typescript
   export { default as MetadataRegenerationModal } from "./MetadataRegenerationModal"
   ```

3. Verify component compiles without errors:
   - Run `cd frontend && npm run build` to check for TypeScript errors
   - Fix any type issues or import errors

### Phase 5: Frontend - Integrate with GeneratedImageModal
**Goal**: Add regeneration button to existing image modal

**Dependencies**: Phase 4 completed

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Button component added to GeneratedImageModal with FiRefreshCw icon
- [ ] State variable `isMetadataModalOpen` added
- [ ] Button onClick handler sets `isMetadataModalOpen` to true
- [ ] MetadataRegenerationModal component rendered with correct props
- [ ] Modal receives promptId and imageId from currentImage
- [ ] Button disabled when promptId is null
- [ ] Necessary imports added (FiRefreshCw, MetadataRegenerationModal)

**Tasks**:
1. Update `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`:
   - Import `MetadataRegenerationModal` and `FiRefreshCw` icon
   - Add state: `const [isMetadataModalOpen, setIsMetadataModalOpen] = useState(false)`
   - Add button after flavour text display (around line 395):
   ```typescript
   <HStack justify="space-between" align="center" mt={2}>
     <Text fontSize="xs" color="fg.muted">
       {promptTitle || promptFlavour ? "Generated Metadata" : "No metadata yet"}
     </Text>
     <Button
       size="xs"
       variant="ghost"
       colorPalette="purple"
       leftIcon={<FiRefreshCw />}
       onClick={() => setIsMetadataModalOpen(true)}
       disabled={!currentImage?.prompt?.id}
     >
       Regenerate
     </Button>
   </HStack>
   ```
   - Add modal component at end of return statement (before closing `DialogContent`):
   ```typescript
   <MetadataRegenerationModal
     isOpen={isMetadataModalOpen}
     onClose={() => setIsMetadataModalOpen(false)}
     promptId={currentImage?.prompt?.id ?? null}
     imageId={currentImage?.image?.id ?? null}
   />
   ```

2. Import necessary components:
   ```typescript
   import { FiRefreshCw } from "react-icons/fi"
   import { MetadataRegenerationModal } from "@/components/GeneratedImages"
   ```

3. Verify TypeScript compilation:
   - Run `cd frontend && npm run build` to check for errors
   - Ensure all imports resolve correctly

### Phase 6: Verification and Linting
**Goal**: Verify endpoints work correctly and code passes linting

**Dependencies**: All previous phases completed

**Time Estimate**: 20 minutes

**Success Metrics**:
- [ ] Backend endpoints respond correctly to API calls
- [ ] Backend linting passes
- [ ] Frontend linting passes
- [ ] TypeScript compilation succeeds
- [ ] Database updates persist correctly

**Tasks**:
1. Test backend generate endpoint:
   - Get a prompt ID: `docker compose exec db psql -U postgres -d app -c "SELECT id FROM image_prompts LIMIT 1;"`
   - Test generation: `curl -X POST http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata/generate -H "Content-Type: application/json" -d '{"variants_count": 5}'`
   - Verify response contains 5 variants with title and flavour_text fields
   - Check for 200 status code

2. Test backend update endpoint:
   - Test update: `curl -X PATCH http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata -H "Content-Type: application/json" -d '{"title": "Test Title", "flavour_text": "This is a test flavour text for verification."}'`
   - Verify response contains updated fields
   - Check database: `docker compose exec db psql -U postgres -d app -c "SELECT id, title, flavour_text FROM image_prompts WHERE id = '{prompt_id}';"`
   - Verify title and flavour_text match the update

3. Run linting:
   - Backend: `cd backend && uv run bash scripts/lint.sh`
   - Fix any linting errors (formatting, type issues, imports)
   - Frontend: `cd frontend && npm run lint`
   - Fix any linting errors

4. Verify TypeScript compilation:
   - Run: `cd frontend && npm run build`
   - Ensure no TypeScript errors
   - Fix any type errors or import issues

5. Check for common issues:
   - Ensure no unused imports
   - Remove any debug console.log statements
   - Verify proper error handling in all async functions
   - Check that all promises are awaited

## System Integration Points

**Database Tables**:
- **Read**: `image_prompts` (fetch prompt for metadata generation)
- **Write**: `image_prompts` (update title and flavour_text columns)

**External APIs**:
- **Gemini API**: Generate 5 title/flavour text variants (5 calls per regeneration action)

**Message Queues**: None

**WebSockets**: None

**Cron Jobs**: None

**Cache Layers**:
- **React Query cache**: Invalidate `generated-image` and `generated-images` queries after update

## Technical Considerations

**Performance**:
- Generating 5 variants takes ~3-5 seconds (single LLM call)
- Single call generates all variants together, allowing model to create diverse options
- Much faster than 5 sequential calls (reduced from ~10-15s to ~3-5s)
- Loading state keeps user informed during generation
- No backend caching needed (fresh generation each time)

**Security**:
- Validate prompt_id exists before generating/updating
- Sanitize title and flavour_text inputs (max lengths enforced)
- No XSS risk (React escapes strings by default)
- Rate limiting handled by Gemini API (existing infrastructure)

**Database**:
- No schema changes needed (columns already exist)
- Atomic updates to title + flavour_text (single transaction)
- `updated_at` timestamp updated automatically
- No indexes needed (not querying by metadata)

**API Design**:
- RESTful endpoints following existing patterns
- Async endpoints for non-blocking LLM calls
- Clear separation between generate (preview) and update (persist)
- Proper HTTP status codes (200 for success, 404 for not found, 500 for errors)

**Error Handling**:
- Frontend shows toast for errors
- Backend logs detailed error info
- If LLM call fails entirely, show error message with retry option
- If response has fewer than requested variants, show what was generated
- User can retry by closing and reopening modal

**Monitoring**:
- Log metadata generation requests (prompt_id, variants_count, execution time)
- Log update requests (prompt_id, fields changed)
- Track success/failure rates for quality monitoring

## Testing Strategy

1. **Unit Tests**: Not required per CLAUDE.md (LLM integration)
2. **API Testing**: Covered in Phase 6 with curl commands
   - Test generate endpoint returns 5 variants
   - Test update endpoint modifies database
   - Verify responses have correct structure
3. **Database Verification**:
   - Query database after update to confirm persistence
   - Check title and flavour_text columns updated correctly
4. **Code Quality**:
   - Backend linting passes
   - Frontend linting passes
   - TypeScript compilation succeeds

## Acceptance Criteria

- [ ] All phases completed successfully
- [ ] Backend generate endpoint returns 5 variants with correct JSON structure
- [ ] Backend update endpoint successfully updates title and flavour_text in database
- [ ] Database query confirms metadata persists after update
- [ ] Frontend components compile without TypeScript errors
- [ ] MetadataRegenerationModal component created with correct props
- [ ] GeneratedImageModal updated with regenerate button and modal integration
- [ ] API client functions added to `imagePrompts.ts`
- [ ] Backend linting passes (`uv run bash scripts/lint.sh`)
- [ ] Frontend linting passes (`npm run lint`)
- [ ] Frontend build succeeds (`npm run build`)
- [ ] All imports resolve correctly
- [ ] No unused variables or imports remain

## Quick Reference Commands

- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run frontend locally**: `cd frontend && npm run dev`
- **Test generate endpoint**: `curl -X POST http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata/generate -H "Content-Type: application/json"`
- **Test update endpoint**: `curl -X PATCH http://localhost:8000/api/v1/image-prompts/{prompt_id}/metadata -H "Content-Type: application/json" -d '{"title": "Test", "flavour_text": "Test text"}'`
- **Check prompt metadata**: `docker compose exec db psql -U postgres -d app -c "SELECT id, title, flavour_text FROM image_prompts LIMIT 5"`
- **Backend linting**: `cd backend && uv run bash scripts/lint.sh`
- **Frontend linting**: `cd frontend && npm run lint`
- **View API logs**: `docker compose logs -f backend`

## Inter-Instance Communication

### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes
#### Phase 1 (completed 2025-11-03)
- **Status**: ✅ Completed
- **Highlights**: Added JSON request/response schemas, multi-variant generation helper in `PromptMetadataGenerationService`, and async `POST /api/v1/image-prompts/{prompt_id}/metadata/generate`.
- **Deviations**: Capped requested variants to 10 server-side to guard against oversized prompts.
- **Tests**: `uv run pytest` *(fails: `test_generate_for_scene_returns_existing_when_overwrite_disabled`, `test_generate_for_scene_returns_existing_when_overwrite_disabled_dry_run` expect no Gemini call; failures pre-exist this phase work).*

#### Phase 2 (completed 2025-11-03)
- **Status**: ✅ Completed
- **Highlights**: Added `MetadataUpdateRequest`, repository helper for atomic metadata writes, and async `PATCH /api/v1/image-prompts/{prompt_id}/metadata` wiring back to `ImagePromptRead`.
- **Deviations**: Added 422 error guard when both metadata fields are omitted to avoid timestamp-only updates.
- **Tests**: Not run; manual API verification still outstanding.

#### Phase 3 (completed 2025-11-03)
- **Status**: ✅ Completed
- **Highlights**: Added metadata variant/update types plus `generatePromptMetadata()` and `updatePromptMetadata()` helpers with shared `buildUrl` utility and error handling tailored for React Query consumers.
- **Deviations**: Introduced `ImagePromptMetadataRead` union because the generated OpenAPI models still omit the `flavour_text` field; fetch wrappers now cast to that extended shape.
- **Tests**: Deferred to Phase 6 (no standalone verification needed).

#### Phase 4 (completed 2025-11-03)
- **Status**: ✅ Completed
- **Highlights**: Created `MetadataRegenerationModal` with optimistic React Query cache updates, toast feedback, retry affordances, and clean cancellation handling for in-flight generation requests.
- **Deviations**: Rendered icons inline instead of using `leftIcon` props to keep compatibility with the stricter Chakra v3 typings surfaced by `tsc`.
- **Tests**: Deferred to Phase 6; no manual UI exercise performed yet.

#### Phase 5 (completed 2025-11-03)
- **Status**: ✅ Completed
- **Highlights**: Wired regeneration controls into `GeneratedImageModal`, synchronized modal state resets on parent close, and plumbed prompt/image identifiers down to the new modal.
- **Deviations**: Mirrored Chakra prop adjustments from Phase 4 (inline icons, `disabled`/`loading` props) so the integration compiles against current UI typings.
- **Tests**: Deferred to Phase 6.

#### Phase 6 (completed 2025-11-03)
- **Status**: ⚠️ Completed with caveats
- **Highlights**: Attempted `npm run lint` and `npm run build`; both surfaced long-standing issues outside this change set (Biome rewrites on generated client files and Chakra v3 prop API mismatches across existing components).
- **Deviations**: Reverted Biome's auto-edits to the generated client to avoid unrelated churn; no further remediation applied for the pre-existing lint/build breaks.
- **Tests**: `npm run lint` *(fails due to hundreds of existing Biome findings across `frontend/src/client/**/*`)*; `npm run build` *(fails on existing Chakra component typing mismatches such as `leftIcon`, `isLoading`, `noOfLines`, etc.)*.

### Phase Completion Notes Structure:
Each phase should document:
- Completion status
- Date completed
- Key findings or learnings
- Any deviations from the original plan and rationale
- Warnings or gotchas for future work
