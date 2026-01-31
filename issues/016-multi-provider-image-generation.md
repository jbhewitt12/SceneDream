# Multi-Provider Image Generation Support

## Overview
Refactor the image generation system to support multiple providers through an abstract base class and registry pattern, while keeping DALLE3 as the only current implementation.

## Problem Statement
- **Current limitation**: The image generation system is tightly coupled to OpenAI's DALL-E 3 API
- **User impact**: Cannot easily switch between or add new image generation providers (e.g., Stability AI, Midjourney API, local models)
- **Business value**: A provider-agnostic architecture enables cost optimization, quality comparisons, and future flexibility

## Proposed Solution
- Create an abstract base class `ImageGenerationProvider` that all providers must implement
- Implement a registry pattern for provider discovery and selection
- Refactor existing DALL-E implementation to use the new abstraction
- Add environment variable configuration for default provider/model
- Update frontend to display provider/model info and filter by provider

## Codebase Research Summary

### Relevant Existing Patterns
- Service layer pattern: `backend/app/services/image_generation/image_generation_service.py` orchestrates image generation
- Current DALL-E API: `backend/app/services/image_generation/dalle_image_api.py` handles OpenAI calls
- Repository pattern: `backend/app/repositories/generated_image_repository.py` for database operations
- Settings pattern: `backend/app/core/config.py` uses Pydantic BaseSettings for environment config

### Files and Components Affected
- `backend/app/services/image_generation/dalle_image_api.py` - refactor to class-based provider
- `backend/app/services/image_generation/image_generation_service.py` - use registry instead of direct import
- `backend/app/services/image_generation/main.py` - update CLI defaults
- `backend/app/core/config.py` - add new settings
- `backend/app/api/routes/generated_images.py` - add providers endpoint
- `backend/app/repositories/generated_image_repository.py` - add distinct providers query
- `frontend/src/routes/_layout/generated-images.tsx` - add filter, update display

### Database
- Existing `provider` and `model` fields in `GeneratedImage` model will be reused
- No migration needed - existing images remain as-is

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes
4. Look for TODO/FIXME comments in affected files

**Key Decisions Made**:
- **Abstraction**: Abstract base class that providers must implement (not a protocol)
- **Configuration**: Environment variable for default provider (DEFAULT_IMAGE_PROVIDER, DEFAULT_IMAGE_MODEL)
- **Database**: Reuse existing `provider`/`model` fields - no migration needed
- **Migration**: Leave existing images as-is (no backfill)
- **Frontend Display**: Replace aspect ratio/tags with provider/model badges
- **Frontend Filter**: Dynamic filter based on used providers (fetched from API)
- **Provider Selection**: Registry pattern with class-level registration

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify all dependencies from previous phases
- [ ] Read the latest version of files you'll modify

## Implementation Phases

### Phase 1: Backend Provider Abstraction

**Goal**: Create the abstract base class and registry, refactor DALL-E to use it

**Dependencies**: None

**Success Metrics**:
- [ ] `base_provider.py` exists with `ImageGenerationProvider` ABC and `GeneratedImageResult` dataclass
- [ ] `provider_registry.py` exists with `ProviderRegistry` class
- [ ] `DalleProvider` class implements the interface and registers itself
- [ ] `image_generation_service.py` uses registry to get providers
- [ ] Existing image generation still works (no regression)
- [ ] Lint passes

**Tasks**:

1. Create `backend/app/services/image_generation/base_provider.py`:
   - Define `GeneratedImageResult` dataclass with fields: `image_data: bytes | None`, `image_url: str | None`, `revised_prompt: str | None`, `error: str | None`
   - Define `ImageGenerationProvider` ABC with abstract methods:
     - `provider_name` property (str)
     - `supported_models` property (list[str])
     - `generate_image()` async method
     - `get_supported_sizes()` method
     - `validate_config()` method

2. Create `backend/app/services/image_generation/provider_registry.py`:
   - Define `ProviderRegistry` class with class methods:
     - `register(provider)` - add provider to registry
     - `get(name)` - get provider by name
     - `list_providers()` - list all registered provider names

3. Refactor `backend/app/services/image_generation/dalle_image_api.py`:
   - Create `DalleProvider(ImageGenerationProvider)` class
   - Move existing `generate_images()` logic into `generate_image()` method
   - Implement all abstract methods
   - Keep helper functions `save_image_from_url()` and `save_image_from_b64()` as module-level
   - Register provider at module level: `ProviderRegistry.register(DalleProvider())`

