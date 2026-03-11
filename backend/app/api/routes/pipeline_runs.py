"""API routes for launching and polling pipeline runs."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep
from app.core.db import engine
from app.repositories import DocumentRepository, PipelineRunRepository
from app.schemas import PipelineRunRead, PipelineRunStartRequest
from app.services.image_gen_cli import _run_full_pipeline
from app.services.image_generation.image_generation_service import ImageGenerationConfig
from app.services.image_prompt_generation.models import ImagePromptGenerationConfig
from app.services.pipeline import (
    DocumentStageStatusService,
    PipelineRunStartService,
    PipelineValidationError,
)
from models.document import Document

router = APIRouter(prefix="/pipeline-runs", tags=["pipeline-runs"])

logger = logging.getLogger(__name__)


class _RunDiagnosticsTracker:
    """Collects per-run stage timing and event diagnostics."""

    def __init__(
        self,
        *,
        run_id: UUID,
        started_at: datetime,
    ) -> None:
        self.run_id = str(run_id)
        self.started_at = started_at
        self.current_stage: str | None = None
        self.current_stage_started_at: datetime | None = None
        self.stage_durations_ms: dict[str, int] = {}
        self.stage_events: list[dict[str, Any]] = []
        self._append_event(event_type="run_started", at=started_at, stage="pending")

    def _append_event(
        self,
        *,
        event_type: str,
        at: datetime,
        stage: str | None = None,
        **details: Any,
    ) -> None:
        event: dict[str, Any] = {
            "type": event_type,
            "at": at.isoformat(),
        }
        if stage is not None:
            event["stage"] = stage
        event.update(details)
        self.stage_events.append(event)

    @staticmethod
    def _duration_ms(*, started_at: datetime, ended_at: datetime) -> int:
        return max(0, int((ended_at - started_at).total_seconds() * 1000))

    def start_stage(self, *, stage: str, at: datetime) -> tuple[str | None, int | None]:
        """Record a new active stage and close the previous stage, if any."""

        if self.current_stage == stage:
            return None, None

        completed_stage: str | None = None
        completed_duration_ms: int | None = None
        if self.current_stage and self.current_stage_started_at:
            completed_stage = self.current_stage
            completed_duration_ms = self._duration_ms(
                started_at=self.current_stage_started_at,
                ended_at=at,
            )
            existing_duration = self.stage_durations_ms.get(completed_stage, 0)
            self.stage_durations_ms[completed_stage] = (
                existing_duration + completed_duration_ms
            )
            self._append_event(
                event_type="stage_completed",
                at=at,
                stage=completed_stage,
                duration_ms=completed_duration_ms,
            )

        self.current_stage = stage
        self.current_stage_started_at = at
        self._append_event(event_type="stage_started", at=at, stage=stage)
        return completed_stage, completed_duration_ms

    def finalize(
        self,
        *,
        status_value: str,
        completed_at: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Close active stage and return persisted diagnostics payload."""

        final_stage = self.current_stage
        if self.current_stage and self.current_stage_started_at:
            final_duration_ms = self._duration_ms(
                started_at=self.current_stage_started_at,
                ended_at=completed_at,
            )
            existing_duration = self.stage_durations_ms.get(self.current_stage, 0)
            self.stage_durations_ms[self.current_stage] = (
                existing_duration + final_duration_ms
            )
            self._append_event(
                event_type="stage_completed",
                at=completed_at,
                stage=self.current_stage,
                duration_ms=final_duration_ms,
            )

        terminal_type = "run_completed" if status_value == "completed" else "run_failed"
        self._append_event(
            event_type=terminal_type,
            at=completed_at,
            stage=final_stage,
            status=status_value,
        )

        diagnostics: dict[str, Any] = {
            "observed_stage": final_stage,
            "stage_durations_ms": dict(self.stage_durations_ms),
            "stage_events": list(self.stage_events),
        }
        if status_value == "failed":
            diagnostics["error"] = {
                "code": error_code or "pipeline_exception",
                "message": (error_message or "")[:2000],
                "stage": final_stage or "pending",
            }
        return diagnostics


