# Image Approval and Rejection System

## Overview
Implement a user approval system for generated images in the SceneDream gallery, allowing users to approve (thumbs up) or reject (thumbs down) images directly in the UI. Add database columns to track approval status, create API endpoints for updating approval state, and enhance the frontend gallery with thumbs up/down buttons and filtering capabilities.

## Problem Statement

**Current limitations:**
- Generated images have no quality curation mechanism—users can't mark good vs. bad outputs
- No way to filter images by approval status in the gallery
- Difficult to identify which images to use for final outputs or further refinement
- No feedback loop for understanding which prompts/styles produce better results

**User impact:**
- Manual tracking required (external notes, separate files) to remember which images are keepers
- Time-consuming to revisit the gallery and re-evaluate images
- Inability to quickly filter to "approved" images for export or sharing
- Lost context when returning to the gallery after time away

**Business value of solving this:**
- Enable quality curation workflow: approve best images, reject poor ones
- Support filtering to quickly find approved images
- Provide data for future prompt/model optimization (understand what works)
- Improve UX by allowing in-place decisions without external tools
- Build foundation for future features (bulk export approved images, prompt analysis by approval rate)

## Proposed Solution

### High-Level Approach
Add an **approval status system** to the `generated_images` table with three states:
1. **`null` (pending)**: Default state, no decision made yet
2. **`true` (approved)**: User gave thumbs up, high-quality image
3. **`false` (rejected)**: User gave thumbs down, low-quality image

Implement backend API endpoints to update approval status and filter by approval state. Enhance frontend gallery with thumbs up/down button controls on both the card view and modal view, plus filtering dropdown to show only approved, rejected, or pending images.

### Key Components

**Backend Changes:**
- Add `user_approved: bool | None` column to `generated_images` table (nullable, default None)
- Add `approval_updated_at: datetime | None` column to track when approval status was set
- Create `PATCH /api/generated-images/{id}/approval` endpoint to update approval status
- Extend `GET /api/generated-images` to accept `approval` query parameter for filtering

**Frontend Changes:**
- Add thumbs up/down icon buttons to `GeneratedImageCard` component
- Add thumbs up/down buttons to `GeneratedImageModal` component (context panel)
- Add approval filter dropdown to `GeneratedImagesFilters` component
- Update search schema and API calls to pass approval filter
- Add visual indicators for approval state (green/red borders, badge colors)
- Implement optimistic UI updates with TanStack Query mutations

### Integration with Existing Systems
- **Database**: Extend `generated_images` table with 2 new nullable columns (backward compatible)
- **Repository**: Add `GeneratedImageRepository.update_approval()` method
- **API Routes**: Add new PATCH endpoint in `backend/app/api/routes/generated_images.py`
- **API Schemas**: Add `GeneratedImageApprovalUpdate` request schema and extend list filters
- **Frontend Client**: Regenerate TypeScript client after OpenAPI schema update
- **UI Components**: Extend existing `GeneratedImageCard` and `GeneratedImageModal` components

## Codebase Research Summary

**Relevant existing patterns found:**

1. **Update endpoint patterns** (`backend/app/api/routes/users.py:78-100`):
   - Use `@router.patch()` for partial updates
   - Accept specific update schemas (e.g., `UserUpdateMe`)
   - Return updated model with `response_model`
   - Pattern: `repository.update(id, data)` → `session.commit()` → return

2. **Query filtering patterns** (`backend/app/api/routes/generated_images.py:78-156`):
   - Use `Query()` parameters for filters (e.g., `book: str | None = Query(None)`)
   - Route to appropriate repository method based on filters
   - Return metadata dict with applied filters in response

3. **Repository update patterns** (`backend/app/repositories/generated_image.py:223-239`):
   - `mark_failed()` method shows update pattern: get record, modify fields, flush, commit, refresh
   - Use `commit` parameter for transaction control
   - Return updated record after refresh

4. **Frontend mutation patterns** (observed in codebase):
   - TanStack Query `useMutation` for POST/PATCH operations
   - Optimistic updates with `onMutate` and rollback on error
   - Invalidate query keys on success to refresh data

5. **Modal/Card component patterns** (`frontend/src/components/GeneratedImages/`):
   - `GeneratedImageCard` uses Chakra UI `Box`, `Badge`, `Image`
   - `GeneratedImageModal` has context panel on right side with metadata
   - Both use `onClick` handlers for user interactions
   - Props pass callbacks up to parent component

