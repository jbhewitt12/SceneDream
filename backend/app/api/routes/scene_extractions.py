"""API routes for viewing scene extraction results."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.repositories import SceneExtractionRepository
from app.schemas import (
    SceneExtractionFilterOptions,
    SceneExtractionListResponse,
    SceneExtractionRead,
    SceneGenerateRequest,
    SceneGenerateResponse,
)
from app.services.pipeline import (
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineOrchestrator,
    PipelineRunStartService,
    PipelineStagePlan,
    PipelineValidationError,
    PromptExecutionOptions,
    SceneTarget,
    spawn_background_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scene-extractions", tags=["scene-extractions"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get("/", response_model=SceneExtractionListResponse)
def list_scene_extractions(
    *,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    book_slug: str | None = Query(None),
    decision: str | None = Query(None),
    has_warnings: bool | None = Query(None),
    search: str | None = Query(None, min_length=1),
    sort_by: Literal["extracted_desc", "extracted_asc", "ranking_desc"] = Query(
        "extracted_desc"
    ),
) -> SceneExtractionListResponse:
    """Return a paginated list of scene extractions with optional filters."""

    repository = SceneExtractionRepository(session)
    records, total = repository.search(
        page=page,
        page_size=page_size,
        book_slug=book_slug,
        decision=decision,
        has_warnings=has_warnings,
        search_term=search,
        sort_by=sort_by,
    )

    data = []
    for scene, score, flagged in records:
        read = SceneExtractionRead.model_validate(scene)
        read.ranking_score = score
        read.has_content_warnings = flagged
        data.append(read)

    return SceneExtractionListResponse(
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/filters", response_model=SceneExtractionFilterOptions)
def get_filter_options(*, session: SessionDep) -> SceneExtractionFilterOptions:
    """Expose the available filter options for scene extractions."""

    repository = SceneExtractionRepository(session)
    options = repository.filter_options()
    return SceneExtractionFilterOptions.model_validate(options)


@router.get("/{scene_id}", response_model=SceneExtractionRead)
def get_scene_extraction(*, session: SessionDep, scene_id: UUID) -> SceneExtractionRead:
    """Fetch a single scene extraction by its identifier."""

    repository = SceneExtractionRepository(session)
    record = repository.get(scene_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")
    return SceneExtractionRead.model_validate(record)


@router.post(
    "/{scene_id}/generate",
    response_model=SceneGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_for_scene(
    *,
    session: SessionDep,
    scene_id: UUID,
    request: SceneGenerateRequest,
) -> SceneGenerateResponse:
    """Generate images for a specific scene.

    Creates a tracked pipeline run that generates fresh prompts and images
    for the given scene. The run executes in the background.
    """
    # Validate scene exists
    scene_repo = SceneExtractionRepository(session)
    scene = scene_repo.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")

    target = SceneTarget(scene_ids=[scene_id])

    stages = PipelineStagePlan(
        run_extraction=False,
        run_ranking=False,
        run_prompt_generation=True,
        run_image_generation=True,
    )

    prompt_options = PromptExecutionOptions(
        scene_variant_count=request.num_images,
        require_exact_scene_variants=True,
        prompt_art_style_mode=request.prompt_art_style_mode,
        prompt_art_style_text=request.prompt_art_style_text,
    )

    image_options = ImageExecutionOptions(
        quality=request.quality,
        style=request.style,
        aspect_ratio=request.aspect_ratio,
    )

    config = PipelineExecutionConfig(
        target=target,
        stages=stages,
        prompt_options=prompt_options,
        image_options=image_options,
    )

    service = PipelineRunStartService(session)
    try:
        prepared = service.prepare_execution(config)
    except PipelineValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    orchestrator = PipelineOrchestrator()
    coro = orchestrator.execute(prepared)
    try:
        spawn_background_task(
            coro,
            task_name=f"scene-generate-{prepared.run_id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception(
            "Failed to create scene generate task: run_id=%s scene_id=%s",
            prepared.run_id,
            scene_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start scene generation",
        ) from exc

    return SceneGenerateResponse(
        pipeline_run_id=prepared.run_id,
        status="pending",
        message=f"Generating {request.num_images} images for scene",
    )
