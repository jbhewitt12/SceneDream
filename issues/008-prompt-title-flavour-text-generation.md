# Prompt Title and Flavour Text Generation

## Overview
Add `title` and `flavour_text` columns to the `image_prompts` table and create a dedicated service to generate creative, engaging titles and flavour text for image prompts suitable for social media sharing. The service should be called after prompt generation and include a backfill method for existing prompts.

## Problem Statement

**Current limitations**:
- Image prompts lack user-facing titles that make them shareable or memorable
- No engaging copy exists for social media posts featuring generated images
- Current technical prompt text is not suitable for public-facing content

**User impact**:
- Cannot easily share images with catchy, context-appropriate titles
- Manual effort required to create engaging social media copy
- No consistent voice/tone for public-facing content

**Business value**:
- Enables automated social media content creation
- Creates engaging, shareable titles that drive interest
- Maintains consistent brand voice while avoiding copyright issues

## Proposed Solution

Add a new `PromptMetadataGenerationService` that:
1. Generates creative titles (1-5 words) for image prompts
2. Generates flavour text (1-2 sentences) suitable for social media
3. Uses Gemini API with specialized instructions for creativity
4. Never references character names or book-specific details (avoid copyright)
5. Balances fun/creative/interesting tones without being cringy

**Architectural approach**:
- Add `title` and `flavour_text` columns to `image_prompts` model (nullable strings)
- Create new service: `backend/app/services/prompt_metadata/prompt_metadata_service.py`
- Service called automatically after prompt generation in `ImagePromptGenerationService`
- Provide backfill CLI command for existing prompts
- Use Gemini 2.5 Pro for high-quality, creative generation