**Files and components that will be affected:**
- `backend/models/generated_image.py` (add columns)
- `backend/app/repositories/generated_image.py` (add update method, extend list queries)
- `backend/app/api/routes/generated_images.py` (add PATCH endpoint, extend list filters)
- `backend/app/schemas/generated_image.py` (add update request schema)
- `backend/app/alembic/versions/` (migration for new columns)
- `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx` (add buttons)
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` (add buttons)
- `frontend/src/routes/_layout/generated-images.tsx` (add filter UI, mutations)
- `frontend/src/api/generatedImages.ts` (add update method)

**Similar features as reference:**
- Scene rankings: Multi-stage pipeline with metadata persistence
- Image prompt variants: Multiple records per scene with indexed filtering
- Scene extraction filters: Book/chapter dropdown filtering in frontend

**Potential risks identified:**
- **Concurrent updates**: Two users (future multi-user) could race—use optimistic locking if needed
- **Frontend state sync**: Approval state must update in both card grid and modal simultaneously
- **Filter state management**: URL params must sync with filter UI correctly
- **Migration safety**: Nullable columns prevent data loss on existing records

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check the latest `generated_images` table schema in `backend/models/generated_image.py`
3. Review the existing PATCH endpoints in `backend/app/api/routes/` for update patterns
4. Test with actual images in the gallery (ensure images exist first)
5. Verify that frontend client regeneration completes successfully

**Key Decisions Made**:
- **Tri-state approval**: `null` (pending), `true` (approved), `false` (rejected) allows filtering for "not yet decided"
- **Separate timestamp**: `approval_updated_at` field enables tracking when decisions were made (useful for analytics)
- **RESTful endpoint**: `PATCH /api/generated-images/{id}/approval` rather than custom action endpoints
- **No cascade delete**: Approval data lives with image record, no separate approval table
- **UI placement**: Buttons in both card (quick decision) and modal (detailed review) for flexibility
- **Optimistic updates**: Frontend shows approval immediately, rolls back on error for snappy UX

**Assumptions about the system**:
- Single-user system (no authentication required for approval actions)
- Approval status is user preference, not tied to specific prompts/models
- Images are not shared between users (approval is global per image)
- Approval status persists across sessions
- No need for approval history/audit log (current state is sufficient)

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify generated images exist in DB (`SELECT COUNT(*) FROM generated_images;`)
- [ ] Check current schema for `generated_images` table
- [ ] Review latest Alembic migrations
- [ ] Ensure frontend dev server runs successfully
- [ ] Test existing image gallery loads correctly

## Implementation Phases

### Phase 1: Database Schema Extension (30 min)
**Goal**: Add approval status columns to `generated_images` table

**Dependencies**: None (independent schema change)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Migration runs successfully with `alembic upgrade head`
- [ ] New columns appear in `generated_images` table
- [ ] Existing image records remain intact with `user_approved = NULL`
- [ ] Can insert and query new fields via SQLModel

**Tasks**:
1. **Add new fields to `GeneratedImage` model** in `backend/models/generated_image.py` (after line 89):
   ```python
   user_approved: bool | None = Field(
       default=None,
       sa_column=Column(Boolean, nullable=True),
   )
   approval_updated_at: datetime | None = Field(
       default=None,
       sa_column=Column(DateTime(timezone=True), nullable=True),
   )
   ```

2. **Create Alembic migration**:
   ```bash
   cd backend
   uv run alembic revision -m "add_image_approval_columns"
   ```

3. **Edit generated migration** in `backend/app/alembic/versions/` to add columns:
   ```python
   def upgrade() -> None:
       op.add_column(
           "generated_images",
           sa.Column("user_approved", sa.Boolean(), nullable=True),
       )
       op.add_column(
           "generated_images",
           sa.Column(
               "approval_updated_at",
               sa.DateTime(timezone=True),
               nullable=True,
           ),
       )

   def downgrade() -> None:
       op.drop_column("generated_images", "approval_updated_at")
       op.drop_column("generated_images", "user_approved")
   ```

4. **Run migration**:
   ```bash
   uv run alembic upgrade head
   ```

5. **Verify schema change**:
   ```bash
   docker compose exec db psql -U postgres -d app -c "\d generated_images"
   ```

6. **Test model in Python REPL**:
   ```python
   from models.generated_image import GeneratedImage
   from datetime import datetime, timezone

   # Should instantiate without errors
   img = GeneratedImage(
       # ... existing required fields ...
       user_approved=True,
       approval_updated_at=datetime.now(timezone.utc),
   )
   ```

**Risk Mitigation**:
- Nullable columns preserve backward compatibility with existing images
- No indexes needed initially (low query volume, can add later if needed)
- Keep migration reversible for safety

---

### Phase 2: Backend Repository and API Endpoints (45 min)
**Goal**: Implement backend logic to update approval status and filter by approval state

**Dependencies**: Phase 1 complete (schema exists)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] `GeneratedImageRepository.update_approval()` method works correctly
- [ ] PATCH endpoint updates approval status and returns updated record
- [ ] GET endpoint filters by approval status (approved, rejected, pending)
- [ ] API returns camelCase JSON fields (`userApproved`, `approvalUpdatedAt`)
- [ ] Manual curl tests pass

**Tasks**:
1. **Add update method to `GeneratedImageRepository`** in `backend/app/repositories/generated_image.py` (after `mark_failed` method, around line 240):
   ```python
   def update_approval(
       self,
       image_id: UUID,
       approved: bool | None,
       *,
       commit: bool = False,
   ) -> GeneratedImage | None:
       """Update the approval status of a generated image."""
       image = self.get(image_id)
       if image:
           from datetime import datetime, timezone
           image.user_approved = approved
           image.approval_updated_at = datetime.now(timezone.utc)
           self._session.add(image)
           self._session.flush()
           if commit:
               self._session.commit()
           self._session.refresh(image)
       return image
   ```

2. **Extend `list_for_book()` method** to accept `approval` filter (around line 102):
   ```python
   def list_for_book(
       self,
       book_slug: str,
       *,
       chapter_number: int | None = None,
       provider: str | None = None,
       model: str | None = None,
       approval: bool | None = None,  # New parameter
       newest_first: bool = True,
       # ... rest of params ...
   ) -> list[GeneratedImage]:
       statement = select(GeneratedImage).where(GeneratedImage.book_slug == book_slug)

       # ... existing filters ...

       if approval is not None:
           statement = statement.where(GeneratedImage.user_approved == approval)

       # ... rest of method unchanged ...
   ```

3. **Create approval update schema** in `backend/app/schemas/generated_image.py` (after `GeneratedImageCreate`, around line 41):
   ```python
   class GeneratedImageApprovalUpdate(BaseModel):
       """Schema for updating image approval status."""

       user_approved: bool | None = Field(
           ...,
           description="Approval status: true (approved), false (rejected), null (clear approval)",
       )
   ```

4. **Update `GeneratedImageRead` schema** to include new fields (around line 48):
   ```python
   class GeneratedImageRead(GeneratedImageBase):
       """Detailed representation of a generated image."""

       id: UUID
       created_at: datetime
       updated_at: datetime
       user_approved: bool | None = None
       approval_updated_at: datetime | None = None

       model_config = ConfigDict(from_attributes=True)
   ```

5. **Add PATCH endpoint** in `backend/app/api/routes/generated_images.py` (after `get_generated_image`, around line 188):
   ```python
   @router.patch("/{image_id}/approval", response_model=GeneratedImageRead)
   def update_image_approval(
       *,
       session: SessionDep,
       image_id: UUID,
       update: GeneratedImageApprovalUpdate,
   ) -> GeneratedImageRead:
       """Update the approval status of a generated image."""

       repository = GeneratedImageRepository(session)
       image = repository.update_approval(
           image_id,
           update.user_approved,
           commit=True,
       )

       if image is None:
           raise HTTPException(status_code=404, detail="Generated image not found")

       return GeneratedImageRead.model_validate(image)
   ```

6. **Update list endpoint** to accept approval filter (around line 82):
   ```python
   @router.get("", response_model=GeneratedImageListResponse)
   def list_generated_images(
       *,
       session: SessionDep,
       book: str | None = Query(None, min_length=1),
       chapter: int | None = Query(None, ge=0),
       scene_id: UUID | None = Query(None),
       prompt_id: UUID | None = Query(None),
       provider: str | None = Query(None, min_length=1),
       model: str | None = Query(None, min_length=1),
       approval: bool | None = Query(None),  # New parameter
       newest_first: bool = Query(True),
       limit: int = Query(_DEFAULT_LIST_LIMIT, ge=1, le=_MAX_LIST_LIMIT),
       offset: int | None = Query(None, ge=0),
   ) -> GeneratedImageListResponse:
       # ... existing logic ...

       elif book is not None:
           # List by book (and optionally chapter)
           images = repository.list_for_book(
               book,
               chapter_number=chapter,
               provider=provider,
               model=model,
               approval=approval,  # Pass new filter
               newest_first=newest_first,
               limit=limit,
               offset=offset,
           )

       # ... in meta dict assembly (around line 150):
       if approval is not None:
           meta["approval"] = approval
   ```

7. **Export new schema** in `backend/app/schemas/__init__.py`:
   ```python
   from app.schemas.generated_image import (
       GeneratedImageApprovalUpdate,  # Add this
       # ... existing exports ...
   )
   ```

8. **Test with curl**:
   ```bash
   # Get an image ID
   IMAGE_ID=$(docker compose exec db psql -U postgres -d app -t -c \
     "SELECT id FROM generated_images LIMIT 1;")

   # Approve image
   curl -X PATCH http://localhost:8000/api/generated-images/${IMAGE_ID}/approval \
     -H "Content-Type: application/json" \
     -d '{"user_approved": true}' | jq

   # Reject image
   curl -X PATCH http://localhost:8000/api/generated-images/${IMAGE_ID}/approval \
     -H "Content-Type: application/json" \
     -d '{"user_approved": false}' | jq

   # Clear approval
   curl -X PATCH http://localhost:8000/api/generated-images/${IMAGE_ID}/approval \
     -H "Content-Type: application/json" \
     -d '{"user_approved": null}' | jq

   # Filter approved images
   curl "http://localhost:8000/api/generated-images?book=excession-iain-m-banks&approval=true" | jq
   ```

9. **Run linting**:
   ```bash
   cd backend
   uv run bash scripts/lint.sh
   ```

**Risk Mitigation**:
- Validate `image_id` exists before update (404 if not found)
- Use `commit=True` in endpoint to ensure changes persist
- Return full `GeneratedImageRead` schema for frontend consumption

---

### Phase 3: Frontend TypeScript Client Regeneration (10 min)
**Goal**: Regenerate OpenAPI client with new approval endpoints and schemas

**Dependencies**: Phase 2 complete (API updated)

**Time Estimate**: 10 minutes

**Success Metrics**:
- [ ] TypeScript client generation completes without errors
- [ ] New `updateImageApproval` method exists in `GeneratedImageApi`
- [ ] `GeneratedImageRead` type includes `userApproved` and `approvalUpdatedAt`
- [ ] List method accepts `approval` parameter
- [ ] No TypeScript compilation errors

**Tasks**:
1. **Ensure backend is running**:
   ```bash
   docker compose up -d backend
   docker compose logs -f backend
   # Wait for "Application startup complete"
   ```

2. **Regenerate client**:
   ```bash
   cd frontend
   ./scripts/generate-client.sh
   ```

3. **Verify generated types** in `frontend/src/client/`:
   - Check `models/GeneratedImageRead.ts` has `userApproved?: boolean | null` and `approvalUpdatedAt?: string | null`
   - Check `services/GeneratedImageApi.ts` has `updateImageApproval` method
   - Check list methods accept `approval?: boolean | null` parameter

4. **Test TypeScript compilation**:
   ```bash
   npm run build
   ```

5. **If generation fails**, troubleshoot:
   - Check backend OpenAPI spec: `curl http://localhost:8000/openapi.json | jq`
   - Verify schemas are exported in `backend/app/schemas/__init__.py`
   - Check FastAPI router includes new endpoint

