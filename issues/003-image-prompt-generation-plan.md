## Image Prompt Generation Plan

### Goals

- Convert ranked scenes into multiple high-quality AI image prompts using Gemini 2.5 Pro.
- Leverage the multi-genre DALLE3 prompting cheat sheet as embedded guidance to improve prompt craftsmanship.
- Persist each generated prompt (and its metadata) in a new database table modeled after existing `scene_extraction` and `scene_ranking` patterns.
- Expose backend APIs to browse prompts in the frontend with rich filtering and scene context.

### Constraints and inputs

- Model: `gemini-2.5-pro` (vendor: google).
- For each scene, include: the scene’s extracted raw text plus surrounding chapter context: 3 paragraphs before and 1 paragraph after. Do not store copyrighted chapter text; store only spans/metadata. Load paragraphs from the original EPUB via `source_book_path` in `scene_extractions`.
- For each scene, generate X variants (configurable) that intentionally explore different styles/aspects (e.g., camera angle, subject focus, composition, lighting, palette, mood). Each variant should be distinct and should take artistic license inspired by the scene.
- Use `backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md` content verbatim as an embedded guideline section in the LLM prompt.

---

### Phase 1 — Data model, migration, repository

1) Add SQLModel `ImagePrompt` in `backend/models/image_prompt.py` (follows repository patterns from `scene_ranking`).

- Table name: `image_prompts`
- Fields:
  - `id` UUID PK
  - `scene_extraction_id` UUID FK -> `scene_extractions.id` (indexed)
  - `model_vendor` str (e.g., "google")
  - `model_name` str (default "gemini-2.5-pro")
  - `prompt_version` str (e.g., "image-prompts-v1")
  - `variant_index` int (0..X-1) — identifies the variant within a generation set
  - `title` str | None — short label for the variant (e.g., "Kinetic corridor chase")
  - `prompt_text` Text — the actual image prompt text
  - `negative_prompt` Text | None — optional negatives (kept flexible for future generators, don't use this for the first version)
  - `style_tags` JSONB list[str] | None — tags like ["cinematic", "neon", "brutalist"]
  - `attributes` JSONB dict — structured details (composition, camera, lens, aspect_ratio, lighting, palette, references, etc.)
  - `notes` Text | None — optional curator notes; not populated by LLM initially
  - `context_window` JSONB dict — metadata only: {"chapter_number", "paragraph_span": [start, end], "paragraphs_before": 3, "paragraphs_after": 1}; do not store raw copyrighted text
  - `raw_response` JSONB — full LLM response for provenance/debug
  - `temperature` float | None, `max_output_tokens` int | None
  - `llm_request_id` str | None, `execution_time_ms` int | None
  - `created_at` timestamptz, `updated_at` timestamptz
- Relationships:
  - Many `ImagePrompt` belong to one `SceneExtraction` (add `image_prompts` back-populate on `SceneExtraction`)
- Constraints/Indexes:
  - Unique constraint: (`scene_extraction_id`, `model_name`, `prompt_version`, `variant_index`)
  - Indexes: `scene_extraction_id`, `model_name`, `prompt_version`

2) Create Alembic migration in `backend/app/alembic/versions/` to create `image_prompts` with indexes and unique constraint.

3) Add repository `backend/app/repositories/image_prompt.py`:

- Methods:
  - `get(id)`
  - `list_for_scene(scene_extraction_id, newest_first=True, limit: Optional[int])`
  - `list_for_book(book_slug, filters...)` (join via `scene_extractions`)
  - `get_latest_set_for_scene(scene_extraction_id, model_name, prompt_version)`
  - `create(data, commit=False, refresh=True)`
  - `bulk_create(records, commit=False)`
  - `delete_for_scene(scene_extraction_id, prompt_version=None, model_name=None)` (for overwrite workflows)

Acceptance criteria:
- Migration applies cleanly; models import without linter errors; repository methods covered by unit tests with an in-memory or transactional DB session.

---

### Phase 2 — Image Prompt Generation Service

Create `backend/app/services/image_prompt_generation/image_prompt_generation_service.py` with a configuration and a service modeled after `SceneRankingService`.

1) Config `ImagePromptGenerationConfig`:
- `model_vendor: "google"`, `model_name: "gemini-2.5-pro"`
- `prompt_version: "image-prompts-v1"`
- `variants_count: int = 4` (X; configurable)
- `temperature: float = 0.4`, `max_output_tokens: Optional[int]` (set large enough for multiple variants)
- `context_before: int = 3`, `context_after: int = 1`
- `include_cheatsheet_path: str` default to `backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md`
- Runtime flags: `dry_run`, `allow_overwrite`, `autocommit`, `retry_attempts`, `retry_backoff_seconds`, `fail_on_error`

