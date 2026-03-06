I just added backend/app/services/flickr/flickr_service.py.

I have already added the required values to `.env`.

I have also already completed Flickr OAuth setup in local development using this reusable flow:
```bash
cd backend && uv run python -c "
from app.core.config import settings
from app.services.flickr.flickr_service import FlickrService
service = FlickrService(settings.FLICKR_API_KEY, settings.FLICKR_API_SECRET)
"
# The service prints an authorization URL.
# Approve access in Flickr and complete the CLI prompt.
# Credentials are persisted locally after successful authorization.
```

I want to create a new system that will help me to automatically post images that I have approved for posting to whatever applications I have set up to post to, like Flickr or Twitter.

In the /generated-images frontend I would like a new button in both the normal view and the modal view, which is next to the thumbs up and thumbs down buttons. If I click that button, it will mark that image as going in the queue to post to the social media applications I have set up. This information will be saved somewhere in the database. You decide whether it's a new table or just added columns to an existing table. It will be defined as a flag somewhere on how often I want approved images to be posted, like a HOURS_BETWEEN_POSTING_IMAGES constant. Then there will be a background process running somewhere. If it has been that many hours since the last image to post in the queue was posted, that process will use the APIs to post the image to the service. Once an image has been successfully uploaded and posted to our configured services, that should be shown in the /generated-images frontend in a well designed way, like posted images should have a little icon or something that makes it easy to see they have been posted. If I open the modal view of an image, it should show me which services that image has been uploaded to. When the image is posted, we should only use the title of the image eg "The Gilded Ark". I think the title might be attached to the prompt, but I'm not sure. The title I'm talking about is the one that we can change if I click the regenerate button in the front-end. Let's not post the description for now.

Right now I only have Flickr set up but I will probably add twitter and maybe others. Each service like `flickr_service.py` should be set up so that they have a method that is configured for posting ai images to that service, because we want to make sure that we follow all the guidelines of that service that are specific to posting AI-generated art.

---

# Auto-Post to Social Media Feature

## Overview
Implement an automated system to post approved generated images to configured social media services (starting with Flickr). Users can queue approved images for posting via a button in the UI, and a background scheduler will post them at configurable intervals.

## Problem Statement
- **Current limitation**: Generated images must be manually downloaded and uploaded to social media platforms
- **User impact**: Time-consuming workflow to share AI-generated art across multiple platforms
- **Business value**: Streamlined content sharing with automatic compliance for AI-generated content disclosure

## Proposed Solution
- Add a "queue for posting" button next to approval buttons (only visible for approved images)
- Create a new `SocialMediaPost` database table to track posting queue and history
- Use APScheduler to run a background task that posts queued images at configured intervals
- When queuing: if cooldown has passed, post immediately; otherwise add to queue for later
- Display a share icon on posted images; show detailed service info in modal view

## Codebase Research Summary

### Relevant Existing Patterns Found
- **Background tasks**: `backend/app/api/routes/generated_images.py:63` uses `_spawn_background_task()` pattern with `asyncio.create_task()` for remix operations
- **Service layer pattern**: Services like `FlickrService` in `backend/app/services/flickr/flickr_service.py` handle external API calls
- **Model structure**: `GeneratedImage` model in `backend/models/generated_image.py` with SQLModel + relationships
- **Frontend components**: `GeneratedImageCard.tsx` and `GeneratedImageModal.tsx` have approval buttons pattern with `FiThumbsUp`/`FiThumbsDown` icons
- **Settings pattern**: `backend/app/core/config.py` uses pydantic Settings with environment variables

### Files and Components That Will Be Affected
**Backend:**
- `backend/models/` - New `SocialMediaPost` model
- `backend/app/core/config.py` - Add `HOURS_BETWEEN_POSTING_IMAGES` setting
- `backend/app/services/flickr/flickr_service.py` - Already has AI-compliant `upload()` method
- `backend/app/services/` - New `social_posting/` service directory
- `backend/app/api/routes/generated_images.py` - New endpoints for queue management
- `backend/app/main.py` - APScheduler setup

