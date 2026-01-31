# Image Crop Feature

## Overview
Add a "Crop" button to the generated images modal that opens a separate cropping modal. Users can make free-form rectangular selections and apply the crop, which overwrites the original image file. Cropping is done client-side using canvas, then uploaded to the backend.

## Problem Statement
Users viewing generated images sometimes want to crop out unwanted portions or reframe the composition. Currently, users must:
- Download the image
- Crop in an external editor
- Have no way to update the image in the system

**User impact**: Users cannot easily adjust image composition without leaving the application.

**Business value**: Enables quick refinement of generated images directly in the app, improving workflow efficiency.

## Proposed Solution
Add a "Crop" button to `GeneratedImageModal` that:
1. Opens a dedicated `CropModal` component
2. Uses `react-image-crop` library for free-form rectangular crop selection
3. Previews the crop before applying
4. On confirm, crops the image client-side using canvas
5. Uploads the cropped image to a new backend endpoint
6. Backend overwrites the original file

**Key decisions**:
- **Crop UI**: Separate modal (not inline in existing modal)
- **File strategy**: Overwrite original file entirely (no backup)
- **Processing**: Frontend crops via canvas, uploads result
- **Crop shapes**: Free-form rectangular only (no aspect ratio constraints)
- **Approval status**: Unchanged after cropping

**Architectural approach**:
- New `CropModal` component with react-image-crop
- New PUT endpoint `/generated-images/{image_id}/crop` accepting multipart file upload
- Backend overwrites file at existing storage_path

**Key components involved**:
- Frontend: `GeneratedImageModal.tsx` (add Crop button), new `CropModal.tsx`
- Backend: New route in `generated_images.py`
- No database schema changes needed

## Codebase Research Summary

**Relevant existing patterns found**:
1. **Modal pattern**: `MetadataRegenerationModal` demonstrates opening a secondary modal from `GeneratedImageModal`
2. **Image URL building**: `buildGeneratedImageUrl()` utility for constructing image paths
3. **File serving**: `_GENERATED_IMAGES_ROOT` path constant and `FileResponse` usage
4. **API patterns**: Existing endpoints use `SessionDep` and repository pattern