**Risk Mitigation**:
- Keep backend running during generation (client pulls from OpenAPI spec)
- Commit generated client files to git for traceability
- Roll back if generation produces errors

---

### Phase 4: Frontend Gallery Card Component (30 min)
**Goal**: Add thumbs up/down buttons to `GeneratedImageCard` with visual feedback

**Dependencies**: Phase 3 complete (TypeScript client updated)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Thumbs up/down buttons appear on image cards
- [ ] Buttons are visually distinct and accessible
- [ ] Clicking buttons calls `onApprovalChange` callback with new state
- [ ] Visual indicators show approval state (green border for approved, red for rejected)
- [ ] Hover states and disabled states work correctly

**Tasks**:
1. **Update `GeneratedImageCard` props** in `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx` (around line 13):
   ```typescript
   type GeneratedImageCardProps = {
     image: GeneratedImageRead
     onClick: () => void
     onApprovalChange?: (imageId: string, approved: boolean | null) => void
   }

   const GeneratedImageCard = ({
     image,
     onClick,
     onApprovalChange
   }: GeneratedImageCardProps) => {
   ```

2. **Add approval state visual indicator** (around line 27, update Box component):
   ```typescript
   <Box
     borderWidth="1px"
     borderRadius="lg"
     overflow="hidden"
     bg="bg.surface"
     shadow="sm"
     cursor="pointer"
     onClick={onClick}
     transition="all 0.2s"
     borderColor={
       image.user_approved === true
         ? "green.500"
         : image.user_approved === false
           ? "red.500"
           : "border"
     }
     _hover={{
       shadow: "md",
       transform: "translateY(-2px)",
     }}
     display="flex"
     flexDirection="column"
   >
   ```

