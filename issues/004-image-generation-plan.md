# Image Generation Plan

This document details Step 4 (image generation) from `plan.md`, broken into phases from database schema through front-end UI.

## Goals

- Convert ranked image prompts into rendered images using DALL·E 3 (initially)
- Persist outputs and metadata in the database with strong idempotency
- Provide a CLI, API routes, and a front-end gallery with a modal carousel that shows image + prompt + raw scene text

## Definitions

- Generated image storage path: `img/generated/<book_slug>/chapter-<N>/scene-<sceneNumber>-v<variant>.png`
- Provider: `openai` (initial), Model: `dall-e-3`
- Aspect ratio → size mapping:
  - 1:1 → `1024x1024`
  - 9:16 → `1024x1792`
  - 16:9 → `1792x1024`
  - Fallback: `1024x1024`
- Default style: derive from `style_tags` when available (e.g., includes "natural" → `natural`; else `vivid`)
- Default quality: `standard` (allow `hd` for final renders)
- Dry-run mode: resolve parameters and display planned work without API calls

---

## Phase 1 — Model migration and repository creation

- New SQLModel: `GeneratedImage` in `backend/models/generated_image.py` (table: `generated_images`).
  - Fields (initial set; camelCase in JSON via schemas):
    - `id: int` (PK)
    - `sceneExtractionId: int` (FK → `scene_extractions.id`, indexed, not null)
    - `imagePromptId: int` (FK → `image_prompts.id`, indexed, not null)
    - `bookSlug: str` (indexed, not null)
    - `chapterNumber: int` (indexed, not null)
    - `variantIndex: int` (0-based variant within a prompt)
    - `provider: str` (e.g., "openai")
    - `model: str` (e.g., "dall-e-3")
    - `size: str` (resolved size, e.g., "1024x1024")
    - `quality: str` ("standard" | "hd")
    - `style: str` ("vivid" | "natural")
    - `aspectRatio: str | None`
    - `responseFormat: str` ("b64_json" | "url")
    - `storagePath: str` (directory path)
    - `fileName: str` (file name only)
    - `width: int | None`
    - `height: int | None`
    - `bytesApprox: int | None`
    - `checksumSha256: str | None` (of file bytes)
    - `requestId: str | None`
    - `createdAt: datetime`
    - `updatedAt: datetime`
    - `error: str | None`
  - Indexes/constraints:
    - Composite unique idempotency key on `(imagePromptId, variantIndex, provider, model, size, quality, style)`
    - Indexes on `bookSlug`, `chapterNumber`, `sceneExtractionId`, `imagePromptId`, `createdAt`
    - FK cascade on delete for prompts/scenes: `RESTRICT` for safety (no accidental deletes)
- Alembic migration in `backend/app/alembic/versions/` to create `generated_images` with indexes and constraints.
- Schemas in `backend/app/schemas/generated_image.py`:
  - `GeneratedImageBase`, `GeneratedImageCreate`, `GeneratedImageRead`
  - `GeneratedImageWithContext` (see Phase 4) including prompt text and raw scene text
- Repository `backend/app/repositories/generated_image.py`:
  - `create`, `bulk_create`
  - `list_for_scene(scene_id, pagination, sort)`
  - `list_for_book(book_slug, chapter=None, pagination)`
  - `get_latest_for_prompt(prompt_id)`
  - `find_existing_by_params(image_prompt_id, variant_index, provider, model, size, quality, style)`
  - `mark_failed(id, error)`

Acceptance:
- Migration runs cleanly; repository CRUD covered by unit tests
- Unique constraint prevents duplicate renders with same parameters

---

## Phase 2 — Image generation service

- New module: `backend/app/services/image_generation/image_generation_service.py`
- Responsibilities:
  - Select prompts and variants to render based on filters (book/chapters/scene/prompt ids, limits)
  - Map aspect ratio to size; derive style from `style_tags`; set quality
  - Call existing `dalle_image_api.generate_images(...)` with resolved parameters
  - Save image to `img/generated/<book_slug>/chapter-<N>/scene-<scene>-v<variant>.png`
  - Compute checksum, capture metadata, and persist `GeneratedImage`
  - Idempotency: skip when an identical output already exists (via repository unique lookup)
  - Dry-run: log the resolved operations without executing API calls
  - Concurrency: bounded parallelism (e.g., `asyncio.Semaphore`) to avoid rate limits
  - Error handling: mark failures with `mark_failed` including error message

Suggested public surface:

```python
class ImageGenerationService:
    def __init__(self, db_session_factory, image_repo, prompt_repo, scene_repo, dalle_api):
        ...

    async def generate_for_selection(
        self,
        *,
        book_slug: str | None = None,
        chapter_range: tuple[int, int] | None = None,
        scene_ids: list[int] | None = None,
        prompt_ids: list[int] | None = None,
        limit: int | None = None,
        overwrite: bool = False,
        quality: str = "standard",
        preferred_style: str | None = None,
        aspect_ratio: str | None = None,
        provider: str = "openai",
        model: str = "dall-e-3",
        response_format: str = "b64_json",
        concurrency: int = 3,
        dry_run: bool = False,
    ) -> list[int]:
        """Returns list of generated image IDs (or planned count in dry-run)."""
```

Notes:
- Use the existing `backend/app/services/image_generation/dalle_image_api.py` for provider calls.
- Ensure directories exist before writes; generate file names deterministically.
- Record `bytesApprox`, `width`, `height` when available; compute `checksumSha256` after write.

Acceptance:
- Service can produce images for a known prompt selection and persist records
- Dry-run prints planned actions with resolved sizes/styles

---

## Phase 3 — CLI entrypoint (`main.py`)

