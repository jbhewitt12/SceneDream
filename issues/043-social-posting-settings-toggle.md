# Add a Settings Toggle for Social Media Posting Features

## Overview
Add a global Settings toggle that enables or disables social media posting features. The setting should default to `off`. When it is off, the frontend should hide all social-posting UI and all social-posting text outside the Settings page, while keeping the image approval workflow intact.

## Problem Statement
Social media posting is currently treated as a first-class part of the generated-images experience:
- the generated-images gallery exposes a `Posted` filter
- image cards show a posted badge and a queue-for-posting button
- the image modal fetches posting status and renders a `Review and publishing` section with social-posting copy
- posting endpoints and the background scheduler remain active independently of any user-facing setting

This does not match the desired product default. Most users are likely to care about approval, remixing, and image generation, but not posting. The UI should therefore default to a simpler experience and only surface social-posting features when a user explicitly enables them in Settings.

## Proposed Solution
Introduce a persisted boolean setting, `social_posting_enabled`, stored in `app_settings` and exposed through the existing Settings API bundle. Default it to `false`.

Use that setting as the source of truth across both backend and frontend:
- Settings page: expose a toggle and explanatory copy
- Generated-images frontend: hide all social-posting actions, filters, badges, status panels, and social-posting copy when disabled
- Approval controls: remain visible and unchanged
- Backend posting routes/services/scheduler: respect the setting so disabling the feature pauses posting behavior instead of only hiding UI

Existing `social_media_posts` data should remain in the database. Turning the feature off should hide and pause the feature, not delete history.

## Codebase Research Summary

### Current persisted settings surface
- `backend/models/app_settings.py`
  - stores singleton settings for pipeline defaults only
- `backend/app/schemas/app_settings.py`
  - `AppSettingsRead` and `AppSettingsUpdateRequest` currently expose default scenes-per-run and default prompt art-style only
- `backend/app/api/routes/settings.py`
  - `GET /api/v1/settings` returns the settings bundle consumed by the frontend
  - `PATCH /api/v1/settings` updates persisted settings
- `frontend/src/routes/_layout/settings.tsx`
  - renders `Pipeline Defaults` and `Random Style Mix` sections only

### Current frontend social-posting surfaces
- `frontend/src/routes/_layout/generated-images.tsx`
  - includes a `Posted` filter in the gallery filters
  - tracks `posted` in the route search schema and sends it to the API
  - wires queue-for-posting mutations into cards and the modal
- `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx`
  - shows a posted icon badge when `image.has_been_posted`
  - shows the queue-for-posting button when the image is approved and not already posted
- `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`
  - always runs the posting-status query when open
  - renders `Review and publishing`
  - renders a `Social media` block, `Queue for Posting` CTA, service status cards, and fallback copy mentioning social sharing/publishing

### Current backend social-posting behavior
- `backend/app/api/routes/generated_images.py`
  - includes posting-related fields on generated-image list items (`has_been_posted`, `is_queued`)
  - supports `posted` filtering on list endpoints
  - exposes `/{image_id}/queue-for-posting`, `/{image_id}/posting-status`, and `/retry-failed-posts`
- `backend/app/services/social_posting/social_posting_service.py`
  - queues images and processes posting independently of any persisted user setting
- `backend/app/services/social_posting/scheduler.py`
  - starts background queue processing when provider-level env config is enabled

## Key Decisions
- Store the toggle in `AppSettings` as `social_posting_enabled: bool = False`.
- Treat the setting as a true feature gate, not a cosmetic frontend-only switch.
- Preserve approval controls regardless of the setting state.
- Preserve existing `social_media_posts` rows and status history when the feature is turned off.
- When disabled, social-posting routes should reject or no-op cleanly, and the scheduler should skip queue processing.
- Remove social-posting wording from non-Settings frontend copy when the feature is disabled. The modal review section should still exist for approval, but its wording should no longer mention publishing unless the feature is enabled.

## Implementation Plan

### Phase 1: Add the persisted setting and API contract
**Goal**: make social-posting availability part of the canonical app settings payload.