3. **Add approval buttons** (after metadata HStack, around line 94):
   ```typescript
   import { FiThumbsUp, FiThumbsDown } from "react-icons/fi"

   // ... in return statement, after the badges HStack:

   {onApprovalChange && (
     <HStack gap={2} justify="center" pt={1}>
       <IconButton
         aria-label="Approve image"
         size="sm"
         variant={image.user_approved === true ? "solid" : "ghost"}
         colorPalette={image.user_approved === true ? "green" : "gray"}
         onClick={(e) => {
           e.stopPropagation()
           onApprovalChange(
             image.id,
             image.user_approved === true ? null : true
           )
         }}
       >
         <FiThumbsUp />
       </IconButton>
       <IconButton
         aria-label="Reject image"
         size="sm"
         variant={image.user_approved === false ? "solid" : "ghost"}
         colorPalette={image.user_approved === false ? "red" : "gray"}
         onClick={(e) => {
           e.stopPropagation()
           onApprovalChange(
             image.id,
             image.user_approved === false ? null : false
           )
         }}
       >
         <FiThumbsDown />
       </IconButton>
     </HStack>
   )}
   ```

4. **Add imports** at top of file:
   ```typescript
   import { IconButton } from "@chakra-ui/react"
   import { FiThumbsUp, FiThumbsDown } from "react-icons/fi"
   ```

5. **Test component** by running frontend:
   ```bash
   cd frontend
   npm run dev
   # Visit http://localhost:5173 and check gallery
   ```

**Risk Mitigation**:
- Use `e.stopPropagation()` to prevent card click when clicking buttons
- Toggle approval on click (clicking again clears approval)
- Only render buttons if `onApprovalChange` callback provided

---

### Phase 5: Frontend Modal Component (20 min)
**Goal**: Add thumbs up/down buttons to `GeneratedImageModal` context panel

**Dependencies**: Phase 4 complete (card buttons working)

**Time Estimate**: 20 minutes

**Success Metrics**:
- [ ] Approval buttons appear in modal context panel
- [ ] Buttons sync with card state (both show same approval status)
- [ ] Clicking modal buttons updates approval state
- [ ] Visual feedback matches card component styling
- [ ] Modal doesn't close when clicking approval buttons

**Tasks**:
1. **Update `GeneratedImageModal` props** in `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` (around line 25):
   ```typescript
   type GeneratedImageModalProps = {
     isOpen: boolean
     onClose: () => void
     imageId: string | null
     sceneId: string | null
     allImages?: Array<{ id: string; scene_extraction_id: string }>
     onNavigate?: (imageId: string, sceneId: string) => void
     onApprovalChange?: (imageId: string, approved: boolean | null) => void
   }

   const GeneratedImageModal = ({
     isOpen,
     onClose,
     imageId,
     sceneId,
     allImages = [],
     onNavigate,
     onApprovalChange,
   }: GeneratedImageModalProps) => {
   ```

