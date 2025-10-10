# SceneDream Implementation Plan

## Overview

SceneDream extracts visually compelling scenes from sci-fi EPUBs (e.g., Ian M. Banks novels), ranks them by visual/AI generation potential, generates optimized image prompts, and creates images using DALL-E 3. The complete workflow is database-backed using PostgreSQL for persistence and tracking.

**Pipeline**: EPUB → Scene Extraction → Scene Ranking → Image Prompt Generation → Image Generation

---

## Architecture Overview

The system is built on the FastAPI full-stack template with:
- **Backend**: FastAPI + SQLModel (ORM) + PostgreSQL + Alembic migrations
- **Frontend**: React + TypeScript + Vite + TanStack Router/Query + Chakra UI
- **AI Integration**: Gemini (extraction/prompts), Grok (refinement/ranking), DALL-E 3 (images)

All data is persisted in PostgreSQL tables: `scene_extractions`, `scene_rankings`, `image_prompts`, `generated_images`.

---

## Implementation Steps

### 1. Scene Extraction Pipeline *(Implemented)*

**Purpose**: Parse EPUBs and extract scenes with high visual/cinematic potential.

**Implementation**:
- **Service**: `backend/app/services/scene_extraction/scene_extraction.py`
  - `SceneExtractor` reads EPUB chapters with BeautifulSoup
  - Normalizes paragraph text with 1-indexed paragraph numbering
  - Chunks chapters (~12k characters with paragraph overlap to prevent truncation)
  - Sends chunks to Gemini 2.5 Pro via `gemini_api.json_output()` using `SCENE_EXTRACTION_SCHEMA_TEXT`
  - Deduplicates scenes within and across chunks
  - Assigns sequential scene IDs per chapter

- **Optional Refinement**: `backend/app/services/scene_extraction/scene_refinement.py`
  - Uses Grok via `XAIAPI` to evaluate extracted scenes
  - Applies `REFINEMENT_SCHEMA` to mark scenes as keep/discard
  - Preserves original extraction, adds optional refined excerpts

- **Persistence**: `backend/app/repositories/scene_extraction.py`
  - Stores in `scene_extractions` table via `SceneExtractionRepository`
  - Records: raw/refined text, word/char counts, chunk indices, model metadata, hash signatures
  - Idempotent: skips existing chunk indexes on reruns

- **API Routes**: `backend/app/api/routes/scene_extractions.py`
  - Paginated listings with filters (book, chapter, keep/discard status)
  - Detail views for individual scenes
  - Metadata endpoints for UI consumption

- **CLI**: `backend/app/services/scene_extraction/main.py`
  ```bash
  uv run python -m app.services.scene_extraction.main preview-excession 3 --refine
  uv run python -m app.services.scene_extraction.main extract-excession --refine
  ```

**Database Schema**: `backend/models/scene_extraction.py` (`scene_extractions` table)

---

### 2. Scene Ranking *(Implemented)*

**Purpose**: Score scenes on visual potential, AI generation feasibility, and uniqueness to prioritize the best candidates.

**Implementation**:
- **Service**: `backend/app/services/scene_ranking/`
  - Scores scenes on multiple criteria:
    - Visual potential (epicness, color vibrancy, dynamic action, scale 1-10)
    - AI generation feasibility (avoid overly complex compositions)
    - Uniqueness (novelty compared to typical sci-fi imagery)
  - Uses Grok (`grok-4-fast-reasoning`) or Gemini Flash models
  - Generates composite scores and detailed explanations

- **LLM Strategy**:
  - Multi-model committee approach supported (query multiple model instances, average scores)
  - Feedback loop capability: "Re-rank based on why lower-scored scenes might improve with better prompting"
  - Top 10-20 scenes per book proceed to prompt generation

- **Persistence**: `backend/app/repositories/scene_ranking.py`
  - Stores in `scene_rankings` table via `SceneRankingRepository`
  - Foreign key to `scene_extractions.id`
  - Records: individual scores, composite score, model metadata, reasoning

- **API Routes**: `backend/app/api/routes/scene_rankings.py`
  - List rankings filtered by book/chapter/score threshold
  - Detail views with score breakdowns
  - Sorting by composite score, visual potential, etc.

**Database Schema**: `backend/models/scene_ranking.py` (`scene_rankings` table)

---

### 3. Image Prompt Generation *(Implemented)*

**Purpose**: Convert ranked scenes into detailed, DALL-E 3-optimized image prompts.

**Implementation**:
- **Service**: `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`
  - Generates multiple prompt variants per scene (default: 4)
  - Uses Gemini with embedded `dalle3_sci_fi_prompting_cheatsheet.md` guidelines
  - Includes context window: 3 paragraphs before + 1 after scene (loaded from EPUB at generation time)
  - Structured output includes:
    - `prompt_text`: Full DALL-E 3 prompt
    - `style_tags`: Array of style descriptors (e.g., "cinematic", "hyper-realistic", "Syd Mead-inspired")
    - `attributes`: JSON with camera/lens/composition/aspect_ratio metadata