def _log_pipeline_event(
    *,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit structured pipeline-run logs as JSON payloads."""

    payload = {"event": event, **fields}
    logger.log(
        level,
        "pipeline_run_event %s",
        json.dumps(payload, default=str, sort_keys=True),
    )


def _classify_pipeline_error_code(
    *,
    exc: Exception | None = None,
    error_message: str | None = None,
    observed_stage: str | None = None,
) -> str:
    """Classify errors into stable, machine-readable failure codes."""

    message = (error_message or "").lower()
    if not message and exc is not None:
        message = str(exc).lower()

    has_book_path_hint = "book_path" in message or "book-path" in message
    if has_book_path_hint and ("required" in message or "does not exist" in message):
        return "missing_source"

    if isinstance(exc, ValueError):
        return "invalid_request"

    if observed_stage in {
        "extracting",
        "ranking",
        "generating_prompts",
        "generating_images",
    }:
        return "stage_error"

    if exc is not None:
        return "pipeline_exception"

    return "pipeline_exception"


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


def _update_status(
    *,
    run_id: UUID,
    status_value: str,
    current_stage: str | None,
    error_message: str | None = None,
    usage_summary: dict[str, Any] | None = None,
    completed: bool = False,
) -> None:
    with Session(engine) as background_session:
        repository = PipelineRunRepository(background_session)
        run = repository.update_status(
            run_id,
            status=status_value,
            current_stage=current_stage,
            error_message=error_message,
            usage_summary=usage_summary,
            completed=completed,
            commit=True,
            refresh=False,
        )
        if run is None:
            logger.warning(
                "Pipeline run %s no longer exists while updating status", run_id
            )


def _apply_document_stage_update_for_run(
    *,
    run_id: UUID,
    update_fn: Callable[[DocumentStageStatusService, Document], object],
) -> None:
    with Session(engine) as background_session:
        run_repository = PipelineRunRepository(background_session)
        run = run_repository.get(run_id)
        if run is None:
            return
        if run.document_id is None:
            return

        document_repository = DocumentRepository(background_session)
        document = document_repository.get(run.document_id)
        if document is None:
            return

        status_service = DocumentStageStatusService(background_session)
        update_fn(status_service, document)
        background_session.commit()


def _set_document_stage_running(*, run_id: UUID, pipeline_stage: str) -> None:
    stage = DocumentStageStatusService.to_document_stage_name(pipeline_stage)
    if stage is None:
        return
    try:
        _apply_document_stage_update_for_run(
            run_id=run_id,
            update_fn=lambda service, document: service.mark_stage_running(
                document=document,
                stage=stage,
            ),
        )
    except Exception:
        logger.exception(
            "Failed to mark document stage running: run_id=%s stage=%s",
            run_id,
            pipeline_stage,
        )


def _set_document_stage_failed(
    *,
    run_id: UUID,
    pipeline_stage: str | None,
    error_message: str | None,
) -> None:
    stage = DocumentStageStatusService.to_document_stage_name(pipeline_stage)
    if stage is None:
        return
    try:
        _apply_document_stage_update_for_run(
            run_id=run_id,
            update_fn=lambda service, document: service.mark_stage_failed(
                document=document,
                stage=stage,
                error_message=error_message,
            ),
        )
    except Exception:
        logger.exception(
            "Failed to mark document stage failed: run_id=%s stage=%s",
            run_id,
            pipeline_stage,
        )


def _sync_document_stage_statuses(
    *,
    run_id: UUID,
    preserve_failed_pipeline_stage: str | None = None,
) -> None:
    preserve_failed: set[str] = set()
    failed_stage = DocumentStageStatusService.to_document_stage_name(
        preserve_failed_pipeline_stage
    )
    if failed_stage is not None:
        preserve_failed.add(failed_stage)

    try:
        _apply_document_stage_update_for_run(
            run_id=run_id,
            update_fn=lambda service, document: service.sync_document(
                document=document,
                preserve_failed_stages=preserve_failed,
            ),
        )
    except Exception:
        logger.exception(
            "Failed to synchronize document stage status: run_id=%s",
            run_id,
        )


def _format_failure_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:2000]


def _build_usage_summary(
    *,
    args: argparse.Namespace,
    stats: Any | None,
    status_value: str,
    started_at: datetime,
    completed_at: datetime,
    config_overrides: dict[str, Any] | None,
    error_message: str | None = None,
    error_code: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt_defaults = ImagePromptGenerationConfig()
    image_defaults = ImageGenerationConfig(
        quality=getattr(args, "quality", "standard"),
        preferred_style=getattr(args, "style", None),
        aspect_ratio=getattr(args, "aspect_ratio", None),
    )

    stats_dict = stats.to_dict() if stats is not None else {}
    raw_errors = stats_dict.get("errors", [])
    error_messages = (
        [str(message)[:200] for message in raw_errors[:5]]
        if isinstance(raw_errors, list)
        else []
    )
    if error_message:
        error_messages = [error_message[:200], *error_messages]

    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))

    return {
        "status": status_value,
        "timing": {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
        },
        "requested": {
            "book_slug": getattr(args, "book_slug", None),
            "book_path": getattr(args, "book_path", None),
            "images_for_scenes": getattr(args, "images_for_scenes", None),
            "prompts_for_scenes": getattr(args, "prompts_for_scenes", None),
            "prompts_per_scene": getattr(args, "prompts_per_scene", None),
            "skip_extraction": getattr(args, "skip_extraction", None),
            "skip_ranking": getattr(args, "skip_ranking", None),
            "skip_prompts": getattr(args, "skip_prompts", None),
            "quality": getattr(args, "quality", None),
            "style": getattr(args, "style", None),
            "aspect_ratio": getattr(args, "aspect_ratio", None),
            "mode": getattr(args, "mode", None),
        },
        "effective": {
            "config_overrides": config_overrides or {},
            "prompt_generation": {
                "model_vendor": prompt_defaults.model_vendor,
                "model_name": prompt_defaults.model_name,
                "backup_model_vendor": prompt_defaults.backup_model_vendor,
                "backup_model_name": prompt_defaults.backup_model_name,
                "prompt_version": prompt_defaults.prompt_version,
                "target_provider": prompt_defaults.target_provider,
                "preferred_style": getattr(args, "prompt_art_style", None),
            },
            "image_generation": {
                "provider": image_defaults.provider,
                "model": image_defaults.model,
                "quality": image_defaults.quality,
                "style": image_defaults.preferred_style,
                "aspect_ratio": image_defaults.aspect_ratio,
                "mode": getattr(args, "mode", "sync"),
            },
        },
        "outputs": {
            "scenes_extracted": int(stats_dict.get("scenes_extracted", 0) or 0),
            "scenes_refined": int(stats_dict.get("scenes_refined", 0) or 0),
            "scenes_ranked": int(stats_dict.get("scenes_ranked", 0) or 0),
            "prompts_generated": int(stats_dict.get("prompts_generated", 0) or 0),
            "images_generated": int(stats_dict.get("images_generated", 0) or 0),
        },
        "errors": {
            "count": len(error_messages),
            "messages": error_messages,
            "code": error_code,
        },
        "diagnostics": diagnostics or {},
    }


async def _execute_pipeline_run(
    *,
    run_id: UUID,
    args: argparse.Namespace,
    config_overrides: dict[str, Any] | None = None,
) -> None:
    """Execute the end-to-end pipeline in a background task."""

    execution_started_at = datetime.now(timezone.utc)
    observed_book_slug = getattr(args, "book_slug", None)
    diagnostics = _RunDiagnosticsTracker(run_id=run_id, started_at=execution_started_at)

    _log_pipeline_event(
        event="run_started",
        run_id=str(run_id),
        book_slug=observed_book_slug,
        status="pending",
    )

    async def _stage_callback(stage: str) -> None:
        stage_started_at = datetime.now(timezone.utc)
        completed_stage, completed_duration_ms = diagnostics.start_stage(
            stage=stage,
            at=stage_started_at,
        )
        if completed_stage is not None:
            _log_pipeline_event(
                event="stage_completed",
                run_id=str(run_id),
                book_slug=observed_book_slug,
                stage=completed_stage,
                duration_ms=completed_duration_ms,
            )
        _log_pipeline_event(
            event="stage_started",
            run_id=str(run_id),
            book_slug=observed_book_slug,
            stage=stage,
        )
        _update_status(
            run_id=run_id,
            status_value=stage,
            current_stage=stage,
            error_message=None,
        )
        _set_document_stage_running(run_id=run_id, pipeline_stage=stage)

    try:
        stats = await _run_full_pipeline(args, stage_callback=_stage_callback)
    except Exception as exc:
        failure_message = _format_failure_message(exc)
        completed_at = datetime.now(timezone.utc)
        error_code = _classify_pipeline_error_code(
            exc=exc,
            error_message=failure_message,
            observed_stage=diagnostics.current_stage,
        )
        diagnostics_payload = diagnostics.finalize(
            status_value="failed",
            completed_at=completed_at,
            error_code=error_code,
            error_message=failure_message,
        )
        usage_summary = _build_usage_summary(
            args=args,
            stats=None,
            status_value="failed",
            started_at=execution_started_at,
            completed_at=completed_at,
            config_overrides=config_overrides,
            error_message=failure_message,
            error_code=error_code,
            diagnostics=diagnostics_payload,
        )
        _log_pipeline_event(
            event="run_failed",
            level=logging.ERROR,
            run_id=str(run_id),
            book_slug=observed_book_slug,
            stage=diagnostics_payload.get("observed_stage") or "pending",
            error_code=error_code,
            error_message=failure_message,
        )
        _update_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=failure_message,
            usage_summary=usage_summary,
            completed=True,
        )
        _set_document_stage_failed(
            run_id=run_id,
            pipeline_stage=diagnostics.current_stage,
            error_message=failure_message,
        )
        _sync_document_stage_statuses(
            run_id=run_id,
            preserve_failed_pipeline_stage=diagnostics.current_stage,
        )
        return

    if stats.errors:
        combined_error = " | ".join(stats.errors)
        completed_at = datetime.now(timezone.utc)
        error_code = _classify_pipeline_error_code(
            error_message=combined_error,
            observed_stage=diagnostics.current_stage,
        )
        diagnostics_payload = diagnostics.finalize(
            status_value="failed",
            completed_at=completed_at,
            error_code=error_code,
            error_message=combined_error[:2000],
        )
        usage_summary = _build_usage_summary(
            args=args,
            stats=stats,
            status_value="failed",
            started_at=execution_started_at,
            completed_at=completed_at,
            config_overrides=config_overrides,
            error_message=combined_error[:2000],
            error_code=error_code,
            diagnostics=diagnostics_payload,
        )
        _update_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=combined_error[:2000],
            usage_summary=usage_summary,
            completed=True,
        )
        _set_document_stage_failed(
            run_id=run_id,
            pipeline_stage=diagnostics.current_stage,
            error_message=combined_error[:2000],
        )
        _sync_document_stage_statuses(
            run_id=run_id,
            preserve_failed_pipeline_stage=diagnostics.current_stage,
        )
        _log_pipeline_event(
            event="run_failed",
            level=logging.ERROR,
            run_id=str(run_id),
            book_slug=observed_book_slug,
            stage=diagnostics_payload.get("observed_stage") or "pending",
            error_code=error_code,
            error_count=len(stats.errors),
            error_message=combined_error[:2000],
        )
        return

    completed_at = datetime.now(timezone.utc)
    diagnostics_payload = diagnostics.finalize(
        status_value="completed",
        completed_at=completed_at,
    )
    usage_summary = _build_usage_summary(
        args=args,
        stats=stats,
        status_value="completed",
        started_at=execution_started_at,
        completed_at=completed_at,
        config_overrides=config_overrides,
        diagnostics=diagnostics_payload,
    )
    _update_status(
        run_id=run_id,
        status_value="completed",
        current_stage="completed",
        error_message=None,
        usage_summary=usage_summary,
        completed=True,
    )
    _sync_document_stage_statuses(
        run_id=run_id,
        preserve_failed_pipeline_stage=None,
    )
    _log_pipeline_event(
        event="run_completed",
        run_id=str(run_id),
        book_slug=observed_book_slug,
        stage=diagnostics_payload.get("observed_stage"),
        duration_ms=usage_summary.get("timing", {}).get("duration_ms"),
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
    service = PipelineRunStartService(session)
    try:
        resolution = service.resolve_pipeline_request(launch_request)
    except PipelineValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    coro = _execute_pipeline_run(
        run_id=resolution.run.id,
        args=resolution.args,
        config_overrides=resolution.config_overrides,
    )
    try:
        _spawn_background_task(
            coro,
            task_name=f"pipeline-run-{resolution.run.id}",
        )
    except Exception as exc:
        if asyncio.iscoroutine(coro):
            coro.close()
        logger.exception(
            "Failed to create pipeline run task: run_id=%s",
            resolution.run.id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start pipeline run",
        ) from exc

    return PipelineRunRead.model_validate(resolution.run)


@router.get("/{run_id}", response_model=PipelineRunRead)
async def get_pipeline_run(*, session: SessionDep, run_id: UUID) -> PipelineRunRead:
    """Return the current state of a pipeline run."""

    repository = PipelineRunRepository(session)
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PipelineRunRead.model_validate(run)