2. **Add approval section** in context panel (after Image Details Box, around line 252):
   ```typescript
   import { FiThumbsUp, FiThumbsDown } from "react-icons/fi"

   // ... in return statement, after Image Details Box:

   {/* Approval controls */}
   {onApprovalChange && currentImage && (
     <Box>
       <Text fontWeight="bold" fontSize="sm" mb={2}>
         Approval
       </Text>
       <HStack gap={2}>
         <IconButton
           aria-label="Approve image"
           variant={currentImage.image.user_approved === true ? "solid" : "outline"}
           colorPalette={currentImage.image.user_approved === true ? "green" : "gray"}
           onClick={() =>
             onApprovalChange(
               currentImage.image.id,
               currentImage.image.user_approved === true ? null : true
             )
           }
         >
           <FiThumbsUp />
         </IconButton>
         <IconButton
           aria-label="Reject image"
           variant={currentImage.image.user_approved === false ? "solid" : "outline"}
           colorPalette={currentImage.image.user_approved === false ? "red" : "gray"}
           onClick={() =>
             onApprovalChange(
               currentImage.image.id,
               currentImage.image.user_approved === false ? null : false
             )
           }
         >
           <FiThumbsDown />
         </IconButton>
         {currentImage.image.user_approved !== null && (
           <Text fontSize="xs" color="fg.muted" ml={2}>
             {currentImage.image.user_approved ? "Approved" : "Rejected"}
           </Text>
         )}
       </HStack>
     </Box>
   )}
   ```

3. **Add imports** at top of file:
   ```typescript
   import { FiThumbsUp, FiThumbsDown } from "react-icons/fi"
   ```

4. **Test modal** by opening it from gallery:
   - Click an image card to open modal
   - Verify approval buttons appear
   - Click buttons and verify they work
   - Close and reopen modal to verify state persists

**Risk Mitigation**:
- Buttons use same logic as card component for consistency
- Modal doesn't close on button click (only affects approval state)
- Show approval status text for clarity

---

### Phase 6: Frontend API Integration and State Management (45 min)
**Goal**: Implement TanStack Query mutations and integrate with gallery page

**Dependencies**: Phase 5 complete (UI components ready)

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] Approval mutations call backend API correctly
- [ ] Optimistic updates show immediate feedback
- [ ] Query invalidation refreshes gallery after update
- [ ] Error handling rolls back on API failure
- [ ] Both card and modal buttons trigger same mutation
- [ ] Loading states during mutation handled gracefully

**Tasks**:
1. **Create API wrapper method** in `frontend/src/api/generatedImages.ts`:
   ```typescript
   // Add to GeneratedImageApi namespace or create wrapper
   export const updateImageApproval = async (
     imageId: string,
     approved: boolean | null
   ) => {
     const response = await fetch(
       `${API_BASE_URL}/generated-images/${imageId}/approval`,
       {
         method: "PATCH",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ user_approved: approved }),
       }
     )
     if (!response.ok) {
       throw new Error(`Failed to update approval: ${response.statusText}`)
     }
     return response.json()
   }
   ```

2. **Add approval mutation** in `frontend/src/routes/_layout/generated-images.tsx` (around line 275):
   ```typescript
   import { useMutation, useQueryClient } from "@tanstack/react-query"
   import { updateImageApproval } from "@/api/generatedImages"

   function GeneratedImagesGalleryPage() {
     const queryClient = useQueryClient()
     // ... existing state ...

     const approvalMutation = useMutation({
       mutationFn: ({ imageId, approved }: { imageId: string; approved: boolean | null }) =>
         updateImageApproval(imageId, approved),
       onMutate: async ({ imageId, approved }) => {
         // Cancel outgoing refetches
         await queryClient.cancelQueries({ queryKey: ["generated-images"] })

         // Snapshot previous value
         const previousImages = queryClient.getQueryData(["generated-images", "list", search])

         // Optimistically update
         queryClient.setQueryData(["generated-images", "list", search], (old: any) => {
           if (!old?.pages) return old
           return {
             ...old,
             pages: old.pages.map((page: any) => ({
               ...page,
               data: page.data.map((img: any) =>
                 img.id === imageId
                   ? { ...img, user_approved: approved, approval_updated_at: new Date().toISOString() }
                   : img
               ),
             })),
           }
         })

         // Also update single image query if it exists
         queryClient.setQueryData(["generated-image", imageId], (old: any) => {
           if (!old) return old
           return {
             ...old,
             image: {
               ...old.image,
               user_approved: approved,
               approval_updated_at: new Date().toISOString(),
             },
           }
         })

         return { previousImages }
       },
       onError: (err, variables, context) => {
         // Rollback on error
         if (context?.previousImages) {
           queryClient.setQueryData(
             ["generated-images", "list", search],
             context.previousImages
           )
         }
         console.error("Failed to update approval:", err)
       },
       onSuccess: () => {
         // Invalidate to refetch
         queryClient.invalidateQueries({ queryKey: ["generated-images"] })
         queryClient.invalidateQueries({ queryKey: ["generated-image"] })
       },
     })

     const handleApprovalChange = (imageId: string, approved: boolean | null) => {
       approvalMutation.mutate({ imageId, approved })
     }
   ```