- New file: `backend/app/services/image_generation/main.py`
- Use `typer` or `argparse` to expose the service in local development.
- Commands/flags (representative):
  - `--book <slug>`
  - `--chapter-range <start>:<end>`
  - `--scene-ids 10,11,12`
  - `--prompt-ids 200,201`
  - `--limit 50`
  - `--overwrite`
  - `--quality [standard|hd]`
  - `--style [vivid|natural]`
  - `--aspect-ratio [1:1|9:16|16:9]`
  - `--provider openai`
  - `--model dall-e-3`
  - `--response-format [b64_json|url]`
  - `--concurrency 3`
  - `--dry-run`

Examples:

```bash
uv run python backend/app/services/image_generation/main.py --book excession --limit 10 --dry-run
uv run python backend/app/services/image_generation/main.py --scene-ids 123,124 --quality hd --style vivid --aspect-ratio 16:9
```

Acceptance:
- CLI resolves filters and parameters correctly and runs service

---

## Phase 4 — Back-end routes to support the UI

- New router: `backend/app/api/routes/generated_images.py`
- Endpoints:
  - `GET /api/generated-images` — list with filters
    - Query params: `book`, `chapter`, `sceneId`, `promptId`, `page`, `size`, `sort`
    - Returns `GeneratedImageRead[]`
  - `GET /api/generated-images/{id}` — detail with context
    - Returns `GeneratedImageWithContext` including:
      - `image`: `GeneratedImageRead`
      - `prompt`: `promptText`, `attributes`, etc.
      - `scene`: `rawText`, `chapterNumber`, `sceneNumber`
  - `GET /api/scenes/{sceneId}/generated-images` — list for scene (paginated)
  - `GET /api/prompts/{promptId}/generated-images` — list for prompt (paginated)
  - `POST /api/generated-images/generate` — trigger generation for a selection (dev-only sync or background task)
- Add schemas in `backend/app/schemas/generated_image.py` for the above shapes.
- Wire router in `backend/app/api/main.py`.

Acceptance:
- Lists are paginated and filterable
- Detail endpoint returns image + prompt text + raw scene text in one call

---

## Phase 5 — Front-end UI (gallery + modal carousel)

Requirements:
- Scrollable gallery grid of generated images
- Clicking an image opens a modal. Inside the modal:
  - Show the image
  - Show both the prompt text and the raw scene text
  - Left/right arrows navigate a carousel of other images generated from the same scene
  - Keyboard navigation with ←/→

Data shape (ideal response from detail or list-with-expand):

```json
{
  "id": 1001,
  "bookSlug": "excession",
  "chapterNumber": 12,
  "sceneExtractionId": 321,
  "imagePromptId": 654,
  "storagePath": "img/generated/excession/chapter-12/",
  "fileName": "scene-17-v0.png",
  "width": 1024,
  "height": 1024,
  "createdAt": "2025-10-09T10:00:00Z",
  "prompt": { "text": "...resolved prompt text..." },
  "scene": { "rawText": "...raw scene text...", "sceneNumber": 17 }
}
```

Implementation outline:
- Pages/components (Chakra UI):
  - `GeneratedImagesGalleryPage.tsx` (route: `/images/:bookSlug?chapter?scene?`)
    - Grid: `SimpleGrid` with responsive columns
    - Infinite scroll via `IntersectionObserver` or react-query `fetchNextPage`
  - `GeneratedImageCard.tsx` — thumbnail + hover metadata (chapter, variant)
  - `GeneratedImageModal.tsx` — modal with carousel
    - Shows image, prompt text, raw scene text
    - Left/right arrows to navigate within images for the same `sceneExtractionId`
    - Pre-fetch neighbor images; support keyboard arrows
    - Close on overlay click or Escape; trap focus
- API client additions:
  - `listGeneratedImages({ book, chapter, sceneId, page, size })`
  - `getGeneratedImage(id)` returns `GeneratedImageWithContext`
  - `listGeneratedImagesForScene(sceneId)` used to seed modal carousel

Minimal modal/carousel sketch:

```tsx
function GeneratedImageModal({ isOpen, onClose, sceneImages, index, setIndex }) {
  const current = sceneImages[index];
  const goPrev = () => setIndex((i) => (i - 1 + sceneImages.length) % sceneImages.length);
  const goNext = () => setIndex((i) => (i + 1) % sceneImages.length);
  return (
    <Modal isOpen={isOpen} onClose={onClose} size="6xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>{current.bookSlug} · Chapter {current.chapterNumber}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <HStack align="start" spacing={6}>
            <IconButton aria-label="Previous" onClick={goPrev} icon={<ChevronLeftIcon />} />
            <Image src={`/${current.storagePath}${current.fileName}`} alt="generated" maxH="70vh" objectFit="contain" />
            <IconButton aria-label="Next" onClick={goNext} icon={<ChevronRightIcon />} />
            <VStack align="start" spacing={4} maxW="lg">
              <Box>
                <Text fontWeight="bold">Prompt</Text>
                <Text whiteSpace="pre-wrap">{current.prompt?.text}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold">Scene</Text>
                <Text whiteSpace="pre-wrap">{current.scene?.rawText}</Text>
              </Box>
            </VStack>
          </HStack>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}
```

Acceptance:
- Gallery scrolls and loads additional pages
- Clicking opens modal; arrows cycle through images for the same scene
- Prompt and raw scene text are visible in the modal

---

## Milestones & acceptance criteria

- M1: Schema + repository
  - Migration applied; CRUD works; uniqueness enforced
- M2: Service end-to-end (dry-run + render one)
  - Generate a single image from a known prompt; record persisted
- M3: CLI usability
  - Can target by book/scene; dry-run lists planned renders
- M4: API routes
  - Paginated list + detail with prompt and scene context
- M5: Front-end
  - Gallery + modal carousel operational with keyboard support


