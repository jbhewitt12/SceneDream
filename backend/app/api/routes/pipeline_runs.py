"""API routes for launching and polling pipeline runs."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep
from app.core.db import engine
from app.repositories import (
    ArtStyleRepository,
    DocumentRepository,
    PipelineRunRepository,
    SceneExtractionRepository,
)
from app.schemas import PipelineRunRead, PipelineRunStartRequest
from app.services.books.book_content_service import BookContentService
from app.services.image_gen_cli import (
    _resolve_default_scenes_per_run,
    _run_full_pipeline,
)

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])

logger = logging.getLogger(__name__)


def _spawn_background_task(
    coro: Coroutine[Any, Any, None],
    *,
    task_name: str,
) -> asyncio.Task[Any]:
    """Schedule a coroutine and log unhandled exceptions."""

    task = asyncio.create_task(coro, name=task_name)

    def _handle_task_result(completed: asyncio.Task[Any]) -> None:
        try:
            completed.result()
        except Exception:
            logger.exception("Unhandled exception in background task %s", task_name)

    task.add_done_callback(_handle_task_result)
    return task


def _build_run_namespace(
    *,
    launch_request: PipelineRunStartRequest,
    book_slug: str,
    book_path: str | None,
    images_for_scenes: int,
    skip_extraction: bool,
    prompt_art_style: str | None,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="run",
        book_slug=book_slug,
        book_path=book_path,
        prompts_per_scene=launch_request.prompts_per_scene,
        ignore_ranking_recommendations=launch_request.ignore_ranking_recommendations,
        prompts_for_scenes=launch_request.prompts_for_scenes,
        images_for_scenes=images_for_scenes,
        skip_extraction=skip_extraction,
        skip_ranking=launch_request.skip_ranking,
        skip_prompts=launch_request.skip_prompts,
        prompt_art_style=prompt_art_style,
        quality=launch_request.quality,
        style=launch_request.style,
        aspect_ratio=launch_request.aspect_ratio,
        mode=launch_request.mode,
        poll_timeout=launch_request.poll_timeout,
        poll_interval=launch_request.poll_interval,
        dry_run=launch_request.dry_run,
        verbose=False,
    )


def _update_status(
    *,
    run_id: UUID,
    status_value: str,
    current_stage: str | None,
    error_message: str | None = None,
    completed: bool = False,
) -> None:
    with Session(engine) as background_session:
        repository = PipelineRunRepository(background_session)
        run = repository.update_status(
            run_id,
            status=status_value,
            current_stage=current_stage,
            error_message=error_message,
            completed=completed,
            commit=True,
            refresh=False,
        )
        if run is None:
            logger.warning(
                "Pipeline run %s no longer exists while updating status", run_id
            )


def _format_failure_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:2000]


def _source_path_exists(
    *,
    source_path: str | None,
    book_service: BookContentService,
) -> bool:
    if not source_path:
        return False
    try:
        resolved = book_service.resolve_book_path(source_path)
    except Exception:
        return False
    return resolved.exists()


async def _execute_pipeline_run(
    *,
    run_id: UUID,
    args: argparse.Namespace,
) -> None:
    """Execute the end-to-end pipeline in a background task."""

    logger.info(
        "Pipeline run task started: run_id=%s, book_slug=%s",
        run_id,
        getattr(args, "book_slug", None),
    )

    async def _stage_callback(stage: str) -> None:
        _update_status(
            run_id=run_id,
            status_value=stage,
            current_stage=stage,
            error_message=None,
        )

    try:
        stats = await _run_full_pipeline(args, stage_callback=_stage_callback)
    except Exception as exc:
        logger.exception("Pipeline run failed with exception: run_id=%s", run_id)
        _update_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=_format_failure_message(exc),
            completed=True,
        )
        return

    if stats.errors:
        combined_error = " | ".join(stats.errors)
        _update_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=combined_error[:2000],
            completed=True,
        )
        logger.error(
            "Pipeline run completed with errors: run_id=%s, error_count=%d",
            run_id,
            len(stats.errors),
        )
        return

    _update_status(
        run_id=run_id,
        status_value="completed",
        current_stage="completed",
        error_message=None,
        completed=True,
    )
    logger.info("Pipeline run task completed: run_id=%s", run_id)


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

    art_style_repo = ArtStyleRepository(session)
    document_repo = DocumentRepository(session)
    run_repo = PipelineRunRepository(session)
    scene_repo = SceneExtractionRepository(session)
    book_service = BookContentService()

    resolved_document = None
    resolved_book_slug = launch_request.book_slug
    resolved_book_path = launch_request.book_path
    resolved_prompt_art_style: str | None = None

    if launch_request.document_id is not None:
        resolved_document = document_repo.get(launch_request.document_id)
        if resolved_document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if not resolved_book_slug:
            resolved_book_slug = resolved_document.slug
        if not resolved_book_path and resolved_document.source_path:
            resolved_book_path = resolved_document.source_path

    if resolved_document is None and resolved_book_slug:
        resolved_document = document_repo.get_by_slug(resolved_book_slug)

    if launch_request.art_style_id is not None:
        art_style = art_style_repo.get(launch_request.art_style_id)
        if art_style is None:
            raise HTTPException(status_code=404, detail="Art style not found")
        if not art_style.is_active:
            raise HTTPException(status_code=400, detail="Art style is inactive")
        resolved_prompt_art_style = art_style.display_name

    if not resolved_book_slug:
        raise HTTPException(
            status_code=400,
            detail="book_slug is required when document_id is not provided",
        )

    should_skip_extraction = launch_request.skip_extraction
    has_existing_extractions = bool(scene_repo.list_for_book(resolved_book_slug))
    source_path_exists = _source_path_exists(
        source_path=resolved_book_path,
        book_service=book_service,
    )

    if not should_skip_extraction:
        if source_path_exists:
            pass
        elif has_existing_extractions:
            should_skip_extraction = True
        elif resolved_book_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "book_path does not exist and no extracted scenes are available to resume"
                ),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="book_path is required when extraction is enabled",
            )

    if not source_path_exists:
        resolved_book_path = None

    images_for_scenes = launch_request.images_for_scenes
    if images_for_scenes is None:
        images_for_scenes = _resolve_default_scenes_per_run()

    args = _build_run_namespace(
        launch_request=launch_request,
        book_slug=resolved_book_slug,
        book_path=resolved_book_path,
        images_for_scenes=images_for_scenes,
        skip_extraction=should_skip_extraction,
        prompt_art_style=resolved_prompt_art_style,
    )

    config_overrides = launch_request.model_dump(exclude_none=True, mode="json")
    config_overrides["resolved_book_slug"] = resolved_book_slug
    if resolved_book_path is not None:
        config_overrides["resolved_book_path"] = resolved_book_path
    config_overrides["skip_extraction"] = should_skip_extraction
    config_overrides["resolved_images_for_scenes"] = images_for_scenes
    if resolved_prompt_art_style is not None:
        config_overrides["resolved_prompt_art_style"] = resolved_prompt_art_style

    run = run_repo.create(
        data={
            "document_id": resolved_document.id if resolved_document else None,
            "book_slug": resolved_book_slug,
            "status": "pending",
            "current_stage": "pending",
            "config_overrides": config_overrides,
        },
        commit=True,
        refresh=True,
    )

    coro = _execute_pipeline_run(run_id=run.id, args=args)
    try:
        _spawn_background_task(
            coro,
            task_name=f"pipeline-run-{run.id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception("Failed to create pipeline run task: run_id=%s", run.id)
        raise HTTPException(
            status_code=500,
            detail="Failed to start pipeline run",
        ) from exc

    return PipelineRunRead.model_validate(run)


@router.get("/{run_id}", response_model=PipelineRunRead)
async def get_pipeline_run(*, session: SessionDep, run_id: UUID) -> PipelineRunRead:
    """Return the current state of a pipeline run."""

    repository = PipelineRunRepository(session)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PipelineRunRead.model_validate(run)