3. **Pass callback to components** (around line 350-392):
   ```typescript
   {/* In gallery grid */}
   <SimpleGrid columns={{ base: 1, sm: 2, md: 3 }} gap={4}>
     {images.map((image) => (
       <GeneratedImageCard
         key={image.id}
         image={image}
         onClick={() => handleImageClick(image.id, image.scene_extraction_id)}
         onApprovalChange={handleApprovalChange}
       />
     ))}
   </SimpleGrid>

   {/* In modal */}
   <GeneratedImageModal
     isOpen={isModalOpen}
     onClose={handleModalClose}
     imageId={selectedImageId}
     sceneId={selectedSceneId}
     allImages={images.map((img) => ({
       id: img.id,
       scene_extraction_id: img.scene_extraction_id
     }))}
     onNavigate={handleNavigate}
     onApprovalChange={handleApprovalChange}
   />
   ```

4. **Test mutation**:
   - Run frontend dev server: `npm run dev`
   - Open gallery, click thumbs up/down on a card
   - Verify immediate UI update (optimistic)
   - Check network tab for PATCH request
   - Verify data refetches and matches server state
   - Test error case (stop backend, click button, verify rollback)

5. **Run linting**:
   ```bash
   cd frontend
   npm run lint
   ```

**Risk Mitigation**:
- Optimistic updates provide instant feedback
- Rollback on error prevents stale state
- Query invalidation ensures server truth
- Handle undefined/null gracefully in map functions

---

### Phase 7: Frontend Approval Filter UI (30 min)
**Goal**: Add approval filter dropdown to gallery filters

**Dependencies**: Phase 6 complete (mutations working)

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Approval filter dropdown appears in filters section
- [ ] Filter options: All, Approved, Rejected, Pending
- [ ] Selecting filter updates URL params and triggers refetch
- [ ] Filter state persists in URL (shareable/bookmarkable)
- [ ] Gallery shows correct filtered results
- [ ] Reset button clears approval filter

**Tasks**:
1. **Update search schema** in `frontend/src/routes/_layout/generated-images.tsx` (around line 34):
   ```typescript
   const generatedImagesSearchSchema = z.object({
     book_slug: z.string().trim().min(1).optional().or(z.literal("").transform(() => undefined)).catch(undefined),
     chapter_number: z.coerce.number().int().min(0).optional().or(z.literal("").transform(() => undefined)).catch(undefined),
     provider: z.string().trim().min(1).optional().or(z.literal("").transform(() => undefined)).catch(undefined),
     model: z.string().trim().min(1).optional().or(z.literal("").transform(() => undefined)).catch(undefined),
     approval: z
       .enum(["approved", "rejected", "pending", ""])
       .transform((val) => {
         if (val === "approved") return true
         if (val === "rejected") return false
         if (val === "pending") return null
         return undefined
       })
       .optional()
       .catch(undefined),
     page_size: z.coerce.number().int().min(1).max(48).catch(24),
   })
   ```

2. **Update API query** to pass approval filter (around line 210):
   ```typescript
   const query = useInfiniteQuery({
     queryKey: ["generated-images", "list", search],
     queryFn: ({ pageParam = 0 }) =>
       GeneratedImageApi.list({
         book: search.book_slug!,
         chapter: search.chapter_number,
         provider: search.provider,
         model: search.model,
         approval: search.approval,  // Add this
         limit: search.page_size,
         offset: pageParam,
       }),
     enabled: queryEnabled,
     // ...
   })
   ```

3. **Add filter dropdown** in `GeneratedImagesFilters` component (around line 200):
   ```typescript
   <Stack spacing={1}>
     <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
       Approval
     </Text>
     <NativeSelectRoot disabled={disabled} w="full">
       <NativeSelectField
         value={
           search.approval === true
             ? "approved"
             : search.approval === false
               ? "rejected"
               : search.approval === null
                 ? "pending"
                 : ""
         }
         onChange={(event) => {
           const val = event.target.value
           handleChange({
             approval:
               val === "approved"
                 ? true
                 : val === "rejected"
                   ? false
                   : val === "pending"
                     ? null
                     : undefined,
           })
         }}
       >
         <option value="">All images</option>
         <option value="approved">Approved only</option>
         <option value="rejected">Rejected only</option>
         <option value="pending">Pending only</option>
       </NativeSelectField>
       <NativeSelectIndicator />
     </NativeSelectRoot>
   </Stack>
   ```

4. **Update reset filters** to include approval (around line 92):
   ```typescript
   const resetFilters = () => {
     handleChange({
       chapter_number: undefined,
       provider: undefined,
       model: undefined,
       approval: undefined,  // Add this
     })
   }
   ```

5. **Update SimpleGrid columns** to adjust for new filter (around line 120):
   ```typescript
   <SimpleGrid columns={{ base: 1, md: 5 }} gap={4}>
     {/* Book, Chapter, Provider, Model, Approval */}
   ```

6. **Test filtering**:
   - Select "Approved only" → should show only images with green borders
   - Select "Rejected only" → should show only images with red borders
   - Select "Pending only" → should show images with no approval status
   - Select "All images" → should show everything
   - Check URL updates with filter param
   - Refresh page and verify filter persists