**Files and components that will be affected**:
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`: Add Crop button
- `frontend/src/components/GeneratedImages/CropModal.tsx`: New component
- `frontend/src/components/GeneratedImages/index.ts`: Export new component
- `backend/app/api/routes/generated_images.py`: New crop endpoint
- `frontend/package.json`: Add react-image-crop dependency

**Similar features that can serve as reference**:
- `MetadataRegenerationModal` for modal-within-modal pattern
- Remix button flow for button + async operation pattern

**Potential risks or conflicts identified**:
- Large image files may cause browser memory issues during canvas operations
- Need to preserve image format (PNG/JPEG) when saving
- CORS considerations for loading images into canvas

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes

**Key Decisions Made**:
- Use `react-image-crop` library (lightweight, well-maintained)
- Free-form crop only (no preset aspect ratios)
- Client-side cropping via canvas API
- Overwrite original file (no backup/versioning)
- Approval status preserved after crop

**Assumptions about the system**:
- Images are accessible via URL for canvas loading
- Backend has write permissions to image directories
- Image formats are standard web formats (PNG, JPEG, WebP)

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify dependencies from previous phases
- [ ] Read the latest version of files you'll modify
- [ ] Ensure frontend dev server is running

## Implementation Phases

### Phase 1: Install Dependencies and Create CropModal Component
**Goal**: Create the crop modal UI with react-image-crop

**Dependencies**: None

**Success Metrics**:
- [ ] react-image-crop installed
- [ ] CropModal component renders with image
- [ ] User can draw crop selection
- [ ] Preview of cropped result shown
- [ ] Cancel and Apply buttons functional

**Tasks**:
1. Install react-image-crop:
   ```bash
   cd frontend && npm install react-image-crop
   ```

2. Create `frontend/src/components/GeneratedImages/CropModal.tsx`:
   - Props: `isOpen`, `onClose`, `imageSrc`, `onCropComplete: (croppedBlob: Blob) => void`
   - Use `ReactCrop` component for selection UI
   - Add preview canvas showing cropped result
   - Cancel button closes modal
   - Apply button calls canvas crop logic and invokes `onCropComplete`

3. Implement canvas crop logic in CropModal:
   - Load image into hidden img element
   - On Apply, draw cropped region to canvas
   - Detect original format from image src (PNG vs JPEG)
   - Convert canvas to Blob preserving original format (`image/png` or `image/jpeg` with quality 1.0)
   - Pass blob to `onCropComplete` callback

4. Export from `frontend/src/components/GeneratedImages/index.ts`

### Phase 2: Backend Crop Endpoint
**Goal**: Create endpoint to receive and save cropped image

**Dependencies**: None (can be done in parallel with Phase 1)

**Success Metrics**:
- [ ] PUT `/generated-images/{image_id}/crop` endpoint exists
- [ ] Accepts multipart file upload
- [ ] Validates image exists
- [ ] Overwrites original file
- [ ] Returns success response

**Tasks**:
1. Add imports to `backend/app/api/routes/generated_images.py`:
   - `from fastapi import UploadFile, File`

2. Create PUT route:
   ```python
   @router.put("/{image_id}/crop")
   async def crop_image(
       image_id: UUID,
       session: SessionDep,
       file: UploadFile = File(...),
   ) -> dict[str, str]:
   ```

3. Implement route logic:
   - Load image record from `GeneratedImageRepository.get(image_id)`
   - Raise 404 if not found
   - Construct full file path from `storage_path` and `file_name`
   - Validate file path exists
   - Write uploaded file contents to path (overwrite)
   - Return `{"status": "success"}`

4. Add error handling:
   - 404 if image not found
   - 400 if file path doesn't exist on disk
   - 500 for write failures

### Phase 3: Integrate Crop Button and Modal into GeneratedImageModal
**Goal**: Wire up the crop flow in the existing modal

**Dependencies**: Phases 1 and 2 completed

**Success Metrics**:
- [ ] Crop button visible in GeneratedImageModal
- [ ] Clicking opens CropModal with current image
- [ ] Applying crop uploads to backend
- [ ] Success/error feedback shown
- [ ] Image refreshes after successful crop

**Tasks**:
1. Add Crop button to `GeneratedImageModal.tsx`:
   - Import `FiCrop` from react-icons/fi
   - Add state: `isCropModalOpen`
   - Add IconButton with crop icon in the Image Details section
   - onClick sets `isCropModalOpen = true`

2. Add CropModal to GeneratedImageModal:
   - Import `CropModal` component
   - Render at bottom of component (like MetadataRegenerationModal)
   - Pass `isOpen={isCropModalOpen}`, `onClose`, `imageSrc={fullPath}`

3. Create API client function in `frontend/src/api/generatedImages.ts`:
   ```typescript
   export const cropImage = async (imageId: string, file: Blob): Promise<void> => {
     const formData = new FormData()
     formData.append("file", file)
     await fetch(`/api/generated-images/${imageId}/crop`, {
       method: "PUT",
       body: formData,
     })
   }
   ```

4. Handle crop completion in GeneratedImageModal:
   - Create `handleCropComplete` callback
   - Call `cropImage(imageId, blob)`
   - On success: close crop modal, invalidate image query to refresh
   - On error: show toast
   - Add loading state during upload

5. Add toast notifications for success/error feedback

### Phase 4: Polish and Testing
**Goal**: Ensure robust UX and handle edge cases

**Dependencies**: Phase 3 completed

**Success Metrics**:
- [ ] Loading states during crop upload
- [ ] Error handling for failed uploads
- [ ] Image cache busted after crop (shows updated image)
- [ ] Works with different image formats
- [ ] No console errors

**Tasks**:
1. Add loading state to CropModal Apply button

2. Handle image cache busting:
   - After successful crop, append timestamp query param to image URL
   - Or invalidate TanStack Query cache for the image

3. Test with various image sizes and formats

4. Ensure crop modal closes on successful upload

5. Run linting:
   - `cd frontend && npm run lint`
   - `cd backend && uv run bash scripts/lint.sh`

## System Integration Points

**Database Tables**:
- **Read**: `generated_images` (to get file path)
- **Write**: None (file system only)

**External APIs**: None

**File System**:
- **Write**: Overwrites image file at `storage_path/file_name`

## Technical Considerations

**Performance**:
- Canvas operations happen client-side (no server CPU load)
- Large images may be slow to crop in browser
- File upload is the only network operation

**Security**:
- Validate image_id exists before allowing overwrite
- Sanitize file path to prevent directory traversal
- Accept only image MIME types

**Image Quality**:
- Detect original format from URL/response headers
- PNG: Lossless, no quality loss on re-encode
- JPEG: Use quality=1.0 to minimize generational loss
- DALL-E images are PNG by default, so most crops will be lossless

**Browser Compatibility**:
- Canvas API widely supported
- react-image-crop supports modern browsers

**Error Handling**:
- Network failures during upload
- Invalid crop selections (zero width/height)
- File write permission errors

## Acceptance Criteria
- [ ] Crop button appears in GeneratedImageModal
- [ ] Clicking Crop opens a separate modal with the image
- [ ] User can draw free-form rectangular crop selection
- [ ] User can see preview of cropped result
- [ ] Applying crop uploads to backend and overwrites file
- [ ] Image refreshes to show cropped version
- [ ] Error cases handled gracefully
- [ ] No console errors

## Quick Reference Commands
- **Run frontend locally**: `cd frontend && npm run dev`
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Frontend linting**: `cd frontend && npm run lint`
- **Backend linting**: `cd backend && uv run bash scripts/lint.sh`
- **Test crop endpoint**: `curl -X PUT -F "file=@test.png" http://localhost:8000/api/generated-images/{image_id}/crop`

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
_Completed 2026-01-31_
- Installed react-image-crop via npm
- Created CropModal.tsx with ReactCrop component
- Implemented canvas crop logic for generating previews and final cropped blob
- Exported from index.ts

**Phase 2 Notes**:
_Completed 2026-01-31_
- Added PUT /generated-images/{image_id}/crop endpoint
- Added UploadFile and File imports to routes
- Endpoint validates image exists, resolves file path, and overwrites with uploaded cropped image
- Returns {"status": "success"} on completion

**Phase 3 Notes**:
_Completed 2026-01-31_
- Added FiCrop icon import and isCropModalOpen state to GeneratedImageModal
- Added Crop button as IconButton next to "Image Details" header
- Created cropImage API function in generatedImages.ts
- Added handleCropComplete callback with cache busting (imageCacheBuster state)
- Integrated CropModal component with toast notifications for success/error

**Phase 4 Notes**:
_Completed 2026-01-31_
- Removed crossOrigin="anonymous" attribute from img element - was causing image not to load due to CORS preflight issues with same-origin API endpoint
- Fixed alt text lint warning (changed "Image to crop" to "Crop selection area")
- Tested via Chrome extension:
  - CropModal opens correctly when clicking crop icon
  - Image loads properly in the crop modal
  - Preview section shows instructions
  - Cancel and Apply Crop buttons render correctly
  - No console errors
- Note: Drag-to-crop functionality was not tested as requested by user, but the modal renders without errors