**Key components involved**:
- `backend/models/image_prompt.py`: Add new columns
- `backend/app/services/prompt_metadata/`: New service directory
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`: Integration
- `backend/app/repositories/image_prompt.py`: Add update method if needed
- `backend/app/alembic/versions/`: New migration

**Integration with existing systems**:
- Called within `ImagePromptGenerationService.generate_for_scene()` after LLM response
- Uses existing `ImagePromptRepository` for updates
- Follows existing service patterns (config, error handling, dry-run support)

## Codebase Research Summary

**Relevant existing patterns found**:
1. **Service architecture**: `ImagePromptGenerationService` and `SceneRankingService` provide templates for LLM-based services with config classes
2. **Repository pattern**: `ImagePromptRepository` with create/update methods for persistence
3. **LLM integration**: `gemini_api.json_output()` for structured responses from Gemini
4. **Migration pattern**: Recent migration `3b8d621aa59a` shows column addition pattern for `image_prompts`
5. **CLI pattern**: `image_prompt_generation/main.py` shows backfill command structure

**Files and components that will be affected**:
- `backend/models/image_prompt.py`: Add `flavour_text` column (note: `title` already exists at line 52)
- `backend/app/services/prompt_metadata/prompt_metadata_service.py`: New service
- `backend/app/services/prompt_metadata/main.py`: New CLI for backfill
- `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`: Call metadata service
- `backend/app/repositories/image_prompt.py`: Potentially add bulk update method
- `backend/app/alembic/versions/`: New migration

**Similar features that can serve as reference**:
- `SceneRankingService` (lines 1-200 in scene_ranking_service.py): Service with LLM integration and config
- `ImagePromptGenerationService._invoke_llm()` (lines 786-830): Retry logic and error handling
- `image_prompt_generation/main.py`: CLI with dry-run, batch processing, and filtering

**Potential risks or conflicts identified**:
- `title` column already exists in model (line 52 of image_prompt.py) but may be populated by LLM
- Need to decide if we overwrite existing titles or only populate null ones
- Flavour text must never leak copyrighted content (character names, plot details)
- Balance between "interesting" and "cringy" is subjective—need clear guidelines for LLM

## Context for Future Claude Instances

**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check the current state of `image_prompt.py` model (verify `title` column usage)
3. Review `ImagePromptGenerationService` to understand existing title generation
4. Look at recent migrations to understand current schema state

**Key Decisions Made**:
- **Column names**: `title` (already exists, check if we use it), `flavour_text` (new, Text type)
- **LLM model**: Gemini 2.5 Pro (higher quality for creative, engaging metadata)
- **Temperature**: 0.8-0.9 for creative, varied outputs
- **Backfill strategy**: Only populate null values by default, add `--force` flag to overwrite
- **Integration point**: Called after main prompt generation but before returning records
- **Service isolation**: Separate service (not part of ImagePromptGenerationService) for modularity
- **Error handling**: Non-blocking—if metadata generation fails, still save the prompt
- **Copyright safety**: LLM instructed to use generic sci-fi/fantasy language, no character names

**Deviations from standard patterns**:
- Unlike other services, this one updates existing records rather than creating new ones
- Operates on `ImagePrompt` records rather than raw scene text
- Has lighter error handling (failures shouldn't block prompt persistence)

**Assumptions about the system**:
- `title` column in `image_prompts` may already contain LLM-generated titles from prompt generation
- If title exists, we may want to use it or regenerate it (decision: use existing if present)
- Flavour text is distinct from title and prompt_text (more casual, social media friendly)
- Backfill should be run after migration on existing prompts

## Pre-Implementation Checklist for Each Phase

Before starting implementation:
- [ ] Verify current schema of `image_prompts` table in database
- [ ] Check if `title` column is currently being populated by `ImagePromptGenerationService`
- [ ] Review existing prompts to understand title patterns
- [ ] Confirm Gemini API access and model availability

## Implementation Phases

### Phase 1: Database Schema Update
**Goal**: Add `flavour_text` column to `image_prompts` table

**Dependencies**: None (foundational change)

**Time Estimate**: 20 minutes

**Success Metrics**:
- [ ] New migration file created
- [ ] Migration adds `flavour_text TEXT NULL` column
- [ ] Migration runs successfully (`alembic upgrade head`)
- [ ] Model updated in `backend/models/image_prompt.py`

**Tasks**:
1. Verify current state of `title` column in `backend/models/image_prompt.py`:
   - Confirm it exists at line 52: `title: str | None = Field(default=None, max_length=255)`
   - Check if `ImagePromptGenerationService._build_records()` populates it (line 878)
   - Decision: Keep existing title usage, only add flavour_text

2. Update `backend/models/image_prompt.py`:
   - Add new field after `title` field (around line 53):
   ```python
   flavour_text: str | None = Field(default=None, sa_column=Column(Text))
   ```
   - Follow pattern from `prompt_text` and `notes` fields

3. Create Alembic migration:
   - Run: `cd backend && uv run alembic revision -m "add_flavour_text_to_image_prompts"`
   - Edit generated file to add column:
   ```python
   def upgrade() -> None:
       op.add_column(
           "image_prompts",
           sa.Column("flavour_text", sa.Text(), nullable=True)
       )

   def downgrade() -> None:
       op.drop_column("image_prompts", "flavour_text")
   ```

4. Apply migration:
   - Run: `uv run alembic upgrade head`
   - Verify column exists: `docker compose exec db psql -U postgres -d app -c "\d image_prompts"`

### Phase 2: Create PromptMetadataGenerationService
**Goal**: Build a service that generates title and flavour text for prompts

**Dependencies**: Phase 1 completed

**Time Estimate**: 60 minutes

**Success Metrics**:
- [ ] New service file created with `PromptMetadataGenerationService` class
- [ ] Service generates creative titles (verified by dry-run testing)
- [ ] Service generates flavour text (verified by dry-run testing)
- [ ] Service has config class with temperature, model_name, dry_run options
- [ ] Service includes error handling and retry logic

**Tasks**:
1. Create service directory and files:
   - Create `backend/app/services/prompt_metadata/` directory
   - Create `backend/app/services/prompt_metadata/__init__.py`
   - Create `backend/app/services/prompt_metadata/prompt_metadata_service.py`

2. Create config dataclass in `prompt_metadata_service.py`:
   ```python
   @dataclass(slots=True)
   class PromptMetadataConfig:
       model_vendor: str = "google"
       model_name: str = "gemini-2.5-pro"
       temperature: float = 0.85
       max_output_tokens: int = 512
       retry_attempts: int = 2
       retry_backoff_seconds: float = 1.0
       fail_on_error: bool = False
       overwrite_existing: bool = False
   ```

3. Create `PromptMetadataGenerationService` class:
   - Constructor: `__init__(self, session: Session, config: PromptMetadataConfig | None = None)`
   - Main method: `generate_metadata_for_prompt(prompt: ImagePrompt | UUID) -> ImagePrompt | dict`
   - Method should return updated prompt (or dict if dry-run)

4. Implement LLM prompt builder `_build_metadata_prompt()`:
   - Input: `ImagePrompt` record
   - Extract: `prompt_text`, `style_tags`, `attributes`
   - Construct prompt with instructions:
     - "Generate a catchy title (1-5 words) and engaging flavour text (1-2 sentences)"
     - "Style should be fun, creative, or interesting—avoid being cringy or over-the-top"
     - "Never reference character names, book titles, or plot-specific details"
     - "Use generic sci-fi/fantasy language that captures the mood and visual style"
     - "Flavour text should work as social media copy for the image"
   - Return JSON schema: `{"title": "string", "flavour_text": "string"}`

5. Implement LLM invocation `_invoke_llm()`:
   - Call `gemini_api.json_output()` with built prompt
   - Add retry logic (follow pattern from `ImagePromptGenerationService._invoke_llm()` lines 786-830)
   - Return parsed JSON response

6. Implement metadata update logic in `generate_metadata_for_prompt()`:
   - Check if `overwrite_existing=False` and metadata exists, skip update
   - Call `_build_metadata_prompt()` and `_invoke_llm()`
   - Parse response and extract title + flavour_text
   - Update prompt record using repository or direct session update
   - Return updated prompt

7. Implement batch method `generate_metadata_for_prompts()`:
   - Accept list of prompts
   - Iterate with progress logging
   - Handle errors gracefully (log and continue)
   - Return list of results or None for failures

### Phase 3: Integrate with ImagePromptGenerationService
**Goal**: Automatically generate metadata after prompt creation

**Dependencies**: Phase 2 completed

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Metadata service called after prompt generation
- [ ] New prompts have title and flavour_text populated
- [ ] Failure in metadata generation doesn't block prompt creation
- [ ] Dry-run mode respects metadata generation (preview only)

**Tasks**:
1. Update `ImagePromptGenerationService.generate_for_scene()`:
   - After `_prompt_repo.bulk_create()` call (line 319-323)
   - Add metadata generation step (if not dry-run):
   ```python
   # Generate metadata for new prompts
   if not config.dry_run:
       try:
           metadata_service = PromptMetadataGenerationService(
               self._session,
               config=PromptMetadataConfig(fail_on_error=False)
           )
           for prompt in created:
               metadata_service.generate_metadata_for_prompt(prompt)
       except Exception as exc:
           logger.warning("Metadata generation failed: %s", exc)
           # Non-blocking: continue even if metadata generation fails
   ```

2. Import `PromptMetadataGenerationService` at top of file:
   - Add: `from app.services.prompt_metadata.prompt_metadata_service import PromptMetadataGenerationService, PromptMetadataConfig`

3. Test integration:
   - Run `uv run python -m app.services.image_prompt_generation.main run --limit 1 --dry-run`
   - Verify metadata appears in preview output
   - Run without dry-run and check database for populated fields

4. Handle remix variant generation:
   - Update `generate_remix_variants()` similarly (after line 499-505)
   - Add same metadata generation step for remix prompts

### Phase 4: Create Backfill CLI
**Goal**: Provide a command to generate metadata for existing prompts

**Dependencies**: Phase 2 completed

**Time Estimate**: 45 minutes

**Success Metrics**:
- [ ] CLI command `backfill` created
- [ ] Command processes prompts in batches
- [ ] Command supports filtering (book, date range, missing metadata only)
- [ ] Command has dry-run mode
- [ ] Progress is logged clearly

**Tasks**:
1. Create CLI file `backend/app/services/prompt_metadata/main.py`:
   - Copy structure from `image_prompt_generation/main.py` as reference
   - Create `_build_parser()` function with subparsers

2. Add `backfill` subcommand to parser:
   - Arguments:
     - `--book-slug` (optional): Filter by book
     - `--limit` (default: 100): Max prompts to process
     - `--batch-size` (default: 10): Process N at a time
     - `--overwrite` (flag): Regenerate even if metadata exists
     - `--dry-run` (flag): Preview without updating
     - `--created-after` (optional): ISO date filter

3. Implement `_handle_backfill()` function:
   - Query prompts using `ImagePromptRepository`:
     - If `--book-slug`: use `list_for_book()`
     - Else: use custom query to get all prompts
   - Filter where `flavour_text IS NULL` (unless `--overwrite`)
   - Process in batches with progress logging
   - Call `PromptMetadataGenerationService.generate_metadata_for_prompts()`
   - Print summary JSON with counts

4. Add main entry point:
   ```python
   def main(argv: list[str] | None = None) -> int:
       logging.basicConfig(level=logging.INFO)
       parser = _build_parser()
       args = parser.parse_args(argv)
       if args.command == "backfill":
           return _handle_backfill(args)
       return 2

   if __name__ == "__main__":
       raise SystemExit(main())
   ```

5. Add query method to `ImagePromptRepository` if needed:
   - Method: `list_all(*, limit: int | None = None, offset: int | None = None, missing_metadata: bool = False)`
   - Filter: `WHERE flavour_text IS NULL` if `missing_metadata=True`

### Phase 5: Testing and Validation
**Goal**: Verify metadata generation works correctly and produces quality output

**Dependencies**: All previous phases completed

**Time Estimate**: 30 minutes

**Success Metrics**:
- [ ] Manual test of single prompt metadata generation
- [ ] Backfill command runs on sample data
- [ ] Generated titles are concise and engaging
- [ ] Flavour text avoids copyright issues (no character names)
- [ ] Integration with prompt generation verified
- [ ] Linting passes

**Tasks**:
1. Test single prompt generation:
   - Find existing prompt ID: `docker compose exec db psql -U postgres -d app -c "SELECT id FROM image_prompts LIMIT 1"`
   - Run service method directly in Python shell or write test script:
   ```python
   from sqlmodel import Session
   from app.core.db import engine
   from app.services.prompt_metadata.prompt_metadata_service import PromptMetadataGenerationService
   from uuid import UUID

   with Session(engine) as session:
       service = PromptMetadataGenerationService(session)
       result = service.generate_metadata_for_prompt(UUID("..."))
       print(result.title)
       print(result.flavour_text)
   ```

2. Test backfill command:
   - Run: `uv run python -m app.services.prompt_metadata.main backfill --limit 5 --dry-run`
   - Verify output shows generated metadata
   - Run without dry-run: `uv run python -m app.services.prompt_metadata.main backfill --limit 5`
   - Check database: `SELECT title, flavour_text FROM image_prompts WHERE flavour_text IS NOT NULL LIMIT 5`

3. Test integration with prompt generation:
   - Run: `uv run python -m app.services.image_prompt_generation.main run --book-slug excession-iain-m-banks --limit 1`
   - Check created prompts have metadata populated

4. Quality check on generated content:
   - Review 10-20 generated titles and flavour texts
   - Verify no character names or book-specific references
   - Verify tone is appropriate (not cringy, not too dry)
   - Adjust LLM prompt if needed

5. Run linting:
   - `cd backend && uv run bash scripts/lint.sh`
   - Fix any issues

6. Test error handling:
   - Simulate LLM failure (disconnect network or mock API)
   - Verify prompt generation still succeeds even if metadata fails
   - Check logs for appropriate warnings

## System Integration Points

**Database Tables**:
- **Read/Write**: `image_prompts` (add `flavour_text` column, update records)

**External APIs**:
- **Gemini API**: Generate title and flavour text via `gemini_api.json_output()`

**Message Queues**: None

**WebSockets**: None

**Cron Jobs**: None (manual backfill via CLI)

**Cache Layers**: None

## Technical Considerations

**Performance**:
- Metadata generation adds ~2-4 seconds per prompt (Gemini 2.5 Pro provides higher quality)
- For batch operations, process 10-20 at a time to avoid rate limits
- Non-blocking in integration (doesn't slow down main workflow)

**Security**:
- Ensure LLM cannot leak copyrighted content (character names, book details)
- Use clear instructions in prompt to avoid sensitive references

**Database**:
- New column: `flavour_text TEXT NULL` (nullable)
- Existing column: `title VARCHAR(255) NULL` (already exists, may be populated)
- No indexes needed (metadata not used for queries)
- Migration is additive only (safe rollback)

**API Design**:
- No new API endpoints needed (service layer only)
- Future enhancement: Could expose via API for manual regeneration

**Error Handling**:
- Metadata generation failures should log warnings but not raise exceptions
- Retry logic for transient LLM errors
- Graceful degradation: prompts without metadata are still usable

**Monitoring**:
- Log metadata generation requests (prompt ID, execution time)
- Log failures with error details
- Track success rate for quality monitoring

## Testing Strategy

1. **Unit Tests**: Not required (LLM integration, per CLAUDE.md guidelines)
2. **Manual Verification**:
   - Run service on 5 sample prompts, verify output quality
   - Run backfill command on 10 prompts, check database
   - Generate new prompts and verify metadata is populated
   - Verify titles are 1-5 words, flavour text is 1-2 sentences
   - Check no character names appear in generated content
3. **Performance Check**:
   - Time backfill of 100 prompts, should complete in ~2-3 minutes

## Acceptance Criteria

- [ ] All phases completed successfully
- [ ] Migration applied and `flavour_text` column exists
- [ ] `PromptMetadataGenerationService` generates creative, appropriate metadata
- [ ] Integration with `ImagePromptGenerationService` works (new prompts have metadata)
- [ ] Backfill CLI command processes existing prompts
- [ ] Generated content avoids character names and book-specific details
- [ ] Metadata generation failures don't block prompt creation
- [ ] Code follows project conventions (4 spaces, snake_case, type hints)
- [ ] Linting passes (`uv run bash scripts/lint.sh`)

## Quick Reference Commands

- **Run backend locally**: `cd backend && uv run fastapi dev app/main.py`
- **Apply migration**: `cd backend && uv run alembic upgrade head`
- **Check database schema**: `docker compose exec db psql -U postgres -d app -c "\d image_prompts"`
- **Test metadata service**: `cd backend && uv run python -m app.services.prompt_metadata.main backfill --limit 5 --dry-run`
- **Generate new prompts with metadata**: `cd backend && uv run python -m app.services.image_prompt_generation.main run --limit 1`
- **Backend linting**: `cd backend && uv run bash scripts/lint.sh`
- **View prompts with metadata**: `docker compose exec db psql -U postgres -d app -c "SELECT id, title, flavour_text FROM image_prompts WHERE flavour_text IS NOT NULL LIMIT 10"`

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
