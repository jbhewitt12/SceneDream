"""API routes for viewing generated images."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.api.errors import api_error, api_error_from_exception, build_error_responses
from app.repositories import (
    AppSettingsRepository,
    GeneratedImageRepository,
    ImagePromptRepository,
    PipelineRunRepository,
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
    ImageFileDeletedError,
    ImageFileError,
    ImageFileNotFoundError,
    ImageFileWriteError,
    ImageGenerationService,
    ImageNotFoundError,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    REMIX_VARIANTS_COUNT,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
)
from app.services.pipeline import (
    CustomRemixTarget,
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineOrchestrator,
    PipelineRunStartService,
    PipelineStagePlan,
    PipelineValidationError,
    PromptExecutionOptions,
    RemixTarget,
    spawn_background_task,
)
from app.services.social_posting import SocialPostingService
from app.services.social_posting.exceptions import SocialPostingDisabledError
from app.services.social_posting.scheduler import get_scheduler
from models.image_prompt import ImagePrompt

router = APIRouter(prefix="/generated-images", tags=["generated-images"])

_DEFAULT_LIST_LIMIT = 24
_MAX_LIST_LIMIT = 200
_DEFAULT_SCENE_LIMIT = 20
_MAX_SCENE_LIMIT = 100

logger = logging.getLogger(__name__)

_SOCIAL_POSTING_DISABLED_DETAIL = "Social media posting is disabled in Settings"


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


def _ensure_social_posting_enabled(session: SessionDep) -> None:
    settings_repo = AppSettingsRepository(session)
    if not settings_repo.social_posting_enabled():
        raise HTTPException(status_code=409, detail=_SOCIAL_POSTING_DISABLED_DETAIL)


async def _read_upload_contents(file: UploadFile) -> bytes:
    """Read uploaded file contents from an HTTP request."""
    return await file.read()


def _fail_pending_run(session: SessionDep, run_id: UUID, error_message: str) -> None:
    """Mark a pending pipeline run as failed when request-scope setup fails."""
    run_repo = PipelineRunRepository(session)
    run_repo.update_status(
        run_id,
        status="failed",
        current_stage="failed",
        error_message=error_message[:2000],
        completed=True,
        commit=True,
        refresh=False,
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

    service = ImageGenerationService(session)
    try:
        file_path = service.get_image_file_path(image_id)
    except ImageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Generated image not found"
        ) from exc
    except ImageFileDeletedError as exc:
        raise HTTPException(
            status_code=410, detail="Image file has been deleted"
        ) from exc
    except ImageFileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Generated image file not found",
        ) from exc
    except ImageFileError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    responses=build_error_responses(400, 404, 422, 500),
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
        raise api_error(
            status_code=404,
            code="generated_image_not_found",
            message="Generated image not found",
        )

    prompt_repository = ImagePromptRepository(session)
    prompt = prompt_repository.get(image.image_prompt_id)
    if prompt is None:
        raise api_error(
            status_code=404,
            code="source_prompt_not_found",
            message="Source image prompt for remix not found",
        )

    variants_count = request.variants_count or REMIX_VARIANTS_COUNT

    target = RemixTarget(
        source_image_id=image_id,
        source_prompt_id=prompt.id,
    )
    config = PipelineExecutionConfig(
        target=target,
        stages=PipelineStagePlan(
            run_prompt_generation=True,
            run_image_generation=True,
        ),
        prompt_options=PromptExecutionOptions(
            variants_count=variants_count,
        ),
        image_options=ImageExecutionOptions(),
        dry_run=bool(request.dry_run),
    )

    service = PipelineRunStartService(session)
    try:
        prepared = service.prepare_execution(config)
    except PipelineValidationError as exc:
        raise api_error_from_exception(
            status_code=exc.status_code,
            code="invalid_remix_request",
            exc=exc,
            default_message="Remix request validation failed",
        ) from exc

    orchestrator = PipelineOrchestrator()
    coro = orchestrator.execute(prepared)
    try:
        spawn_background_task(
            coro,
            task_name=f"remix-generated-image-{image_id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception(
            "Failed to create remix generation task for image %s", image_id
        )
        raise api_error_from_exception(
            status_code=500,
            code="remix_generation_start_failed",
            exc=exc,
            default_message="Failed to start remix generation",
        ) from exc

    estimated_seconds = max(variants_count * 60, 120)
    return GeneratedImageRemixResponse(
        pipeline_run_id=prepared.run_id,
        remix_prompt_ids=[],
        status="accepted",
        estimated_completion_seconds=estimated_seconds,
    )


@router.post(
    "/{image_id}/custom-remix",
    response_model=GeneratedImageCustomRemixResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=build_error_responses(400, 404, 422, 500),
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
        raise api_error(
            status_code=404,
            code="generated_image_not_found",
            message="Generated image not found",
        )

    prompt_repository = ImagePromptRepository(session)
    prompt = prompt_repository.get(image.image_prompt_id)
    if prompt is None:
        raise api_error(
            status_code=404,
            code="source_prompt_not_found",
            message="Source image prompt for custom remix not found",
        )

    custom_prompt_text = request.custom_prompt_text
    if not custom_prompt_text or not custom_prompt_text.strip():
        raise api_error(
            status_code=400,
            code="custom_prompt_required",
            message="Custom prompt text must not be empty",
        )

    # Build config with CustomRemixTarget (custom_prompt_id set after creation)
    target = CustomRemixTarget(
        source_image_id=image_id,
        source_prompt_id=prompt.id,
        custom_prompt_text=custom_prompt_text,
    )
    config = PipelineExecutionConfig(
        target=target,
        stages=PipelineStagePlan(
            run_prompt_generation=True,
            run_image_generation=True,
        ),
        prompt_options=PromptExecutionOptions(),
        image_options=ImageExecutionOptions(),
    )

    # Create the pending pipeline run first
    service = PipelineRunStartService(session)
    try:
        prepared = service.prepare_execution(config)
    except PipelineValidationError as exc:
        raise api_error_from_exception(
            status_code=exc.status_code,
            code="invalid_custom_remix_request",
            exc=exc,
            default_message="Custom remix request validation failed",
        ) from exc

    run_id = prepared.run_id

    # Create the custom prompt in request scope, linked to the run
    try:
        prompt_service = ImagePromptGenerationService(session)
        custom_prompt = await prompt_service.create_custom_remix_variant(
            prompt,
            custom_prompt_text,
            dry_run=False,
            pipeline_run_id=run_id,
        )
    except ImagePromptGenerationServiceError as exc:
        _fail_pending_run(
            session, run_id, f"Custom remix prompt creation failed: {exc}"
        )
        raise api_error_from_exception(
            status_code=400,
            code="custom_remix_prompt_creation_failed",
            exc=exc,
            default_message="Custom remix prompt creation failed",
        ) from exc
    except Exception as exc:
        _fail_pending_run(
            session, run_id, f"Custom remix prompt creation failed: {exc}"
        )
        raise api_error_from_exception(
            status_code=500,
            code="custom_remix_prompt_creation_failed",
            exc=exc,
            default_message="Custom remix prompt creation failed",
        ) from exc

    if not isinstance(custom_prompt, ImagePrompt):  # pragma: no cover - safety valve
        _fail_pending_run(
            session, run_id, "Custom remix prompt creation returned unexpected type"
        )
        raise api_error(
            status_code=500,
            code="custom_remix_prompt_creation_failed",
            message="Custom remix prompt creation failed",
        )

    # Update the target with the created prompt ID and register in context
    custom_remix_target: CustomRemixTarget = prepared.config.target  # type: ignore[assignment]
    custom_remix_target.custom_prompt_id = custom_prompt.id

    # Spawn orchestrator execution in the background
    orchestrator = PipelineOrchestrator()
    coro = orchestrator.execute(prepared)
    try:
        spawn_background_task(
            coro,
            task_name=f"custom-remix-generated-image-{image_id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception(
            "Failed to create custom remix task for image %s (prompt %s)",
            image_id,
            prompt.id,
        )
        raise api_error_from_exception(
            status_code=500,
            code="custom_remix_generation_start_failed",
            exc=exc,
            default_message="Failed to start custom remix generation",
        ) from exc

    logger.info(
        "Custom remix requested for image %s (prompt %s, custom prompt %s, text_length=%s)",
        image_id,
        prompt.id,
        custom_prompt.id,
        len(custom_prompt_text),
    )

    return GeneratedImageCustomRemixResponse(
        pipeline_run_id=run_id,
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
    _ensure_social_posting_enabled(session)
    service = SocialPostingService(session)

    try:
        posts = service.queue_image(image_id)
    except SocialPostingDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        spawn_background_task(
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
    _ensure_social_posting_enabled(session)
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
    _ensure_social_posting_enabled(session)
    from datetime import datetime, timedelta, timezone

    # Requeue posts that failed in the last 24 hours
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    svc = SocialPostingService(session)
    try:
        posts = svc.retry_failed(service_name=service_name, since=since)
    except SocialPostingDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not posts:
        return QueueForPostingResponse(posts=[], message="No failed posts to retry")

    # Trigger immediate queue check
    scheduler = get_scheduler()
    if scheduler.is_running:
        spawn_background_task(
            scheduler.trigger_immediate_check(),
            task_name="retry-failed-posts-check",
        )

    post_schemas = [SocialMediaPostRead.model_validate(p) for p in posts]
    return QueueForPostingResponse(
        posts=post_schemas,
        message=f"Requeued {len(posts)} failed post(s) for retry",
    )


@router.put(
    "/{image_id}/crop",
    responses=build_error_responses(400, 404, 410, 500),
)
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
    service = ImageGenerationService(session)

    try:
        contents = await _read_upload_contents(file)
        await service.save_cropped_image(image_id, contents)
    except ImageNotFoundError as exc:
        raise api_error_from_exception(
            status_code=404,
            code="generated_image_not_found",
            exc=exc,
            default_message="Generated image not found",
        ) from exc
    except ImageFileDeletedError as exc:
        raise api_error_from_exception(
            status_code=410,
            code="generated_image_deleted",
            exc=exc,
            default_message="Image file has been deleted",
        ) from exc
    except ImageFileNotFoundError as exc:
        raise api_error_from_exception(
            status_code=400,
            code="generated_image_file_not_found",
            exc=exc,
            default_message="Original image file not found on disk",
        ) from exc
    except ImageFileWriteError as exc:
        raise api_error_from_exception(
            status_code=500,
            code="generated_image_crop_save_failed",
            exc=exc,
            default_message="Failed to save cropped image",
        ) from exc

    return {"status": "success"}
