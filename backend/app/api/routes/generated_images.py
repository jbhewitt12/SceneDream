"""API routes for viewing generated images."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import OperationalError

from app.api.deps import SessionDep
from app.repositories import (
    GeneratedImageRepository,
    ImagePromptRepository,
    SceneExtractionRepository,
)
from app.schemas import (
    GeneratedImageApprovalUpdate,
    GeneratedImageCustomRemixRequest,
    GeneratedImageCustomRemixResponse,
    GeneratedImageGenerateRequest,
    GeneratedImageGenerateResponse,
    GeneratedImageListItem,
    GeneratedImageListResponse,
    GeneratedImageRead,
    GeneratedImageRemixRequest,
    GeneratedImageRemixResponse,
    GeneratedImageWithContext,
    ImagePromptSummary,
    PostingStatusResponse,
    QueueForPostingResponse,
    SceneSummary,
    SocialMediaPostRead,
)
from app.services.image_generation.image_generation_service import (
    ImageGenerationService,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    REMIX_VARIANTS_COUNT,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
)
from app.services.social_posting import SocialPostingService
from app.services.social_posting.scheduler import get_scheduler
from models.image_prompt import ImagePrompt

router = APIRouter(prefix="/generated-images", tags=["generated-images"])

_DEFAULT_LIST_LIMIT = 24
_MAX_LIST_LIMIT = 200
_DEFAULT_SCENE_LIMIT = 20
_MAX_SCENE_LIMIT = 100

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
# In Docker the backend code lives one level higher (/app/app/...) so parents[4]
# resolves to "/" instead of the real project root.  Fall back to parents[3] when
# the img/ directory cannot be found at the first candidate.
if not (_PROJECT_ROOT / "img").is_dir():
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GENERATED_IMAGES_ROOT = (_PROJECT_ROOT / "img").resolve()
logger = logging.getLogger(__name__)


def _spawn_background_task(
    coro: Coroutine[Any, Any, None],
    *,
    task_name: str,
) -> asyncio.Task[Any]:
    """
    Schedule a coroutine to run in the background and surface unhandled exceptions.
    """

    task = asyncio.create_task(coro, name=task_name)

    def _handle_task_result(completed: asyncio.Task[Any]) -> None:
        try:
            completed.result()
        except Exception:
            logger.exception("Unhandled exception in background task %s", task_name)

    task.add_done_callback(_handle_task_result)
    return task


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


def _build_list_item(record: Any) -> GeneratedImageListItem:
    """Convert a generated image record into a list item with prompt metadata."""

    base_image = GeneratedImageRead.model_validate(record)
    payload = base_image.model_dump()

    prompt = getattr(record, "image_prompt", None)
    payload["prompt_title"] = getattr(prompt, "title", None)
    payload["prompt_flavour_text"] = getattr(prompt, "flavour_text", None)

    # Add posting status from social_media_posts relationship
    social_posts = getattr(record, "social_media_posts", None) or []
    payload["has_been_posted"] = any(p.status == "posted" for p in social_posts)
    payload["is_queued"] = any(p.status == "queued" for p in social_posts)

    return GeneratedImageListItem.model_validate(payload)


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

    logger.info(
        "Remix generation task started: image_id=%s, prompt_id=%s, variants=%d, dry_run=%s",
        source_image_id,
        source_prompt_id,
        variants_count,
        dry_run,
    )
    started_at = time.perf_counter()
    prompt_ids: list[UUID] = []

    try:
        with Session(engine) as background_session:
            prompt_service = ImagePromptGenerationService(background_session)
            prompts = await prompt_service.generate_remix_variants(
                source_prompt_id,
                variants_count=variants_count,
                dry_run=dry_run,
            )
            if dry_run:
                logger.info(
                    "Remix dry-run complete in %.2fs: image_id=%s, prompt_id=%s, preview_count=%d",
                    time.perf_counter() - started_at,
                    source_image_id,
                    source_prompt_id,
                    len(prompts),
                )
                return

            persisted_prompts = cast(list[ImagePrompt], prompts)
            prompt_ids = [prompt.id for prompt in persisted_prompts]
            if not prompt_ids:
                elapsed = time.perf_counter() - started_at
                logger.info(
                    "Remix task created no prompts for image %s (prompt %s); skipping image generation (elapsed=%.2fs)",
                    source_image_id,
                    source_prompt_id,
                    elapsed,
                )
                return

            image_service = ImageGenerationService(background_session)
            await image_service.generate_for_selection(
                prompt_ids=prompt_ids,
            )
            background_session.commit()
    except ImagePromptGenerationServiceError:
        logger.exception(
            "Remix prompt generation failed for image %s (prompt %s)",
            source_image_id,
            source_prompt_id,
        )
    except OperationalError as exc:
        logger.exception(
            "Database error during remix task for image %s (prompt %s): %s",
            source_image_id,
            source_prompt_id,
            exc,
        )
    except Exception:
        logger.exception(
            "Unexpected error while processing remix for image %s (prompt %s)",
            source_image_id,
            source_prompt_id,
        )
    else:
        elapsed = time.perf_counter() - started_at
        logger.info(
            "Remix generation task completed in %.2fs: image_id=%s, prompt_id=%s, generated_prompts=%d, prompt_ids=%s",
            elapsed,
            source_image_id,
            source_prompt_id,
            len(prompt_ids),
            ", ".join(str(pid) for pid in prompt_ids),
        )


async def _execute_custom_remix_generation(
    *,
    source_image_id: UUID,
    source_prompt_id: UUID,
    custom_prompt_id: UUID,
    custom_prompt_text: str,
) -> None:
    """Background task to generate an image for a custom remix prompt."""
    from sqlmodel import Session

    from app.core.db import engine

    logger.info(
        "Custom remix task started: image_id=%s, prompt_id=%s, custom_prompt_id=%s, text_length=%d",
        source_image_id,
        source_prompt_id,
        custom_prompt_id,
        len(custom_prompt_text),
    )
    started_at = time.perf_counter()

    try:
        with Session(engine) as background_session:
            prompt = background_session.get(ImagePrompt, custom_prompt_id)
            if prompt is None:
                elapsed = time.perf_counter() - started_at
                logger.warning(
                    "Custom remix prompt %s not found for image %s (source prompt %s); elapsed=%.2fs",
                    custom_prompt_id,
                    source_image_id,
                    source_prompt_id,
                    elapsed,
                )
                return

            image_service = ImageGenerationService(background_session)
            await image_service.generate_for_selection(
                prompt_ids=[custom_prompt_id],
            )
            background_session.commit()
    except OperationalError as exc:
        logger.exception(
            "Database error during custom remix task for image %s (prompt %s, custom prompt %s): %s",
            source_image_id,
            source_prompt_id,
            custom_prompt_id,
            exc,
        )
    except Exception:
        logger.exception(
            "Unexpected error while processing custom remix for image %s (source prompt %s, custom prompt %s)",
            source_image_id,
            source_prompt_id,
            custom_prompt_id,
        )
    else:
        elapsed = time.perf_counter() - started_at
        logger.info(
            "Custom remix task completed in %.2fs: image_id=%s, prompt_id=%s, custom_prompt_id=%s",
            elapsed,
            source_image_id,
            source_prompt_id,
            custom_prompt_id,
        )


@router.get("/providers", response_model=list[str])
def list_providers(
    *,
    session: SessionDep,
) -> list[str]:
    """Return list of distinct providers used in generated images."""
    repository = GeneratedImageRepository(session)
    return repository.get_distinct_providers()


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
    posted: bool | None = Query(None),
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
            include_prompt=True,
            include_posting_status=True,
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
            include_prompt=True,
            include_posting_status=True,
        )
    elif book is not None:
        # List by book (and optionally chapter)
        images = repository.list_for_book(
            book,
            chapter_number=chapter,
            provider=provider,
            model=model,
            approval=approval,
            posted=posted,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
            include_prompt=True,
            include_posting_status=True,
        )
    else:
        # List across all books when no specific filter is provided
        images = repository.list_all(
            chapter_number=chapter,
            provider=provider,
            model=model,
            approval=approval,
            posted=posted,
            newest_first=newest_first,
            limit=limit,
            offset=offset,
            include_prompt=True,
            include_posting_status=True,
        )

    data = [_build_list_item(record) for record in images]
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
    if posted is not None:
        meta["posted"] = posted

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

    if record.file_deleted:
        raise HTTPException(status_code=410, detail="Image file has been deleted")

    file_path = _resolve_image_file(record.storage_path, record.file_name)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Generated image file not found")

    media_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=file_path.name,
        headers={"Access-Control-Allow-Origin": "*"},
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
        include_posting_status=True,
    )

    data = [_build_list_item(record) for record in images]
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
        include_prompt=True,
        include_posting_status=True,
    )

    data = [_build_list_item(record) for record in images]
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

    try:
        _spawn_background_task(
            _execute_remix_generation(
                source_image_id=image_id,
                source_prompt_id=prompt.id,
                variants_count=variants_count,
                dry_run=dry_run,
            ),
            task_name=f"remix-generated-image-{image_id}",
        )
    except Exception as exc:
        logger.exception(
            "Failed to create remix generation task for image %s", image_id
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start remix generation",
        ) from exc

    estimated_seconds = max(variants_count * 60, 120)
    return GeneratedImageRemixResponse(
        remix_prompt_ids=[],
        status="accepted",
        estimated_completion_seconds=estimated_seconds,
    )


@router.post(
    "/{image_id}/custom-remix",
    response_model=GeneratedImageCustomRemixResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def custom_remix_generated_image(
    *,
    session: SessionDep,
    image_id: UUID,
    request: GeneratedImageCustomRemixRequest,
) -> GeneratedImageCustomRemixResponse:
    """Trigger a custom remix using user-supplied prompt text for a generated image."""

    image_repository = GeneratedImageRepository(session)
    image = image_repository.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    prompt_repository = ImagePromptRepository(session)
    prompt = prompt_repository.get(image.image_prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=404,
            detail="Source image prompt for custom remix not found",
        )

    custom_prompt_text = request.custom_prompt_text
    if not custom_prompt_text or not custom_prompt_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Custom prompt text must not be empty",
        )

    try:
        prompt_service = ImagePromptGenerationService(session)
        _ = ImageGenerationService(session)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Unable to initialize custom remix services: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Unable to initialize custom remix services",
        ) from exc

    try:
        custom_prompt = await prompt_service.create_custom_remix_variant(
            prompt,
            custom_prompt_text,
            dry_run=False,
        )
    except ImagePromptGenerationServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not isinstance(custom_prompt, ImagePrompt):  # pragma: no cover - safety valve
        raise HTTPException(
            status_code=500,
            detail="Custom remix prompt creation failed",
        )

    try:
        _spawn_background_task(
            _execute_custom_remix_generation(
                source_image_id=image_id,
                source_prompt_id=prompt.id,
                custom_prompt_id=custom_prompt.id,
                custom_prompt_text=custom_prompt_text,
            ),
            task_name=f"custom-remix-generated-image-{image_id}",
        )
    except Exception as exc:
        logger.exception(
            "Failed to create custom remix task for image %s (prompt %s)",
            image_id,
            prompt.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start custom remix generation",
        ) from exc

    logger.info(
        "Custom remix requested for image %s (prompt %s, custom prompt %s, text_length=%s)",
        image_id,
        prompt.id,
        custom_prompt.id,
        len(custom_prompt_text),
    )

    return GeneratedImageCustomRemixResponse(
        custom_prompt_id=custom_prompt.id,
        status="accepted",
        estimated_completion_seconds=60,
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


@router.post(
    "/{image_id}/queue-for-posting",
    response_model=QueueForPostingResponse,
    status_code=status.HTTP_200_OK,
)
async def queue_image_for_posting(
    *,
    session: SessionDep,
    image_id: UUID,
) -> QueueForPostingResponse:
    """
    Queue an approved image for posting to configured social media services.

    The image must have user_approved=True. If the cooldown period has passed
    since the last post, the image will be posted immediately. Otherwise, it
    will be added to the queue for later posting.
    """
    service = SocialPostingService(session)

    try:
        posts = service.queue_image(image_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not posts:
        return QueueForPostingResponse(
            posts=[],
            message="No services available to post to, or image already queued/posted",
        )

    # Trigger immediate queue check if cooldown has passed
    scheduler = get_scheduler()
    if scheduler.is_running:
        _spawn_background_task(
            scheduler.trigger_immediate_check(),
            task_name=f"immediate-post-check-{image_id}",
        )

    post_schemas = [SocialMediaPostRead.model_validate(p) for p in posts]
    return QueueForPostingResponse(
        posts=post_schemas,
        message=f"Queued for {len(posts)} service(s)",
    )


@router.get(
    "/{image_id}/posting-status",
    response_model=PostingStatusResponse,
)
def get_image_posting_status(
    *,
    session: SessionDep,
    image_id: UUID,
) -> PostingStatusResponse:
    """
    Get the social media posting status for an image.

    Returns all posting records for the image, along with summary flags
    indicating whether it has been posted or is currently queued.
    """
    repository = GeneratedImageRepository(session)
    image = repository.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    service = SocialPostingService(session)
    posts = service.get_posting_status(image_id)

    post_schemas = [SocialMediaPostRead.model_validate(p) for p in posts]
    has_been_posted = any(p.status == "posted" for p in posts)
    is_queued = any(p.status == "queued" for p in posts)

    return PostingStatusResponse(
        posts=post_schemas,
        has_been_posted=has_been_posted,
        is_queued=is_queued,
    )


@router.post(
    "/retry-failed-posts",
    response_model=QueueForPostingResponse,
    status_code=status.HTTP_200_OK,
)
async def retry_failed_posts(
    *,
    session: SessionDep,
    service_name: str | None = Query(
        None, description="Filter by service (e.g. 'flickr')"
    ),
) -> QueueForPostingResponse:
    """
    Requeue all failed social media posts so they will be retried.

    Optionally filter by service name. Requeued posts will be picked up by
    the scheduler on its next run.
    """
    from datetime import datetime, timedelta, timezone

    # Requeue posts that failed in the last 24 hours
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    svc = SocialPostingService(session)
    posts = svc.retry_failed(service_name=service_name, since=since)

    if not posts:
        return QueueForPostingResponse(posts=[], message="No failed posts to retry")

    # Trigger immediate queue check
    scheduler = get_scheduler()
    if scheduler.is_running:
        _spawn_background_task(
            scheduler.trigger_immediate_check(),
            task_name="retry-failed-posts-check",
        )

    post_schemas = [SocialMediaPostRead.model_validate(p) for p in posts]
    return QueueForPostingResponse(
        posts=post_schemas,
        message=f"Requeued {len(posts)} failed post(s) for retry",
    )


@router.put("/{image_id}/crop")
async def crop_image(
    *,
    session: SessionDep,
    image_id: UUID,
    file: UploadFile = File(...),
) -> dict[str, str]:
    """
    Replace a generated image with a cropped version.

    Accepts a multipart file upload containing the cropped image data
    and overwrites the original file on disk.
    """
    repository = GeneratedImageRepository(session)
    image = repository.get(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Generated image not found")

    if image.file_deleted:
        raise HTTPException(status_code=410, detail="Image file has been deleted")

    file_path = _resolve_image_file(image.storage_path, image.file_name)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail="Original image file not found on disk",
        )

    try:
        contents = await file.read()
        file_path.write_bytes(contents)
        logger.info(
            "Cropped image %s written to %s (%d bytes)",
            image_id,
            file_path,
            len(contents),
        )
    except Exception as exc:
        logger.exception("Failed to write cropped image %s: %s", image_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to save cropped image",
        ) from exc

    return {"status": "success"}
