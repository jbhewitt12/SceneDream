"""API routes for viewing generated images."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.repositories import (
    GeneratedImageRepository,
    ImagePromptRepository,
    SceneExtractionRepository,
)
from app.schemas import (
    GeneratedImageApprovalUpdate,
    GeneratedImageGenerateRequest,
    GeneratedImageGenerateResponse,
    GeneratedImageListResponse,
    GeneratedImageRead,
    GeneratedImageWithContext,
    GeneratedImageRemixRequest,
    GeneratedImageRemixResponse,
    ImagePromptSummary,
    SceneSummary,
)
from app.services.image_generation.image_generation_service import (
    ImageGenerationService,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
    REMIX_VARIANTS_COUNT,
)
from models.image_prompt import ImagePrompt

router = APIRouter(prefix="/generated-images", tags=["generated-images"])

_DEFAULT_LIST_LIMIT = 24
_MAX_LIST_LIMIT = 200
_DEFAULT_SCENE_LIMIT = 20
_MAX_SCENE_LIMIT = 100

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_GENERATED_IMAGES_ROOT = (_PROJECT_ROOT / "img").resolve()
logger = logging.getLogger(__name__)


def _build_context(
    record: Any, *, include_prompt: bool, include_scene: bool
) -> GeneratedImageWithContext:
    """Build a GeneratedImageWithContext from a record with optional relationships."""
    image = GeneratedImageRead.model_validate(record)

    prompt_data = None
    if include_prompt and getattr(record, "image_prompt", None) is not None:
        prompt_data = ImagePromptSummary.model_validate(record.image_prompt)

    scene_data = None
    if include_scene and getattr(record, "scene_extraction", None) is not None:
        scene_data = SceneSummary.model_validate(record.scene_extraction)

    return GeneratedImageWithContext(
        image=image,
        prompt=prompt_data,
        scene=scene_data,
    )


def _resolve_image_file(storage_path: str, file_name: str) -> Path:
    """Resolve the on-disk path for a generated image and guard against traversal."""

    relative_dir = Path(storage_path.strip("/"))
    candidate = (_PROJECT_ROOT / relative_dir / file_name).resolve()

    try:
        candidate.relative_to(_GENERATED_IMAGES_ROOT)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail="Image file not available") from exc

    return candidate


async def _execute_remix_generation(
    *,
    source_image_id: UUID,
    source_prompt_id: UUID,
    variants_count: int,
    dry_run: bool,
) -> None:
    """Background task to generate remix prompts and downstream images."""
    from sqlmodel import Session

    from app.core.db import engine

    try:
        with Session(engine) as background_session:
            prompt_service = ImagePromptGenerationService(background_session)
            prompts = prompt_service.generate_remix_variants(
                source_prompt_id,
                variants_count=variants_count,
                dry_run=dry_run,
            )
            if dry_run:
                logger.info(
                    "Remix dry-run for image %s produced %d prompt previews",
                    source_image_id,
                    len(prompts),
                )
                return

            persisted_prompts = cast(list[ImagePrompt], prompts)
            prompt_ids = [prompt.id for prompt in persisted_prompts]
            if not prompt_ids:
                logger.info(
                    "No remix prompts created for image %s; skipping image generation",
                    source_image_id,
                )
                return

            image_service = ImageGenerationService(background_session)
            await image_service.generate_for_selection(
                prompt_ids=prompt_ids,
            )
            background_session.commit()
            logger.info(
                "Remix generation complete for image %s using prompt IDs %s",
                source_image_id,
                ", ".join(str(pid) for pid in prompt_ids),
            )
    except ImagePromptGenerationServiceError:
        logger.exception(
            "Remix prompt generation failed for image %s (prompt %s)",
            source_image_id,
            source_prompt_id,
        )
    except Exception:
        logger.exception(
            "Unexpected error while processing remix for image %s (prompt %s)",
            source_image_id,
            source_prompt_id,
        )


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
    approval: bool | None = Query(None),
    newest_first: bool = Query(True),
    limit: int = Query(_DEFAULT_LIST_LIMIT, ge=1, le=_MAX_LIST_LIMIT),
    offset: int | None = Query(None, ge=0),
) -> GeneratedImageListResponse:
    """List generated images with optional filters and pagination."""

    repository = GeneratedImageRepository(session)

    # Route to appropriate list method based on filters
    if scene_id is not None:
        # List by scene
        images = repository.list_for_scene(
            scene_id,
            provider=provider,
            model=model,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
        )
    elif prompt_id is not None:
        # List by prompt
        images = repository.list_for_prompt(
            prompt_id,
            provider=provider,
            model=model,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
        )
    elif book is not None:
        # List by book (and optionally chapter)
        images = repository.list_for_book(
            book,
            chapter_number=chapter,
            provider=provider,
            model=model,
            approval=approval,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
        )
    else:
        # List across all books when no specific filter is provided
        images = repository.list_all(
            chapter_number=chapter,
            provider=provider,
            model=model,
            approval=approval,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
        )

    data = [GeneratedImageRead.model_validate(record) for record in images]
    meta: dict[str, object] = {
        "count": len(data),
        "newest_first": newest_first,
        "limit": limit,
    }
    if offset is not None:
        meta["offset"] = offset
    if book is not None:
        meta["book"] = book
    if chapter is not None:
        meta["chapter"] = chapter
    if scene_id is not None:
        meta["scene_id"] = str(scene_id)
    if prompt_id is not None:
        meta["prompt_id"] = str(prompt_id)
    if provider:
        meta["provider"] = provider
    if model:
        meta["model"] = model
    if approval is not None:
        meta["approval"] = approval

    return GeneratedImageListResponse(data=data, meta=meta)


@router.get("/{image_id}", response_model=GeneratedImageWithContext)
def get_generated_image(
    *,
    session: SessionDep,
    image_id: UUID,
    include_prompt: bool = Query(True),
    include_scene: bool = Query(True),
) -> GeneratedImageWithContext:
    """
    Fetch a single generated image by identifier with full context.
    Returns image metadata along with prompt text and raw scene text.
    """

    repository = GeneratedImageRepository(session)
    record = repository.get(image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    # Load relationships if needed
    if include_prompt and record.image_prompt is None:
        prompt_repo = ImagePromptRepository(session)
        record.image_prompt = prompt_repo.get(record.image_prompt_id)

    if include_scene and record.scene_extraction is None:
        scene_repo = SceneExtractionRepository(session)
        record.scene_extraction = scene_repo.get(record.scene_extraction_id)

    return _build_context(
        record, include_prompt=include_prompt, include_scene=include_scene
    )


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


@router.get("/{image_id}/content")
def stream_generated_image_file(
    *,
    session: SessionDep,
    image_id: UUID,
) -> FileResponse:
    """Stream the binary image file for a generated image."""

    repository = GeneratedImageRepository(session)
    record = repository.get(image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    file_path = _resolve_image_file(record.storage_path, record.file_name)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Generated image file not found")

    media_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=file_path.name,
    )


@router.get("/scene/{scene_id}", response_model=GeneratedImageListResponse)
def list_generated_images_for_scene(
    *,
    session: SessionDep,
    scene_id: UUID,
    provider: str | None = Query(None, min_length=1),
    model: str | None = Query(None, min_length=1),
    newest_first: bool = Query(True),
    limit: int = Query(_DEFAULT_SCENE_LIMIT, ge=1, le=_MAX_SCENE_LIMIT),
    offset: int | None = Query(None, ge=0),
    include_prompt: bool = Query(False),
    include_scene: bool = Query(False),
) -> GeneratedImageListResponse:
    """Return generated images for a specific scene extraction."""

    scene_repository = SceneExtractionRepository(session)
    scene = scene_repository.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")

    repository = GeneratedImageRepository(session)
    images = repository.list_for_scene(
        scene_id,
        provider=provider,
        model=model,
        newest_first=newest_first,
        limit=limit,
        offset=offset,
        include_prompt=include_prompt,
        include_scene=include_scene,
    )

    data = [GeneratedImageRead.model_validate(record) for record in images]
    meta: dict[str, object] = {
        "scene_extraction_id": str(scene_id),
        "count": len(data),
        "newest_first": newest_first,
        "limit": limit,
    }
    if offset is not None:
        meta["offset"] = offset
    if provider:
        meta["provider"] = provider
    if model:
        meta["model"] = model

    return GeneratedImageListResponse(data=data, meta=meta)


@router.get("/prompt/{prompt_id}", response_model=GeneratedImageListResponse)
def list_generated_images_for_prompt(
    *,
    session: SessionDep,
    prompt_id: UUID,
    provider: str | None = Query(None, min_length=1),
    model: str | None = Query(None, min_length=1),
    newest_first: bool = Query(True),
    limit: int = Query(_DEFAULT_SCENE_LIMIT, ge=1, le=_MAX_SCENE_LIMIT),
    offset: int | None = Query(None, ge=0),
) -> GeneratedImageListResponse:
    """Return generated images for a specific image prompt."""

    prompt_repository = ImagePromptRepository(session)
    prompt = prompt_repository.get(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Image prompt not found")

    repository = GeneratedImageRepository(session)
    images = repository.list_for_prompt(
        prompt_id,
        provider=provider,
        model=model,
        newest_first=newest_first,
        limit=limit,
        offset=offset,
    )

    data = [GeneratedImageRead.model_validate(record) for record in images]
    meta: dict[str, object] = {
        "image_prompt_id": str(prompt_id),
        "count": len(data),
        "newest_first": newest_first,
        "limit": limit,
    }
    if offset is not None:
        meta["offset"] = offset
    if provider:
        meta["provider"] = provider
    if model:
        meta["model"] = model

    return GeneratedImageListResponse(data=data, meta=meta)


@router.post(
    "/{image_id}/remix",
    response_model=GeneratedImageRemixResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def remix_generated_image(
    *,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    image_id: UUID,
    request: GeneratedImageRemixRequest | None = None,
) -> GeneratedImageRemixResponse:
    """Trigger subtle remix prompt generation for a specific generated image."""

    request = (
        request
        if request is not None
        else GeneratedImageRemixRequest(variants_count=None, dry_run=False)
    )
    image_repository = GeneratedImageRepository(session)
    image = image_repository.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    prompt_repository = ImagePromptRepository(session)
    prompt = prompt_repository.get(image.image_prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=404, detail="Source image prompt for remix not found"
        )

    variants_count = request.variants_count or REMIX_VARIANTS_COUNT
    dry_run = bool(request.dry_run)

    try:
        _ = ImagePromptGenerationService(session)
        _ = ImageGenerationService(session)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Unable to initialize remix services: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to initialize remix services",
        ) from exc

    background_tasks.add_task(
        _execute_remix_generation,
        source_image_id=image_id,
        source_prompt_id=prompt.id,
        variants_count=variants_count,
        dry_run=dry_run,
    )

    estimated_seconds = max(variants_count * 60, 120)
    return GeneratedImageRemixResponse(
        remix_prompt_ids=[],
        status="accepted",
        estimated_completion_seconds=estimated_seconds,
    )


@router.post("/generate", response_model=GeneratedImageGenerateResponse)
async def trigger_image_generation(
    *,
    session: SessionDep,
    request: GeneratedImageGenerateRequest,
) -> GeneratedImageGenerateResponse:
    """
    Trigger image generation for a selection of prompts.

    This endpoint allows you to generate images based on various filters:
    - By book_slug (optionally with chapter_range)
    - By specific scene_ids
    - By specific prompt_ids

    In dry-run mode, it will return a count of 0 and no IDs.
    Otherwise, it returns the list of generated image IDs.
    """

    # Validate that at least one filter is provided
    if not any([request.book_slug, request.scene_ids, request.prompt_ids]):
        raise HTTPException(
            status_code=400,
            detail="At least one filter (book_slug, scene_ids, or prompt_ids) is required",
        )

    # Create service instance
    service = ImageGenerationService(session)

    # Execute generation
    generated_ids = await service.generate_for_selection(
        book_slug=request.book_slug,
        chapter_range=request.chapter_range,
        scene_ids=request.scene_ids,
        prompt_ids=request.prompt_ids,
        limit=request.limit,
        quality=request.quality,
        preferred_style=request.preferred_style,
        aspect_ratio=request.aspect_ratio,
        provider=request.provider,
        model=request.model,
        response_format=request.response_format,
        concurrency=request.concurrency,
        dry_run=request.dry_run,
    )

    return GeneratedImageGenerateResponse(
        generated_image_ids=generated_ids,
        count=len(generated_ids),
        dry_run=request.dry_run,
    )