4. Update `backend/app/services/image_generation/image_generation_service.py`:
   - Import `ProviderRegistry` and ensure dalle provider is imported (for registration)
   - In `_execute_single_task()`, get provider via `ProviderRegistry.get(task.provider)`
   - Call `provider.generate_image()` instead of direct dalle_image_api call

5. Add settings to `backend/app/core/config.py`:
   - Add `DEFAULT_IMAGE_PROVIDER: str = "openai"`
   - Add `DEFAULT_IMAGE_MODEL: str = "dall-e-3"`

6. Update `.env.example` with new settings documentation

7. Update `backend/app/services/image_generation/main.py`:
   - Update argparse defaults to use `settings.DEFAULT_IMAGE_PROVIDER` and `settings.DEFAULT_IMAGE_MODEL`

---

### Phase 2: Backend API Endpoint

**Goal**: Add endpoint to get list of used providers for frontend filtering

**Dependencies**: Phase 1 complete

**Success Metrics**:
- [ ] GET `/api/v1/generated-images/providers` returns list of distinct providers
- [ ] Repository method `get_distinct_providers()` works correctly
- [ ] Lint passes

**Tasks**:

1. Add method to `backend/app/repositories/generated_image_repository.py`:
   - Add `get_distinct_providers()` async method
   - Query for distinct non-null provider values from GeneratedImage table

2. Add endpoint to `backend/app/api/routes/generated_images.py`:
   - Add `GET /providers` endpoint
   - Return list of strings from repository

3. Regenerate frontend client:
   - Run `scripts/generate-client.sh`

---

### Phase 3: Frontend Changes

**Goal**: Add provider filter and update image card display

**Dependencies**: Phase 2 complete (client regenerated)

**Success Metrics**:
- [ ] Provider filter dropdown appears and works
- [ ] Image cards show provider/model instead of aspect ratio/tags
- [ ] Frontend lint passes

**Tasks**:

1. Update `frontend/src/routes/_layout/generated-images.tsx`:
   - Add `provider` to search params schema (zod)
   - Add state/query for fetching providers from new endpoint
   - Add provider `<Select>` filter next to existing filters
   - Update image card display:
     - Remove aspect ratio badge
     - Remove tags/style badges
     - Add provider/model badge (e.g., "openai / dall-e-3")

2. Run frontend lint: `cd frontend && npm run lint`

---

## System Integration Points

- **Database Tables**: `GeneratedImage` (read for providers, existing provider/model fields used)
- **External APIs**: OpenAI DALL-E API (unchanged behavior)
- **Message Queues**: None
- **WebSockets**: None
- **Cron Jobs**: None
- **Cache Layers**: None

## Technical Considerations

- **Performance**: No impact - registry lookup is O(1), abstraction adds minimal overhead
- **Security**: No new security concerns - API keys handled same as before via settings
- **Database**: No schema changes required
- **API Design**: Single new endpoint `/providers` returns `list[str]`
- **Error Handling**: Provider's `validate_config()` method allows checking configuration at startup
- **Monitoring**: Existing logging preserved

## Testing Strategy

1. **Unit Tests**:
   - Test `DalleProvider` class methods (validate_config, get_supported_sizes)
   - Test `ProviderRegistry` registration and retrieval

2. **Integration Tests**:
   - Test `/api/v1/generated-images/providers` endpoint returns correct data

3. **Manual Verification**:
   - Run CLI with `--dry-run` to verify provider/model defaults work
   - Check generated images page shows provider filter
   - Verify images display provider/model correctly

## Acceptance Criteria

- [ ] All automated tests pass
- [ ] Code follows project conventions (as per CLAUDE.md)
- [ ] Linting passes (`uv run bash scripts/lint.sh` and `cd frontend && npm run lint`)
- [ ] Feature works as described in the problem statement
- [ ] Error cases are handled gracefully
- [ ] Existing image generation works without regression

## Quick Reference Commands

- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Run tests**: `cd backend && uv run pytest`
- **Lint check**: `uv run bash scripts/lint.sh`
- **Frontend lint**: `cd frontend && npm run lint`
- **CLI dry run**: `cd backend && uv run python -m app.services.image_generation.main --provider openai --model dall-e-3 --dry-run`
- **Regenerate client**: `./scripts/generate-client.sh`

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