7. **Run linting**:
   ```bash
   npm run lint
   ```

**Risk Mitigation**:
- Use controlled select with explicit value mapping
- Handle tri-state logic carefully (true/false/null/undefined)
- URL encoding preserves filter state across sessions
- Reset button clears all filters consistently

---

## System Integration Points

**Database Tables**:
- `generated_images`: Read/write (new columns: `user_approved`, `approval_updated_at`)

**External APIs**: None (internal backend only)

**Message Queues**: None

**WebSockets**: None

**Cron Jobs**: None

**Cache Layers**: None (TanStack Query handles client-side caching)

## Technical Considerations

**Performance**:
- No indexes on `user_approved` column initially (add if filtering becomes slow)
- Optimistic updates prevent network latency from blocking UI
- Infinite scroll pagination remains efficient
- PATCH requests are lightweight (single field update)

**Security**:
- No authentication required (single-user system)
- Input validation in Pydantic schema (bool | None)
- SQLModel prevents SQL injection
- CORS configured for local development

**Database**:
- **Migration**: Add 2 nullable columns (backward compatible)
- **Indexes**: None initially (low query volume, can add later)
- **Storage**: ~1 byte (bool) + 8 bytes (timestamp) per image
- **Query patterns**: Filter on `user_approved` uses sequential scan (acceptable for <10k images)

**API Design**:
- RESTful endpoint: `PATCH /generated-images/{id}/approval`
- Idempotent (can call repeatedly with same value)
- Returns full resource (not just approval field)
- camelCase in JSON (`userApproved`, `approvalUpdatedAt`)

**Error Handling**:
- 404 if image ID doesn't exist
- 422 if approval value invalid (Pydantic validation)
- Frontend rollback on network error
- Toast notifications for user feedback (optional future enhancement)

**Monitoring**:
- **Logging**: API endpoint logs approval changes at INFO level
- **Metrics to track** (optional future):
  - Approval rate (% approved vs rejected)
  - Time to first approval (engagement metric)
  - Approval distribution by model/provider
- **Alerts**: None needed (non-critical feature)

## Testing Strategy

**Unit Tests** (optional, focus on integration):
- `test_generated_image_repository.py`:
  - `test_update_approval()`: Verify approval update and timestamp set
  - `test_list_for_book_approval_filter()`: Test filtering by approval status

**Integration Tests**:
- `test_generated_images_api.py`:
  - `test_patch_approval_endpoint()`: Verify PATCH returns updated record
  - `test_list_with_approval_filter()`: Test GET with `approval` param

**Manual Verification** (5 min workflow):
1. Generate some test images: `uv run python -m app.services.image_gen_cli ...`
2. Open gallery: http://localhost:5173/generated-images
3. Click thumbs up on 2 images, thumbs down on 1
4. Select "Approved only" filter → see 2 images
5. Select "Rejected only" filter → see 1 image
6. Open modal, verify buttons work and sync with card state

**Performance Check**: None needed (negligible impact)

## Acceptance Criteria

- [ ] All automated tests pass (`uv run pytest`, `npm run build`)
- [ ] Code follows project conventions:
  - Backend: 4-space indent, snake_case, PascalCase models
  - Frontend: 2-space indent, camelCase, PascalCase components
- [ ] Linting passes:
  - Backend: `uv run bash scripts/lint.sh`
  - Frontend: `npm run lint`
- [ ] Feature works as described:
  - [ ] Thumbs up/down buttons appear on cards and modal
  - [ ] Clicking buttons updates approval status
  - [ ] Visual indicators show approval state (borders)
  - [ ] Filter dropdown shows 4 options (All/Approved/Rejected/Pending)
  - [ ] Filtering works correctly for each option
  - [ ] URL params preserve filter state
  - [ ] Reset button clears approval filter
- [ ] Error cases handled gracefully:
  - [ ] 404 if image doesn't exist
  - [ ] Frontend rollback on network error
  - [ ] Null approval clears status correctly
- [ ] Performance meets requirements (no noticeable slowdown)
- [ ] Backward compatibility maintained (existing images show as "pending")

## Quick Reference Commands

**Run backend locally**:
```bash
cd backend
uv run fastapi dev app/main.py
```

**Run frontend locally**:
```bash
cd frontend
npm run dev
```

**Run tests**:
```bash
cd backend
uv run pytest tests/
```

**Lint check**:
```bash
cd backend
uv run bash scripts/lint.sh
cd ../frontend
npm run lint
```

**Database migration**:
```bash
cd backend
uv run alembic revision -m "add_image_approval_columns"
uv run alembic upgrade head
uv run alembic current
```

**View logs**:
```bash
docker compose logs -f backend
docker compose logs -f frontend
```

**Check database**:
```bash
docker compose exec db psql -U postgres -d app
\d generated_images
SELECT id, user_approved, approval_updated_at FROM generated_images LIMIT 5;
```

**Regenerate frontend client**:
```bash
cd frontend
./scripts/generate-client.sh
```

**Test approval endpoint**:
```bash
# Get image ID
IMAGE_ID=$(docker compose exec db psql -U postgres -d app -t -c "SELECT id FROM generated_images LIMIT 1;")

# Approve
curl -X PATCH http://localhost:8000/api/generated-images/${IMAGE_ID}/approval \
  -H "Content-Type: application/json" \
  -d '{"user_approved": true}' | jq

# Filter approved images
curl "http://localhost:8000/api/generated-images?book=excession-iain-m-banks&approval=true" | jq
```