**Tasks**:
- Add `social_posting_enabled` to `backend/models/app_settings.py` with a default of `False`.
- Create an Alembic migration that adds the column and backfills existing singleton rows to `false`.
- Extend `backend/app/schemas/app_settings.py`:
  - `AppSettingsRead`
  - `AppSettingsUpdateRequest`
- Update `backend/app/api/routes/settings.py` so `GET /settings` returns the new field and `PATCH /settings` accepts updates to it.
- Regenerate any frontend client types if the OpenAPI schema changes are committed.

**Verification**:
- [ ] Fresh installs default `social_posting_enabled` to `false`
- [ ] Existing databases migrate cleanly and read back `false`
- [ ] `GET /api/v1/settings` includes the new field
- [ ] `PATCH /api/v1/settings` persists changes to the field

### Phase 2: Enforce the feature gate in backend posting flows
**Goal**: ensure turning the setting off actually pauses social-posting behavior.

**Tasks**:
- Add a small helper at the service or route boundary for reading the global setting from `AppSettingsRepository`.
- Update `backend/app/services/social_posting/social_posting_service.py` to short-circuit when `social_posting_enabled` is `false`.
  - `queue_image()` should reject new queue requests
  - `process_queue()` should no-op without posting queued items
  - `retry_failed()` should no-op or reject consistently
- Update `backend/app/services/social_posting/scheduler.py`:
  - avoid processing the queue when the setting is disabled
  - decide whether scheduler startup should be skipped entirely or whether jobs should remain registered but no-op; either is fine as long as disabled means no posting work happens
- Update posting routes in `backend/app/api/routes/generated_images.py` to return a clear disabled response for:
  - `POST /{image_id}/queue-for-posting`
  - `GET /{image_id}/posting-status`
  - `POST /retry-failed-posts`
- Decide whether generated-image list endpoints should continue returning posting flags while disabled. Recommended approach:
  - keep the stored flags in backend responses for compatibility
  - let frontend ignore them when the feature is disabled

**Verification**:
- [ ] Disabled setting blocks new queue attempts
- [ ] Disabled setting prevents scheduled/background posting
- [ ] Re-enabling the setting allows posting again without data loss
- [ ] Existing queued/posted history remains intact across disable/enable cycles

### Phase 3: Add the Settings UI toggle
**Goal**: let users discover and control the feature from Settings.

**Tasks**:
- Update `frontend/src/api/settings.ts` and generated client types for the new settings field.
- Add a new Settings section, for example `Social Media Posting`, to `frontend/src/routes/_layout/settings.tsx`.
- Add a toggle/switch control bound to `settings.social_posting_enabled`.
- Add concise explanatory copy that only appears in Settings, for example:
  - enabling shows posting actions and status in generated images
  - disabling hides those UI surfaces and pauses posting behavior
- Include the new field in the existing save/reset flow for pipeline defaults, or split social settings into its own save action if that produces a cleaner UX.

**Verification**:
- [ ] Settings page loads the current toggle state
- [ ] Users can save the toggle on and off
- [ ] Refreshing the page preserves the saved state
- [ ] Default state renders as off

### Phase 4: Remove social-posting UI and text from generated-images when disabled
**Goal**: present a clean non-social workflow by default while preserving approval.

**Tasks**:
- Update `frontend/src/routes/_layout/generated-images.tsx` to fetch the settings bundle or otherwise consume `social_posting_enabled`.
- Hide the `Posted` filter entirely when the setting is off.
- Remove hidden filter side effects when disabled:
  - do not keep applying `posted=false` in route state or API calls
  - ignore legacy `posted` query params when the feature is off
- Update `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx`:
  - hide the posted badge
  - hide the queue-for-posting button
  - keep thumbs up/down approval buttons unchanged
- Update `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx`:
  - skip the posting-status query when disabled
  - remove the `Social media` panel entirely
  - keep the approval block visible
  - rename or restructure `Review and publishing` so disabled mode contains no publishing language, for example `Review`