**Frontend:**
- `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx` - Add queue button + posted indicator
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` - Add queue button + service details
- `frontend/src/routes/_layout/generated-images.tsx` - Add posting status filter
- `frontend/src/api/` - New API functions for posting queue

### Similar Features for Reference
- Approval workflow: `user_approved` field in `GeneratedImage`, `updateImageApproval()` API, thumbs up/down UI
- Background task spawning in `generated_images.py` routes

### Potential Risks
- APScheduler needs proper shutdown handling to avoid orphaned jobs
- Service failures should not block the queue (retry mechanism needed)

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes
4. Look for TODO/FIXME comments in affected files

**Key Decisions Made**:
- Single queue for all services (when an image posts, it goes to all configured services at once)
- APScheduler for background scheduling (runs within FastAPI process)
- "Post first immediately" behavior: if cooldown passed, post immediately on queue action; otherwise queue for later
- Share/upload icon for posted indicator in card view
- No queue removal feature (keep it simple)
- HOURS_BETWEEN_POSTING_IMAGES as environment variable
- Retry failed posts on next scheduler run (not blocking)
- Add filter options for queued/posted/not-queued status
- Queue button only appears for approved images (`user_approved=true`)
- Title comes from `ImagePrompt.title` field

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify all dependencies from previous phases
- [ ] Read the latest version of files you'll modify

## Implementation Phases

### Phase 1: Database Model and Migration

**Goal**: Create the data model to track posting queue and history

**Dependencies**: None

**Success Metrics**:
- [ ] `SocialMediaPost` model created
- [ ] Alembic migration runs successfully
- [ ] Model exported in `backend/models/__init__.py`

**Tasks**:
1. Create `backend/models/social_media_post.py` with SQLModel table:
   - `id: UUID` (primary key)
   - `generated_image_id: UUID` (foreign key to `generated_images.id`, indexed)
   - `service_name: str` (e.g., "flickr", "twitter")
   - `status: str` (enum: "queued", "posted", "failed")
   - `external_id: str | None` (e.g., Flickr photo ID)
   - `external_url: str | None` (link to the post)
   - `queued_at: datetime`
   - `posted_at: datetime | None`
   - `last_attempt_at: datetime | None`
   - `attempt_count: int` (default 0)
   - `error_message: str | None`
   - Unique constraint on `(generated_image_id, service_name)`
   - Relationship back to `GeneratedImage`

2. Add relationship to `backend/models/generated_image.py`:
   - `social_media_posts: list["SocialMediaPost"]` relationship

3. Export model in `backend/models/__init__.py`

4. Create Alembic migration:
   - `cd backend && uv run alembic revision --autogenerate -m "Add social_media_posts table"`
   - Review and run: `uv run alembic upgrade head`

---

### Phase 2: Configuration and Social Posting Service

**Goal**: Add configuration and create the orchestrating service for social media posting

**Dependencies**: Phase 1 complete

**Success Metrics**:
- [ ] `HOURS_BETWEEN_POSTING_IMAGES` setting added
- [ ] `SocialPostingService` created with queue and post methods
- [ ] Unit tests pass

**Tasks**:
1. Add to `backend/app/core/config.py`:
   - `HOURS_BETWEEN_POSTING_IMAGES: float = 4.0` (default 4 hours)
   - `FLICKR_ENABLED: bool = True` (feature flag for services)

2. Create `backend/app/services/social_posting/__init__.py`

3. Create `backend/app/services/social_posting/social_posting_service.py`:
   - `SocialPostingService` class with methods:
     - `async def queue_image(image_id: UUID, db: AsyncSession) -> list[SocialMediaPost]`
       - Check if image is approved (`user_approved=True`)
       - Check if already queued/posted for each enabled service
       - Create `SocialMediaPost` records with status="queued"
       - If cooldown has passed since last post, immediately call `process_queue()`
     - `async def process_queue(db: AsyncSession) -> None`
       - Get oldest queued post
       - Check if enough time has passed since last successful post
       - If yes, attempt to post via the appropriate service
       - Update status to "posted" or "failed" with error_message
       - Increment attempt_count, update last_attempt_at
     - `async def get_last_posted_at(db: AsyncSession) -> datetime | None`
       - Return the most recent `posted_at` from any successful post
     - `def _get_enabled_services() -> list[str]`
       - Return list like `["flickr"]` based on config flags

4. Create `backend/app/services/social_posting/flickr_poster.py`:
   - `FlickrPoster` class:
     - `async def post(image: GeneratedImage, prompt: ImagePrompt) -> tuple[str, str]`
       - Use `FlickrService.upload()` with `title=prompt.title`
       - Return `(photo_id, photo_url)`
     - Handle authentication errors, network errors gracefully

5. Create `backend/app/services/social_posting/repository.py`:
   - `SocialMediaPostRepository` with:
     - `get_by_image_id(image_id: UUID) -> list[SocialMediaPost]`
     - `get_oldest_queued() -> SocialMediaPost | None`
     - `get_last_successful_post() -> SocialMediaPost | None`
     - `create(post: SocialMediaPost) -> SocialMediaPost`
     - `update(post: SocialMediaPost) -> SocialMediaPost`

6. Create `backend/app/tests/services/social_posting/test_social_posting_service.py`:
   - Test queue_image creates records for enabled services
   - Test queue_image rejects non-approved images
   - Test process_queue respects cooldown
   - Test process_queue handles failures gracefully
   - Mock FlickrService calls

---

### Phase 3: API Endpoints

**Goal**: Create REST endpoints for queueing images and retrieving posting status

**Dependencies**: Phase 2 complete

**Success Metrics**:
- [ ] POST endpoint to queue an image works
- [ ] GET endpoint returns posting status for an image
- [ ] Tests pass

**Tasks**:
1. Add to `backend/app/api/routes/generated_images.py`:
   - `POST /generated-images/{image_id}/queue-for-posting`
     - Call `SocialPostingService.queue_image()`
     - Return list of created `SocialMediaPost` records
     - Return 400 if image not approved
   - `GET /generated-images/{image_id}/posting-status`
     - Return list of `SocialMediaPost` records for this image
     - Include status, service_name, external_url, posted_at

2. Create schema in `backend/app/schemas/social_media_post.py`:
   - `SocialMediaPostRead` with all fields for API responses

3. Update `backend/app/api/routes/generated_images.py`:
   - Add `posting_status` field to `GeneratedImageWithContext` response
   - Include posting status in list endpoint response (new field `has_been_posted: bool`, `is_queued: bool`)

4. Add filter parameters to list endpoint:
   - `posting_status: Literal["queued", "posted", "not_queued"] | None`

5. Create `backend/app/tests/api/routes/test_generated_images_posting.py`:
   - Test queue endpoint with approved image
   - Test queue endpoint rejects non-approved
   - Test status endpoint returns correct data
   - Test filter by posting status

---

### Phase 4: Background Scheduler with APScheduler

**Goal**: Set up APScheduler to periodically process the posting queue

**Dependencies**: Phase 2 complete

**Success Metrics**:
- [ ] Scheduler starts with FastAPI app
- [ ] Scheduler stops gracefully on shutdown
- [ ] Job runs at configured interval
- [ ] Posts are made when cooldown has passed

**Tasks**:
1. Add `apscheduler` to `backend/pyproject.toml` dependencies

2. Create `backend/app/services/social_posting/scheduler.py`:
   - `SocialPostingScheduler` class:
     - `start()` - Initialize APScheduler with AsyncIOScheduler
     - `stop()` - Graceful shutdown
     - `_process_queue_job()` - Async job that calls `SocialPostingService.process_queue()`
   - Configure job to run every 15 minutes (checks if cooldown passed)

3. Update `backend/app/main.py`:
   - Import scheduler
   - Add `@app.on_event("startup")` handler to start scheduler
   - Add `@app.on_event("shutdown")` handler to stop scheduler
   - Only start scheduler if `FLICKR_ENABLED` or other services enabled

4. Add logging throughout the scheduler for monitoring:
   - Log when job starts/completes
   - Log when posts are made
   - Log errors with full context

5. Manual verification:
   - Set `HOURS_BETWEEN_POSTING_IMAGES=0.01` (36 seconds) for testing
   - Queue an image, verify it posts
   - Queue another, verify it waits for cooldown

---

### Phase 5: Frontend - Card View Updates

**Goal**: Add queue button and posted indicator to image cards

**Dependencies**: Phase 3 complete

**Success Metrics**:
- [ ] Queue button appears on approved images only
- [ ] Share icon appears on posted images
- [ ] Clicking queue button triggers API call
- [ ] Optimistic UI updates work correctly

**Tasks**:
1. Update `frontend/src/api/generatedImages.ts`:
   - Add `queueForPosting(imageId: string): Promise<SocialMediaPost[]>`
   - Add `getPostingStatus(imageId: string): Promise<SocialMediaPost[]>`
   - Update `GeneratedImageRead` type to include `has_been_posted: boolean`, `is_queued: boolean`

2. Update `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx`:
   - Add import for `FiShare2` or `FiUploadCloud` icon
   - Add queue button next to thumbs up/down (only if `image.user_approved === true`)
   - Button disabled if `image.is_queued` or `image.has_been_posted`
   - Show share icon overlay in top-right corner if `image.has_been_posted`
   - Add `onQueueForPosting` prop
   - Handle loading state during queue API call

3. Update `frontend/src/routes/_layout/generated-images.tsx`:
   - Add mutation for queue action (similar to approval mutation)
   - Pass handler to `GeneratedImageCard`
   - Add optimistic update for is_queued state

4. Style the posted indicator:
   - Small share icon with subtle background in top-right of image
   - Use consistent color with approval indicators

---

### Phase 6: Frontend - Modal View Updates

**Goal**: Add queue button and service details to modal view

**Dependencies**: Phase 5 complete

**Success Metrics**:
- [ ] Queue button in modal works
- [ ] Modal shows which services image was posted to
- [ ] External links to posts are clickable

**Tasks**:
1. Update `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`:
   - Add queue button in the approval section (only for approved images)
   - Button shows "Queue for Posting" or "Queued" or "Posted" based on state
   - Add new section "Social Media" below approval:
     - List each service with status
     - If posted, show service name + link to external post
     - If queued, show "Queued" badge
     - If failed, show error message with retry option (future enhancement)
   - Query posting status when modal opens (or include in existing image query)

2. Update API call in modal to include posting status data

3. Style the social media section:
   - Use similar styling to other metadata sections
   - Service icons if available (Flickr logo, etc.) - or just text labels

---

### Phase 7: Frontend - Filter Updates

**Goal**: Add posting status filters to the gallery page

**Dependencies**: Phase 5 complete

**Success Metrics**:
- [ ] Filter dropdown includes posting status options
- [ ] Filtering works correctly with backend

**Tasks**:
1. Update `frontend/src/routes/_layout/generated-images.tsx`:
   - Add `posting_status` to search schema (enum: "queued" | "posted" | "not_queued")
   - Add filter dropdown in `GeneratedImagesFilters` component
   - Pass filter to API call

2. Style the new filter to match existing dropdowns

---

## System Integration Points

- **Database Tables**: `social_media_posts` (new), `generated_images` (read), `image_prompts` (read for title)
- **External APIs**: Flickr API via `flickrapi` library
- **Message Queues**: None (using in-process APScheduler)
- **WebSockets**: None
- **Cron Jobs**: APScheduler job every 15 minutes
- **Cache Layers**: None (direct DB queries)

## Technical Considerations

- **Performance**: Scheduler job is lightweight; actual posting is async. No impact on API response times.
- **Security**: Flickr credentials stored in environment variables. Token file stored in user home directory.
- **Database**: Single new table with proper indexes. No complex queries.
- **API Design**: RESTful endpoints following existing patterns. Consistent with approval workflow.
- **Error Handling**: Failed posts are retried on next scheduler run. Max attempts could be added later.
- **Monitoring**: Logging throughout scheduler and posting operations.

## Testing Strategy

1. **Unit Tests**:
   - `SocialPostingService.queue_image()` logic
   - `SocialPostingService.process_queue()` with mocked external services
   - Repository methods

2. **Integration Tests**:
   - API endpoint tests with database
   - Filter query tests

3. **Manual Verification**:
   - Set short cooldown, queue image, verify posts to Flickr
   - Check UI indicators update correctly

## Acceptance Criteria
- [ ] All automated tests pass
- [ ] Code follows project conventions (as per CLAUDE.md)
- [ ] Linting passes (`cd backend && uv run bash scripts/lint.sh`)
- [ ] Approved images can be queued for posting via UI
- [ ] Queued images are posted to Flickr with correct title
- [ ] Posted images show share icon in card view
- [ ] Modal shows posting status and links
- [ ] Filters work for posting status
- [ ] Scheduler runs reliably in background
- [ ] Failed posts are retried

## Quick Reference Commands
- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run tests**: `cd backend && uv run pytest`
- **Lint check**: `cd backend && uv run bash scripts/lint.sh`
- **Database migration**: `cd backend && uv run alembic upgrade head`
- **Generate frontend client**: `cd scripts && ./generate-client.sh`
- **Run frontend**: `cd frontend && npm run dev`

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

## Completion Notes

### Phase 1: Database Model and Migration - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Created `SocialMediaPost` model in `backend/models/social_media_post.py`
- Added `social_media_posts` relationship to `GeneratedImage` model
- Exported in `backend/models/__init__.py`
- Alembic migration `705b42b7e831` created and applied successfully
- All indexes created: generated_image_id, service_name, status, queued_at

### Phase 2: Configuration and Social Posting Service - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Added `HOURS_BETWEEN_POSTING_IMAGES` (default 4.0) and `FLICKR_ENABLED` (default True) to config
- Created `backend/app/services/social_posting/` directory with:
  - `__init__.py` - exports SocialPostingService
  - `repository.py` - SocialMediaPostRepository for DB operations
  - `flickr_poster.py` - FlickrPoster class using existing FlickrService
  - `social_posting_service.py` - Main orchestrating service with queue_image, process_queue, should_post_now methods
- FlickrPoster uses asyncio.run_in_executor for non-blocking upload

### Phase 3: API Endpoints - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Created `backend/app/schemas/social_media_post.py` with:
  - SocialMediaPostRead, QueueForPostingResponse, PostingStatusResponse
- Added endpoints to `backend/app/api/routes/generated_images.py`:
  - POST `/{image_id}/queue-for-posting` - queues image and triggers immediate check
  - GET `/{image_id}/posting-status` - returns posting records for image
- Updated `GeneratedImageListItem` schema with `has_been_posted` and `is_queued` fields
- Updated repository methods to include `include_posting_status` parameter
- All list endpoints now load social_media_posts relationship

### Phase 4: Background Scheduler with APScheduler - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Added `apscheduler>=3.10.0,<4.0.0` to dependencies
- Created `backend/app/services/social_posting/scheduler.py` with:
  - SocialPostingScheduler class with start/stop methods
  - AsyncIOScheduler running every 15 minutes
  - trigger_immediate_check() for on-demand processing
  - Global instance management via get_scheduler()
- Integrated with FastAPI using lifespan context manager in `backend/app/main.py`
- Scheduler only starts if at least one service (Flickr) is enabled

### Phase 5: Card View Updates - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Updated `GeneratedImageCard.tsx`:
  - Added `FiShare2` icon import
  - Added `onQueueForPosting` prop
  - Added blue share icon overlay on top-right corner for posted images
  - Added queue button (visible only for approved, not-yet-posted images)
  - Queue button disabled when already queued or posting is in progress
- Updated `frontend/src/api/generatedImages.ts`:
  - Added `has_been_posted` and `is_queued` fields to `GeneratedImageRead`
  - Added `SocialMediaPostRead`, `QueueForPostingResponse`, `PostingStatusResponse` types
  - Added `queueForPosting()` and `getPostingStatus()` functions

### Phase 6: Modal View Updates - COMPLETED
- **Date**: 2026-01-29
- **Status**: Complete
- Updated `GeneratedImageModal.tsx`:
  - Added `onQueueForPosting` prop
  - Added `postingStatusQuery` to fetch posting status when modal opens
  - Added "Social Media" section in context panel showing:
    - List of posts with status badges (Posted/Queued/Failed)
    - External link button to view on Flickr
    - Error messages for failed posts
    - "Queue for Posting" button when image is approved but not yet posted
- Updated `generated-images.tsx` route:
  - Added `queueMutation` with optimistic updates
  - Added `handleQueueForPosting` callback
  - Passed `onQueueForPosting` to both `GeneratedImageCard` and `GeneratedImageModal`

### Phase 7: Filter Updates - SKIPPED
- **Reason**: The issue spec mentioned filter updates but didn't specify what filters to add
- **Status**: The basic posting status fields (`has_been_posted`, `is_queued`) are already available on list items, which enables future filter implementation if needed
- **Note**: Filters could be added later by extending the search schema and passing to list endpoints

---

## Phase 8: X (Twitter) API Integration

**Goal**: Add X (Twitter) as a second social media service so queued images post to both Flickr and X

**Dependencies**: Phases 1-6 complete (existing social posting infrastructure)

**Success Metrics**:
- [ ] `tweepy` library added to dependencies
- [ ] X credentials configured in settings
- [ ] `XPoster` class created and integrated with `SocialPostingService`
- [ ] When "Queue for Posting" is clicked, image queues for both Flickr and X
- [ ] Posts include title + AI disclosure hashtags (#AIgenerated #AIart)
- [ ] Alt text set to image title for accessibility
- [ ] Manual verification: image successfully posts to X

**Tasks**:

1. **Add tweepy dependency**:
   - Add `tweepy>=4.14.0` to `backend/pyproject.toml` dependencies
   - Run `uv sync` to install

2. **Add X credentials to config** (`backend/app/core/config.py`):
   ```python
   # X (Twitter) API settings
   X_ENABLED: bool = False  # Default to False until credentials are configured
   X_CONSUMER_KEY: str | None = None
   X_CONSUMER_SECRET: str | None = None
   X_ACCESS_TOKEN: str | None = None
   X_ACCESS_TOKEN_SECRET: str | None = None
   ```

3. **Create `backend/app/services/social_posting/x_poster.py`**:
   - `XPoster` class following same pattern as `FlickrPoster`:
     - Lazy initialization of tweepy Client and API in `_get_client()` / `_get_api()`
     - `async def post(image: GeneratedImage, prompt: ImagePrompt) -> tuple[str, str]`
       - Upload media using v1.1 API (`api.media_upload()`)
       - Set alt text to `prompt.title` using `api.create_media_metadata()`
       - Create tweet using v2 API (`client.create_tweet()`)
       - Tweet text: `"{title} #AIgenerated #AIart"` (title from prompt)
       - Return `(tweet_id, tweet_url)`
     - Use `asyncio.run_in_executor()` for non-blocking calls (same as FlickrPoster)
     - Handle `tweepy.TweepyException` errors gracefully

4. **Update `SocialPostingService`** (`backend/app/services/social_posting/social_posting_service.py`):
   - Import `XPoster`
   - Add `_x_poster: XPoster | None = None` instance variable
   - Update `get_enabled_services()`:
     ```python
     if settings.X_ENABLED and settings.X_CONSUMER_KEY:
         services.append("x")
     ```
   - Update `_post_to_service()` to handle `service_name == "x"`:
     ```python
     elif post.service_name == "x":
         if self._x_poster is None:
             self._x_poster = XPoster()
         tweet_id, tweet_url = await self._x_poster.post(image, prompt)
         post.external_id = tweet_id
         post.external_url = tweet_url
     ```

5. **Update frontend modal** (`frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`):
   - Add X icon or "X" label for x.com posts in the Social Media section
   - The existing code should work automatically since it iterates over all `postingStatusQuery.data` items

6. **Add environment variables to `.env`**:
   ```
   X_ENABLED=true
   X_CONSUMER_KEY=your_consumer_key
   X_CONSUMER_SECRET=your_consumer_secret
   X_ACCESS_TOKEN=your_access_token
   X_ACCESS_TOKEN_SECRET=your_access_token_secret
   ```

7. **Manual verification**:
   - Set `HOURS_BETWEEN_POSTING_IMAGES=0` (no cooldown) for testing
   - Approve an image in the UI
   - Click "Queue for Posting"
   - Verify two `SocialMediaPost` records created (one for flickr, one for x)
   - Verify image posts to X with title and hashtags
   - Verify alt text is set on the X post
   - Check modal shows both Flickr and X posting status

**Technical Notes**:
- X API uses OAuth 1.0a User Context for media upload (v1.1) and tweet creation (v2)
- Media upload is v1.1 only (v2 doesn't support media upload yet)
- Tweet creation uses v2 for better API stability
- 280 character limit for tweets; title + hashtags should fit comfortably
- Image size limit: <5MB for simple upload (DALL-E images are typically within this)

**Error Handling**:
- Authentication errors: Log and mark post as failed
- Rate limit errors: Mark as failed, will retry on next scheduler run
- Network errors: Mark as failed with error message