## Inter-Instance Communication

### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes Structure:
Each phase should document:
- **Phase X: [Name]** - Completed YYYY-MM-DD
- **Status**: ✅ Complete / ⚠️ Partial / ❌ Blocked
- **Key findings**: Any surprises or deviations from plan
- **Gotchas**: Issues encountered and how resolved
- **Warnings for next phase**: Critical information for continuation

### Phase Completion Notes
- **Phase 1: Database Schema Extension** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: Added `user_approved` and `approval_updated_at` columns to the SQLModel and generated Alembic migration; migration applied successfully against the local Postgres instance.
  - **Gotchas**: `uv run` and `docker compose exec` required elevated permissions in this environment; reran commands with escalation to proceed.
  - **Warnings for next phase**: Repository update logic must populate `approval_updated_at` whenever `user_approved` changes to avoid leaving the timestamp null after API interactions.
- **Phase 2: Backend Repository and API Endpoints** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: Added repository support for updating approval state and filtering by approval in book listings, exposed a PATCH endpoint for approval updates, and included the new fields in generated image response schemas.
  - **Gotchas**: `uv run bash scripts/lint.sh` still fails with pre-existing mypy stub/type issues unrelated to the new approval code; documented here for visibility.
  - **Warnings for next phase**: The list endpoint currently treats missing and explicit `null` approval the same, so the upcoming frontend work may need to send a distinct sentinel (or we adjust the API) to support "pending" filters cleanly.
- **Phase 3: Frontend TypeScript Client Regeneration** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: Regenerated the OpenAPI client with `openapi-ts`; the SDK now exposes `updateImageApproval`, list queries accept the `approval` filter, and `GeneratedImageRead`/context payloads include `user_approved` and `approval_updated_at` fields (matching existing snake_case naming in generated types).
  - **Gotchas**: `scripts/generate-client.sh` could not run end-to-end because its inner `python` call does not pick up the `uv` environment in this sandbox; manually reproduced its steps with `uv run` and recorded the new `frontend/src/client` output. `npm run build` still fails due to long-standing Chakra UI typing issues in prompt-related components (see `tsc` errors starting in `frontend/src/components/Prompts/PromptCard.tsx`).
  - **Warnings for next phase**: Frontend build errors persist, so subsequent UI work should account for the failing `npm run build` baseline when validating changes; no additional client regeneration needed before starting card/modal updates.
- **Phase 4: Frontend Card Component Enhancements** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: `GeneratedImageCard` now surfaces thumbs up/down controls with tri-state toggling logic and highlights approval status via dynamic border colors; the component accepts an optional `onApprovalChange` callback that will wire into upcoming mutations.
  - **Gotchas**: Chakra's `IconButton` requires `event.stopPropagation()` to avoid triggering the existing card click handler when changing approval, so both buttons guard against unintended modal opens.
  - **Warnings for next phase**: Parent gallery page still needs to supply `onApprovalChange` once the mutation plumbing lands—Phase 6 should connect the callback to the new backend endpoint.
- **Phase 5: Frontend Modal Component** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: Added approval controls to `GeneratedImageModal`, mirroring the card interaction logic and showing current approval status within the context panel; the callback remains optional so existing consumers continue to work until Phase 6 wires it up.
  - **Gotchas**: Biome's existing `useExhaustiveDependencies` warnings persist for the modal keyboard navigation hook; no new lint issues were introduced.
  - **Warnings for next phase**: Once mutations are implemented, pass `onApprovalChange` from the gallery page so both the modal and card stay in sync during optimistic updates.
- **Phase 6: Frontend API Integration and State Management** - Completed 2025-10-21
  - **Status**: ✅ Complete
  - **Key findings**: Wired the gallery page and modal to the new approval endpoint with a shared TanStack Query mutation, including optimistic cache updates for the infinite list, single-image modal query, and scene-level list. Added the lightweight REST helper in `frontend/src/api/generatedImages.ts` so the mutation can call the PATCH route without regenerating the entire client.
  - **Gotchas**: `npm run lint` still fails with long-standing Biome complaints (scene modal dependency heuristics and generated OpenAPI client styles); no new lint errors were introduced by this phase, but the command exits non-zero due to those pre-existing issues.
  - **Warnings for next phase**: Phase 7 should reuse the existing `listQueryKey`/`search` plumbing when adding approval filters so the optimistic mutation continues to target the right cache key; the `GeneratedImageApi.list` helper already accepts additional query params if needed.
- **Phase 7: Frontend Approval Filter UI** - Completed 2025-10-22
  - **Status**: ✅ Complete
  - **Key findings**: Added the tri-state approval filter to the gallery search schema, query key, and filter controls, letting users toggle All/Approved/Rejected/Pending while keeping state in the URL.
  - **Gotchas**: Because the backend list endpoint cannot distinguish between a missing approval filter and an explicit `null`, pending images are filtered on the client and may require loading extra pages to surface everything.
  - **Warnings for next phase**: Consider extending the API to support an explicit pending sentinel (or similar) before layering on additional analytics or compound filters so server-side pagination stays accurate.
