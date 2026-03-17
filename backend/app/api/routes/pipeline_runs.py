"""API routes for launching and polling pipeline runs."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.repositories import PipelineRunRepository
from app.schemas import PipelineRunRead, PipelineRunStartRequest
from app.services.pipeline import (
    DocumentTarget,
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineOrchestrator,
    PipelineRunStartService,
    PipelineStagePlan,
    PipelineValidationError,
    PromptExecutionOptions,
    spawn_background_task,
)

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])

logger = logging.getLogger(__name__)


def _build_execution_config(
    launch_request: PipelineRunStartRequest,
) -> PipelineExecutionConfig:
    """Translate a launch request into a PipelineExecutionConfig."""
    target = DocumentTarget(
        document_id=launch_request.document_id,
        book_slug=launch_request.book_slug,
        book_path=launch_request.book_path,
    )

    # skip_prompts implies skip images (PipelineStagePlan validates this)
    run_image_generation = not launch_request.skip_prompts
    stages = PipelineStagePlan(
        run_extraction=not launch_request.skip_extraction,
        run_ranking=not launch_request.skip_ranking,
        run_prompt_generation=not launch_request.skip_prompts,
        run_image_generation=run_image_generation,
    )

    prompt_options = PromptExecutionOptions(
        prompts_per_scene=launch_request.prompts_per_scene,
        ignore_ranking_recommendations=launch_request.ignore_ranking_recommendations,
        prompts_for_scenes=launch_request.prompts_for_scenes,
        images_for_scenes=launch_request.images_for_scenes,
        prompt_art_style_mode=launch_request.prompt_art_style_mode,
        prompt_art_style_text=launch_request.prompt_art_style_text,
    )

    image_options = ImageExecutionOptions(
        quality=launch_request.quality,
        style=launch_request.style,
        aspect_ratio=launch_request.aspect_ratio,
    )

    return PipelineExecutionConfig(
        target=target,
        stages=stages,
        prompt_options=prompt_options,
        image_options=image_options,
        dry_run=launch_request.dry_run,
    )


@router.post(
    "",
    response_model=PipelineRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_pipeline_run(
    *,
    session: SessionDep,
    launch_request: PipelineRunStartRequest,
) -> PipelineRunRead:
    """Create a pipeline run and execute it in the background."""
    config = _build_execution_config(launch_request)

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
            task_name=f"pipeline-run-{prepared.run_id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception(
            "Failed to create pipeline run task: run_id=%s",
            prepared.run_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start pipeline run",
        ) from exc

    # Fetch the persisted run to return
    run_repo = PipelineRunRepository(session)
    run = run_repo.get(prepared.run_id)
    if run is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Pipeline run not found after creation")
    return PipelineRunRead.model_validate(run)


@router.get("/{run_id}", response_model=PipelineRunRead)
async def get_pipeline_run(*, session: SessionDep, run_id: UUID) -> PipelineRunRead:
    """Return the current state of a pipeline run."""

    repository = PipelineRunRepository(session)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PipelineRunRead.model_validate(run)
