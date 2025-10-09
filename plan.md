# Plan

## Overview

I want to get books written by authors like Ian M. Banks in text format (like epub). Then, I want to use an LLM to extract scenes from the book that would be able to be turned into incredible-looking images or videos. Next, I want to rank the scenes and use an LLM to turn those descriptions into a description that will work well as a prompt for AI image generation. Finally, I want to generate those images or videos.


## Files that already exist

The critical files are in the `backend/app/services/` directory.

## Steps

1. Scene extraction pipeline *(implemented)*

- `backend/app/services/scene_extraction/scene_extraction.py` defines `SceneExtractor`, which reads EPUB chapters with BeautifulSoup, normalizes paragraph text, and chunks each chapter (~12k characters with paragraph overlap) so prompts can reference numbered paragraphs.
- Each chunk is sent through `gemini_api.json_output(...)` (default `gemini-2.5-flash`, temperature 0.0) using the schema in `SCENE_EXTRACTION_SCHEMA_TEXT`; responses are deduplicated, sequential scene ids assigned, and stats returned by `extract_preview` / `extract_book`.
- CLI entry points in `backend/app/services/scene_extraction/main.py` support previewing the first N chapters or running the full Excession book, with a `--refine` flag to enable downstream refinement.
- When refinement is enabled, `XAIAPI` wraps Grok to evaluate each scene via `REFINEMENT_SCHEMA`, marking keep/discard decisions and optional refined excerpts while preserving the original extraction.
- `_persist_chapter_scenes` stores results in the Postgres-backed `scene_extractions` table via `SceneExtractionRepository`, recording raw/refined text, word/char counts, chunk indices, model metadata, and a hash signature; existing chunk indexes are skipped to keep reruns idempotent.
- FastAPI routes (`backend/app/api/routes/scene_extractions.py`) expose paginated listings, detail views, and filter metadata so the stored scenes can be reviewed without touching the CLI.

2. Rank Scenes with LLM

- Use `grok-4-fast-reasoning` to score scenes on criteria like visual potential (e.g., scale of 1-10 for "epicness," "color vibrancy," "dynamic action"), feasibility for AI gen (e.g., avoid overly complex crowds if the tool struggles), and uniqueness.

- LLM-aggressive: Employ a "committee" of LLMs—query the same ranking prompt across 3-5 model instances (or variations) and average scores. To start with, only query Gemini flash as well. Add a feedback loop: "Re-rank based on why lower-scored scenes might improve with better prompting." Top 10-20 scenes proceed.

- Whenever ranking is done, update the file for that scene with standardized JSON that captures all the ranking information. 

3. Convert to Image Prompts with LLM

- For now, let's focus on just creating image prompts, not video prompts. This will make it easier to start with.

- For each ranked scene: LLM prompt `grok-4-fast-reasoning` like: "Transform this scene description into a detailed AI image prompt. Include style (e.g., cinematic, hyper-realistic), lighting, composition, and references to artists like Syd Mead for sci-fi vibes. Optimize for [tool name] to maximize quality."

- LLM-aggressive: Chain refinements—generate initial prompt, then use another LLM to critique ("Does this prompt avoid ambiguities? Suggest improvements for better output fidelity to the book"). Iterate 2-3 times per scene.

- Make an `image_prompts` folder organized into subdirectories by book. Once a prompt is generated and refined save each prompt as a JSON file. For each prompt, we will start the file name with the chapter number, then a dash and then an integer that is the same as the scene it matches and then a short description of the prompt. The integer will be unique and effectively be the ID of the prompt. The JSON should be structured so that there will be many alternates of the prompt potentially in the file.

4. Generate images from prompts

- Use the structured prompts produced in step 3 to create images via the helper in `backend/app/services/image_generation/dalle_image_api.py`.

- Input sources:
  - Preferred: read prompt variants from the database via `ImagePromptRepository` (created by `backend/app/services/image_prompt_generation/image_prompt_generation_service.py`).

- Model and parameters:
  - Default to DALL·E 3 (`model="dall-e-3"`, `n=1`).
  - Map `attributes.aspect_ratio` from the prompt to a DALL·E size:
    - "1:1" → `1024x1024`; "9:16" → `1024x1792`; "16:9" → `1792x1024`.
    - Fallback to `1024x1024` if missing or unrecognized.
  - Choose `style` based on `style_tags` when available (e.g., tags like "natural" → `style="natural"`, otherwise `"vivid"`).
  - Use `quality="standard"` for drafts; allow `quality="hd"` for final renders.

- Storage and naming:
  - Save images to `img/generated/<book_slug>/chapter-<N>/scene-<sceneNumber>-v<variant>.png`.

- Database storage:
  - Create a new SQLModel `GeneratedImage` (table name: `generated_images`) to persist each rendered output and its metadata.
  - Suggested fields: id, sceneExtractionId (FK), imagePromptId (FK), bookSlug, chapterNumber, variantIndex, provider (e.g., "openai"), model (e.g., "dall-e-3"), size, quality, style, aspectRatio, responseFormat, storagePath, fileName, width, height, bytesApprox, checksumSha256, requestId, createdAt, updatedAt, error (nullable).
  - Add a repository `GeneratedImageRepository` with helpers like `create`, `bulk_create`, `list_for_scene`, `list_for_book`, `get_latest_for_prompt`, and `mark_failed`.
  - After saving each image, insert a record with the resolved `storagePath` and all generation parameters; on failures, capture error details.

- Execution flow (CLI or script outline):
  - Select scenes: either top-N ranked or all with prompts for a book.
  - For each scene variant, call `generate_images(prompt_text, api_key, size=..., quality=..., style=..., response_format="b64_json")`.
  - Decode and write the image via `save_image_from_b64(...)` (or `save_image_from_url(...)` if using `response_format="url"`).
  - Log successes/failures and skip already-rendered outputs unless an overwrite flag is provided.
  - Persist a `generated_images` record per output with metadata and the absolute or project-relative image path.

- Configuration:
  - Read the OpenAI API key from environment ( `OPENAI_API_KEY` exists in the environment variables).
  - Provide a dry-run mode that lists which prompts would be rendered and their resolved parameters without making API calls.