- **Context Handling** (Important):
  - **Does NOT persist copyrighted text** in database
  - Stores only `context_window` metadata (paragraph span references)
  - Reopens EPUB at generation time to extract context paragraphs

- **Refinement Chain**:
  - Generates initial prompts
  - Optional LLM critique pass: "Does this prompt avoid ambiguities? Suggest improvements for fidelity"
  - Iterates 2-3 times per scene variant

- **Persistence**: `backend/app/repositories/image_prompt.py`
  - Stores in `image_prompts` table via `ImagePromptRepository`
  - Foreign key to `scene_extractions.id`
  - Unique constraint: `(scene_extraction_id, model_name, prompt_version, variant_index)`
  - Records: prompt_text, style_tags, attributes (JSONB), context_window metadata, model info

- **API Routes**: `backend/app/api/routes/image_prompts.py`
  - List prompts for scenes/books
  - Detail views with full prompt text and metadata
  - Filter by variant, style tags, aspect ratio

**Database Schema**: `backend/models/image_prompt.py` (`image_prompts` table)

---

### 4. Image Generation *(Implemented)*

**Purpose**: Generate images from database-stored prompts using DALL-E 3.

**Implementation**:
- **Service**: `backend/app/services/image_generation/dalle_image_api.py`
  - Wraps OpenAI DALL-E 3 API
  - Functions: `generate_images()`, `save_image_from_b64()`, `save_image_from_url()`

- **Input Sources**:
  - Reads prompts from database via `ImagePromptRepository`
  - Can target specific scenes, top-N ranked, or entire book

- **Model Parameters**:
  - Model: `dall-e-3` (fixed)
  - Aspect ratio mapping:
    - `"1:1"` → `1024x1024`
    - `"9:16"` → `1024x1792` (portrait)
    - `"16:9"` → `1792x1024` (landscape)
    - Fallback: `1024x1024`
  - Style: Derived from `style_tags` ("natural" → `style="natural"`, otherwise `"vivid"`)
  - Quality: `"standard"` (drafts) or `"hd"` (finals)
  - Response format: `"b64_json"` (default) or `"url"`

- **File Storage**:
  - Path: `img/generated/<book_slug>/chapter-<N>/scene-<sceneNumber>-v<variant>.png`
  - Auto-creates directory structure
  - Naming convention includes variant index for multiple versions per scene

- **Persistence**: `backend/app/repositories/generated_image.py`
  - Stores in `generated_images` table via `GeneratedImageRepository`
  - Foreign keys: `scene_extraction_id`, `image_prompt_id`
  - Records: storage_path, file_name, provider, model, size, quality, style, aspect_ratio, width, height, bytes_approx, checksum_sha256, request_id, error (nullable)
  - Methods: `create()`, `bulk_create()`, `list_for_scene()`, `list_for_book()`, `mark_failed()`

- **CLI**: `backend/app/services/image_gen_cli.py`
  - Orchestrates end-to-end generation workflows
  - Features:
    - Select scenes by rank threshold or explicit IDs
    - Dry-run mode (lists prompts without API calls)
    - Skip already-rendered outputs (checks database)
    - Error handling and retry logic
    - Batch processing with progress tracking

- **API Routes**: `backend/app/api/routes/generated_images.py`
  - List generated images (filterable by book/chapter/scene)
  - Serve images via static file routes
  - Image metadata and generation stats

- **Configuration**:
  - API Key: `OPENAI_API_KEY` environment variable
  - Dry-run mode available for testing without cost

**Database Schema**: `backend/models/generated_image.py` (`generated_images` table)

---

## Model Relationships

```
scene_extractions (1) ─┬─→ (many) scene_rankings
                       ├─→ (many) image_prompts
                       └─→ (many) generated_images

image_prompts (1) ─────→ (many) generated_images
```

**Key Constraints**:
- `image_prompts`: Unique on `(scene_extraction_id, model_name, prompt_version, variant_index)`
- All IDs are UUIDs
- Foreign keys enforce referential integrity
- Timestamps: `created_at`, `updated_at` (auto-managed)

---

## Frontend Access

All data is accessible via the React frontend at http://localhost:5173:
- **Extracted Scenes**: `/extracted-scenes` (paginated list with filters)
- **Scene Rankings**: `/scene-rankings` (sortable by score)
- **Image Prompts**: (integrated into scene detail views)
- **Generated Images**: `/generated-images` (gallery view with metadata)

API documentation: http://localhost:8000/docs

---

## Future Enhancements

- **Video Generation**: Extend prompt generation for video tools (Runway, Pika, etc.)
- **Multi-model Image Gen**: Support Midjourney, Stable Diffusion, Flux
- **Advanced Ranking**: Implement LLM committee voting with score averaging
- **Prompt Iteration**: Add UI for manual prompt refinement and regeneration
- **Cost Tracking**: Track API costs per scene/book for budget management