- Remove all non-Settings social-posting copy when disabled, including strings like:
  - `Posted`
  - `Queue for Posting`
  - `Posted to social media`
  - `Approve this image first to unlock social sharing.`
  - `No social posts yet. Queue this image when you are ready to publish it.`

**Verification**:
- [ ] With the setting off, generated-images shows no social-posting controls, badges, filters, or text
- [ ] Approval controls still work in gallery cards and modal
- [ ] With the setting on, current posting UI reappears
- [ ] Disabled mode does not issue posting-status queries from the modal
- [ ] Disabled mode does not send `posted` filters from the gallery

### Phase 5: Tests and verification
**Goal**: cover the new settings contract, backend enforcement, and frontend gating behavior.

**Tasks**:
- Backend repository tests:
  - extend `backend/app/tests/repositories/test_settings_repositories.py` for the new default and persistence behavior
- Backend route tests:
  - extend `backend/app/tests/api/routes/test_settings.py` for read/update behavior
  - extend `backend/app/tests/api/routes/test_generated_images.py` for disabled posting routes and any changed list behavior
- Backend service tests:
  - add `backend/app/tests/services/test_social_posting_service.py` covering disabled short-circuit behavior
- Frontend static/build verification:
  - update the generated client if needed
  - run lint/build after the UI changes
- Manual verification:
  - confirm generated-images has approval only when the toggle is off
  - confirm the social-posting UI returns after enabling the toggle in Settings

**Verification**:
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npm run build` passes

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/alembic/versions/<new_revision>_add_social_posting_enabled_to_app_settings.py` | Create |
| `backend/models/app_settings.py` | Modify |
| `backend/app/schemas/app_settings.py` | Modify |
| `backend/app/api/routes/settings.py` | Modify |
| `backend/app/repositories/app_settings.py` | Modify if helper accessors are added |
| `backend/app/api/routes/generated_images.py` | Modify |
| `backend/app/services/social_posting/social_posting_service.py` | Modify |
| `backend/app/services/social_posting/scheduler.py` | Modify |
| `backend/app/tests/repositories/test_settings_repositories.py` | Modify |
| `backend/app/tests/api/routes/test_settings.py` | Modify |
| `backend/app/tests/api/routes/test_generated_images.py` | Modify |
| `backend/app/tests/services/test_social_posting_service.py` | Create |
| `frontend/src/api/settings.ts` | Modify |
| `frontend/src/routes/_layout/settings.tsx` | Modify |
| `frontend/src/routes/_layout/generated-images.tsx` | Modify |
| `frontend/src/components/GeneratedImages/GeneratedImageCard.tsx` | Modify |
| `frontend/src/components/GeneratedImages/GeneratedImageModal.tsx` | Modify |
| `frontend/src/client/*` | Regenerate if OpenAPI output is checked in |

## Testing Strategy
- Backend automated coverage:
  - verify the new setting defaults to `false`
  - verify settings updates persist round-trip
  - verify posting routes reject or no-op when disabled
  - verify the social-posting service and scheduler do not process queue items while disabled
- Frontend behavior:
  - off state: no social-posting filter, badges, buttons, panel, or copy in generated-images
  - off state: approval buttons still show and still update approval
  - on state: posting UI and status return without regressions
  - route state: no hidden `posted=false` behavior when the filter is hidden
- Required commands:
  - `cd backend && uv run pytest`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`

## Acceptance Criteria
- [ ] `AppSettings` includes a persisted `social_posting_enabled` field with default `false`
- [ ] Settings page exposes a toggle for social media posting
- [ ] With the toggle off, no social media posting features appear anywhere in the frontend outside Settings
- [ ] With the toggle off, no non-Settings frontend copy mentions social posting, sharing, posting, or publishing
- [ ] Approval buttons remain available with the toggle off
- [ ] Backend posting routes and background processing do not continue posting while the toggle is off
- [ ] Existing social-post history is preserved when the feature is disabled
- [ ] Re-enabling the toggle restores the posting UI and functionality
- [ ] `cd backend && uv run pytest` passes
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npm run build` passes