2) Context loader
- Given a `SceneExtraction`, re-open its EPUB (`source_book_path`) and reconstruct the chapter paragraphs (reuse logic from `SceneExtractor` to ensure parity).
- Compute safe bounds: `start = max(1, scene_paragraph_start - context_before)`, `end = scene_paragraph_end + context_after`, clamped to chapter size.
- Build a context section with numbered paragraph headers but DO NOT persist full text; only return lines for prompting in-memory.

3) Prompt builder
- Load the multi-genre cheat sheet file contents and embed as a “Guidelines” section.
- Provide scene metadata (book slug, chapter number/title, scene number, paragraph span).
- Include the scene’s raw excerpt verbatim.
- Include the surrounding context paragraphs (3 before, 1 after) to anchor composition details.
- Instruct the model to output strict JSON with exactly `variants_count` elements, each with fields:
 - Instruct the model to output strict JSON with exactly `variants_count` elements, each with fields:
  - `title: string`
  - `prompt_text: string` (fully ready to paste into image generators)
  - `style_tags: string[]` (e.g., ["cinematic", "high-contrast", "ultra-wide"])
  - `attributes: object` (e.g., { camera: "35mm", lens: "anamorphic", composition: "rule-of-thirds", lighting: "rim light", palette: "teal & orange", aspect_ratio: "16:9", references: ["Syd Mead"] })

Note: do not request a `notes` field from the LLM; keep `notes` null in the DB for optional human curation later.

4) LLM invocation
- Use `app.services.langchain.gemini_api.json_output(...)` with `model_name = config.model_name` and `temperature = config.temperature`.
- Capture `llm_request_id` if present in response metadata; record `execution_time_ms`.
- Don't include any token cap anywhere.

5) Persistence
- Parse JSON, validate list length equals `variants_count`, then `create` one `ImagePrompt` per element using `variant_index`.
- If `allow_overwrite` is false, first check if a run exists for (`scene_extraction_id`, `model_name`, `prompt_version`, any variant_index); if so, return existing set.
- Store only metadata for `context_window`; never persist raw context text.

6) Public methods
- `generate_for_scene(scene: SceneExtraction | UUID, *, prompt_version, variants_count, overwrite=False, dry_run=False) -> list[ImagePrompt] | list[Preview]`
- `generate_for_scenes(scenes: Sequence[...]) -> list[...]` (batch)
- `generate_for_book(book_slug, *, scene_filter, ranked_only=False, top_n=None, ...)`

Acceptance criteria:
- Service generates distinct, guideline‑compliant variants; records persisted with correct uniqueness semantics; unit tests stub `gemini_api` and EPUB loader.

---

### Phase 3 — Backend API endpoints and schemas

1) Schemas in `backend/app/schemas/image_prompt.py`:
- `ImagePromptSceneSummary` (subset of `SceneExtraction`)
- `ImagePromptRead` (full prompt + optional scene summary)
- `ImagePromptListResponse { data: ImagePromptRead[], meta?: object }`

2) Routes in `backend/app/api/routes/image_prompts.py`:
- `GET /image-prompts/scene/{scene_id}` → list prompts for a scene; query params: `limit`, `newest_first`, `model_name?`, `prompt_version?`, `include_scene?`
- `GET /image-prompts/{prompt_id}` → fetch a single prompt
- `GET /image-prompts/book/{book_slug}` → list prompts across a book (filters: `chapter_number?`, `model_name?`, `prompt_version?`, `style_tag?`, pagination)

3) Wire router in `app/api/main.py` and export via `app/api/__init__.py` like others.

Acceptance criteria:
- Endpoints return shapes consistent with schemas; OpenAPI client generation works; pagination and filtering verified locally.

---

### Phase 4 — Frontend UI to browse prompts

1) API client generation
- Run the existing OpenAPI → TS client generation (`frontend/openapi-ts.config.ts`), exposing `/image-prompts/*` routes.

2) Routes and layout
- Add a "Prompts" view under a book/scene context (e.g., in scene detail: tabs for "Extraction", "Ranking", "Prompts").
- Add a book‑level "Prompt Gallery" route to browse all prompts across chapters with filters.

3) Components
- `PromptCard`: shows `title`, key `style_tags`, a 2–3 line `prompt_text` preview with copy‑to‑clipboard, variant index badge, model/prompt_version chips.
- `PromptList`: virtualized grid with pagination and filters (book, chapter, tags, model, prompt_version).
- `SceneContextPanel`: collapsible panel with scene metadata and paragraph span used (not the copyrighted text).

4) UX polish
- Sticky filter bar; responsive grid; monospaced prompt preview; secondary actions for "Copy", "View full".
- Empty states for scenes without prompts; CTA button to "Generate prompts" (calls POST endpoint).

Acceptance criteria:
- Users can filter and view prompts per scene/book; prompt copy interaction works; layout matches existing Chakra theme.
