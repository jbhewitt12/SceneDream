"""Core pipeline orchestrator: status transitions, diagnostics, and stage dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.db import engine
from app.repositories import (
    DocumentRepository,
    GeneratedImageRepository,
    PipelineRunRepository,
    SceneExtractionRepository,
    SceneRankingRepository,
)
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationService,
)
from app.services.image_prompt_generation.models import ImagePromptGenerationConfig
from app.services.scene_extraction.scene_extraction import (
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_ranking.scene_ranking_service import (
    SceneRankingConfig,
    SceneRankingService,
)

from .document_stage_status_service import DocumentStageStatusService
from .orchestrator_config import (
    PipelineExecutionResult,
    PipelineStats,
    PreparedPipelineExecution,
    PromptExecutionOptions,
    SceneTarget,
)

logger = logging.getLogger(__name__)


def _safe_int(value: object) -> int:
    """Coerce a stats dict value to int, defaulting to 0 for non-numeric types."""
    if isinstance(value, int):
        return value
    return 0


# ---------------------------------------------------------------------------
# Stage execution helpers
# ---------------------------------------------------------------------------


def _extract_book_with_fresh_session(
    config: SceneExtractionConfig,
    book_path: Path,
) -> dict[str, object]:
    """Run extraction in a fresh session for background thread safety."""
    with Session(engine) as session:
        extractor = SceneExtractor(session=session, config=config)
        stats = extractor.extract_book(book_path)
        session.commit()
        return stats


def _resolve_ranked_scene_fetch_limit(target_scenes: int | None) -> int:
    """Return a ranking scan depth that tolerates skipped scenes."""
    if isinstance(target_scenes, int) and target_scenes > 0:
        return max(target_scenes * 50, 100)
    return 100


def _build_prompt_generation_config(
    options: PromptExecutionOptions,
) -> ImagePromptGenerationConfig:
    """Build ImagePromptGenerationConfig from orchestration prompt options."""
    kwargs: dict[str, Any] = {}
    if options.prompt_art_style_mode:
        kwargs["prompt_art_style_mode"] = options.prompt_art_style_mode
    if options.prompt_art_style_text is not None:
        kwargs["prompt_art_style_text"] = options.prompt_art_style_text
    if options.prompts_per_scene is not None:
        kwargs["variants_count"] = options.prompts_per_scene
        kwargs[
            "use_ranking_recommendation"
        ] = not options.ignore_ranking_recommendations
    else:
        kwargs["use_ranking_recommendation"] = True
    return ImagePromptGenerationConfig(**kwargs)


# ---------------------------------------------------------------------------
# Diagnostics tracker
# ---------------------------------------------------------------------------


class RunDiagnosticsTracker:
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


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def classify_pipeline_error_code(
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


# ---------------------------------------------------------------------------
# Structured logging helper
# ---------------------------------------------------------------------------


def log_pipeline_event(
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


# ---------------------------------------------------------------------------
# Usage summary builder
# ---------------------------------------------------------------------------


def build_usage_summary(
    *,
    prepared: PreparedPipelineExecution,
    stats: PipelineStats | None,
    status_value: str,
    started_at: datetime,
    completed_at: datetime,
    error_message: str | None = None,
    error_code: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the backward-compatible usage_summary dict from orchestrator state."""

    config = prepared.config
    stages = config.stages
    prompt_opts = config.prompt_options
    image_opts = config.image_options
    context = prepared.context

    prompt_defaults = ImagePromptGenerationConfig()
    image_defaults = ImageGenerationConfig(
        quality=image_opts.quality,
        preferred_style=image_opts.style,
        aspect_ratio=image_opts.aspect_ratio,
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
            "book_slug": context.book_slug,
            "book_path": context.book_path,
            "images_for_scenes": prompt_opts.images_for_scenes,
            "prompts_for_scenes": prompt_opts.prompts_for_scenes,
            "prompts_per_scene": prompt_opts.prompts_per_scene,
            "prompt_art_style_mode": prompt_opts.prompt_art_style_mode,
            "prompt_art_style_text": prompt_opts.prompt_art_style_text,
            "skip_extraction": not stages.run_extraction,
            "skip_ranking": not stages.run_ranking,
            "skip_prompts": not stages.run_prompt_generation,
            "quality": image_opts.quality,
            "style": image_opts.style,
            "aspect_ratio": image_opts.aspect_ratio,
            "mode": "sync",
        },
        "effective": {
            "config_overrides": prepared.config_overrides,
            "prompt_generation": {
                "model_vendor": prompt_defaults.model_vendor,
                "model_name": prompt_defaults.model_name,
                "backup_model_vendor": prompt_defaults.backup_model_vendor,
                "backup_model_name": prompt_defaults.backup_model_name,
                "prompt_version": prompt_defaults.prompt_version,
                "target_provider": prompt_defaults.target_provider,
                "prompt_art_style_mode": prompt_opts.prompt_art_style_mode,
                "prompt_art_style_text": prompt_opts.prompt_art_style_text,
            },
            "image_generation": {
                "provider": image_defaults.provider,
                "model": image_defaults.model,
                "quality": image_defaults.quality,
                "style": image_defaults.preferred_style,
                "aspect_ratio": image_defaults.aspect_ratio,
                "mode": "sync",
            },
        },
        "outputs": {
            "scenes_extracted": _safe_int(stats_dict.get("scenes_extracted", 0)),
            "scenes_refined": _safe_int(stats_dict.get("scenes_refined", 0)),
            "scenes_ranked": _safe_int(stats_dict.get("scenes_ranked", 0)),
            "prompts_generated": _safe_int(stats_dict.get("prompts_generated", 0)),
            "images_generated": _safe_int(stats_dict.get("images_generated", 0)),
        },
        "errors": {
            "count": len(error_messages),
            "messages": error_messages,
            "code": error_code,
        },
        "diagnostics": diagnostics or {},
    }


# ---------------------------------------------------------------------------
# Internal DB helpers (fresh sessions for background work)
# ---------------------------------------------------------------------------


def _update_run_status(
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


def _apply_document_stage_update(
    *,
    run_id: UUID,
    update_fn: Callable[[DocumentStageStatusService, Any], object],
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
        _apply_document_stage_update(
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
        _apply_document_stage_update(
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
        _apply_document_stage_update(
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


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """Centralized execution engine for orchestrated pipeline runs.

    The orchestrator owns:
    - run status transitions
    - diagnostics tracking
    - stage dispatch
    - usage-summary construction
    - error classification and finalization

    Stage methods are stubs in this phase. They will be wired to real
    service calls in Phase 5+ when callers migrate to the orchestrator.
    """

    def __init__(
        self,
        *,
        update_run_status: Callable[..., None] = _update_run_status,
        set_document_stage_running: Callable[..., None] = _set_document_stage_running,
        set_document_stage_failed: Callable[..., None] = _set_document_stage_failed,
        sync_document_stage_statuses: Callable[
            ..., None
        ] = _sync_document_stage_statuses,
    ) -> None:
        self._update_run_status = update_run_status
        self._set_document_stage_running = set_document_stage_running
        self._set_document_stage_failed = set_document_stage_failed
        self._sync_document_stage_statuses = sync_document_stage_statuses

    async def execute(
        self,
        prepared: PreparedPipelineExecution,
    ) -> PipelineExecutionResult:
        """Execute a prepared pipeline run through its stage plan."""

        run_id = prepared.run_id
        config = prepared.config
        context = prepared.context
        stages = config.stages

        started_at = datetime.now(timezone.utc)
        diagnostics = RunDiagnosticsTracker(run_id=run_id, started_at=started_at)
        stats = PipelineStats()

        book_slug = context.book_slug

        log_pipeline_event(
            event="run_started",
            run_id=str(run_id),
            book_slug=book_slug,
            status="pending",
        )

        try:
            if stages.run_extraction:
                await self._transition_stage(
                    run_id=run_id,
                    stage="extracting",
                    book_slug=book_slug,
                    diagnostics=diagnostics,
                )
                await self._execute_extraction(prepared, stats)

            if stages.run_ranking:
                await self._transition_stage(
                    run_id=run_id,
                    stage="ranking",
                    book_slug=book_slug,
                    diagnostics=diagnostics,
                )
                await self._execute_ranking(prepared, stats)

            if stages.run_prompt_generation:
                await self._transition_stage(
                    run_id=run_id,
                    stage="generating_prompts",
                    book_slug=book_slug,
                    diagnostics=diagnostics,
                )
                await self._execute_prompt_generation(prepared, stats)

            if stages.run_image_generation:
                await self._transition_stage(
                    run_id=run_id,
                    stage="generating_images",
                    book_slug=book_slug,
                    diagnostics=diagnostics,
                )
                await self._execute_image_generation(prepared, stats)

        except Exception as exc:
            return self._finalize_failure(
                run_id=run_id,
                prepared=prepared,
                stats=stats,
                started_at=started_at,
                diagnostics=diagnostics,
                exc=exc,
            )

        if stats.errors:
            # For scene-targeted runs, partial success (at least one image)
            # is still considered a successful completion.
            is_scene_target = isinstance(config.target, SceneTarget)
            if is_scene_target and stats.images_generated > 0:
                logger.info(
                    "Scene-targeted run had errors but generated %d images; "
                    "treating as partial success.",
                    stats.images_generated,
                )
            else:
                return self._finalize_stats_failure(
                    run_id=run_id,
                    prepared=prepared,
                    stats=stats,
                    started_at=started_at,
                    diagnostics=diagnostics,
                )

        # For scene-targeted image runs, fail if zero images were generated
        if (
            isinstance(config.target, SceneTarget)
            and stages.run_image_generation
            and stats.images_generated == 0
            and not stats.errors  # avoid double-finalizing
        ):
            stats.errors.append("No images were generated for scene-targeted run")
            return self._finalize_stats_failure(
                run_id=run_id,
                prepared=prepared,
                stats=stats,
                started_at=started_at,
                diagnostics=diagnostics,
            )

        return self._finalize_success(
            run_id=run_id,
            prepared=prepared,
            stats=stats,
            started_at=started_at,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # Stage dispatch methods
    # ------------------------------------------------------------------

    async def _execute_extraction(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Execute extraction stage."""
        context = prepared.context
        book_path = context.book_path
        if not book_path:
            raise ValueError("book_path is required for extraction")

        config = SceneExtractionConfig(
            enable_refinement=True,
            book_slug=context.book_slug,
            resume_from_chapter=context.extraction_resume_from_chapter,
            resume_from_chunk=context.extraction_resume_from_chunk,
        )
        loop = asyncio.get_running_loop()
        extraction_stats = await loop.run_in_executor(
            None,
            _extract_book_with_fresh_session,
            config,
            Path(book_path),
        )
        scenes_count = extraction_stats.get("scenes", 0)
        stats.scenes_extracted = scenes_count if isinstance(scenes_count, int) else 0
        logger.info("Extracted %d scenes", stats.scenes_extracted)

    async def _execute_ranking(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Execute ranking stage."""
        context = prepared.context
        book_slug = context.book_slug
        run_id = prepared.run_id
        if not book_slug:
            raise ValueError("book_slug is required for ranking")

        with Session(engine) as session:
            scene_repo = SceneExtractionRepository(session)
            ranking_config = SceneRankingConfig()
            ranking_service = SceneRankingService(session, config=ranking_config)

            if context.ranking_scene_ids:
                scenes_to_rank = [
                    scene
                    for sid in context.ranking_scene_ids
                    if (scene := scene_repo.get(sid)) is not None
                ]
            else:
                scenes_to_rank = scene_repo.list_for_book(book_slug)

            for scene in scenes_to_rank:
                try:
                    result = await ranking_service.rank_scene(
                        scene,
                        overwrite=False,
                        dry_run=False,
                        pipeline_run_id=run_id,
                    )
                    if result and hasattr(result, "id"):
                        stats.scenes_ranked += 1
                        context.created_ranking_ids.append(result.id)
                        logger.info(
                            "Ranked scene %d (chapter %d): priority=%.1f",
                            scene.scene_number,
                            scene.chapter_number,
                            result.overall_priority,
                        )
                except Exception as exc:
                    error_msg = f"Failed to rank scene {scene.id}: {exc}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

            logger.info("Ranked %d scenes", stats.scenes_ranked)

    async def _execute_prompt_generation(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Execute prompt generation stage.

        Dispatches to scene-targeted or document-targeted prompt generation
        based on the execution target type.
        """
        if isinstance(prepared.config.target, SceneTarget):
            await self._execute_scene_prompt_generation(prepared, stats)
        else:
            await self._execute_document_prompt_generation(prepared, stats)

    async def _execute_scene_prompt_generation(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Generate exactly N fresh prompts for each scene in a SceneTarget."""
        target: SceneTarget = prepared.config.target  # type: ignore[assignment]
        context = prepared.context
        run_id = prepared.run_id
        prompt_options = prepared.config.prompt_options

        variant_count = prompt_options.scene_variant_count or 1
        prompt_config = _build_prompt_generation_config(prompt_options)
        # Override variants_count to produce exactly the requested number
        prompt_config.variants_count = variant_count

        with Session(engine) as session:
            scene_repo = SceneExtractionRepository(session)
            prompt_service = ImagePromptGenerationService(session, config=prompt_config)

            for scene_id in target.scene_ids:
                scene = scene_repo.get(scene_id)
                if scene is None:
                    error_msg = f"Scene {scene_id} not found during prompt generation"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)
                    continue

                try:
                    prompts = await prompt_service.generate_for_scene(
                        scene,
                        variants_count=variant_count,
                        dry_run=False,
                        overwrite=False,
                        metadata={"source": "scene_target"},
                        pipeline_run_id=run_id,
                    )
                    if prompts:
                        stats.prompts_generated += len(prompts)
                        for p in prompts:
                            prompt_id = getattr(p, "id", None)
                            if prompt_id is not None:
                                context.created_prompt_ids.append(prompt_id)
                                scene_list = (
                                    context.created_prompt_ids_by_scene.setdefault(
                                        scene_id, []
                                    )
                                )
                                scene_list.append(prompt_id)
                        logger.info(
                            "Generated %d prompts for scene %s",
                            len(prompts),
                            scene_id,
                        )
                except Exception as exc:
                    error_msg = (
                        f"Failed to generate prompts for scene {scene_id}: {exc}"
                    )
                    logger.error(error_msg)
                    try:
                        session.rollback()
                    except Exception:
                        logger.exception(
                            "Failed to rollback after prompt error for scene %s",
                            scene_id,
                        )
                    stats.errors.append(error_msg)

        logger.info(
            "Scene-targeted prompt generation complete: %d prompts for %d scenes",
            stats.prompts_generated,
            len(target.scene_ids),
        )

    async def _execute_document_prompt_generation(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Execute prompt generation for document-targeted runs."""
        context = prepared.context
        book_slug = context.book_slug
        run_id = prepared.run_id
        prompt_options = prepared.config.prompt_options

        if not book_slug:
            raise ValueError("book_slug is required for prompt generation")

        prompts_for_scenes = prompt_options.prompts_for_scenes
        if prompts_for_scenes is None:
            prompts_for_scenes = prompt_options.images_for_scenes

        prompt_config = _build_prompt_generation_config(prompt_options)

        with Session(engine) as session:
            ranking_repo = SceneRankingRepository(session)
            image_repo = GeneratedImageRepository(session)
            prompt_service = ImagePromptGenerationService(session, config=prompt_config)

            fetch_limit = _resolve_ranked_scene_fetch_limit(prompts_for_scenes)
            rankings = ranking_repo.list_top_rankings_for_book(
                book_slug=book_slug,
                limit=fetch_limit,
                include_scene=True,
            )

            scenes_with_prompts = 0
            seen_scene_ids: set[UUID] = set()

            for ranking in rankings:
                if (
                    prompts_for_scenes is not None
                    and scenes_with_prompts >= prompts_for_scenes
                ):
                    break

                scene = getattr(ranking, "scene_extraction", None)
                scene_id = getattr(ranking, "scene_extraction_id", None)
                if scene is None or not isinstance(scene_id, UUID):
                    continue
                if scene_id in seen_scene_ids:
                    continue
                seen_scene_ids.add(scene_id)

                if image_repo.list_for_scene(scene_id, limit=1):
                    continue

                try:
                    prompts = await prompt_service.generate_for_scene(
                        scene,
                        dry_run=False,
                        overwrite=False,
                        metadata={"source": "orchestrator"},
                        pipeline_run_id=run_id,
                    )
                    if prompts:
                        stats.prompts_generated += len(prompts)
                        scenes_with_prompts += 1
                        for p in prompts:
                            prompt_id = getattr(p, "id", None)
                            if prompt_id is not None:
                                context.created_prompt_ids.append(prompt_id)
                                scene_list = (
                                    context.created_prompt_ids_by_scene.setdefault(
                                        scene_id, []
                                    )
                                )
                                scene_list.append(prompt_id)
                        logger.info(
                            "Generated %d prompts for scene %d (chapter %d)",
                            len(prompts),
                            scene.scene_number,
                            scene.chapter_number,
                        )
                except Exception as exc:
                    error_msg = (
                        f"Failed to generate prompts for scene {scene_id}: {exc}"
                    )
                    logger.error(error_msg)
                    try:
                        session.rollback()
                    except Exception:
                        logger.exception(
                            "Failed to rollback after prompt error for scene %s",
                            scene_id,
                        )
                    stats.errors.append(error_msg)

            logger.info(
                "Generated %d prompts for %d scenes",
                stats.prompts_generated,
                scenes_with_prompts,
            )

    async def _execute_image_generation(
        self,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
    ) -> None:
        """Execute image generation stage using prompt IDs from this run."""
        context = prepared.context
        run_id = prepared.run_id
        image_options = prepared.config.image_options

        prompt_ids = list(context.created_prompt_ids)
        if not prompt_ids:
            logger.warning("No prompt IDs available for image generation; skipping.")
            return

        image_config = ImageGenerationConfig(
            quality=image_options.quality,
            preferred_style=image_options.style,
            aspect_ratio=image_options.aspect_ratio,
            concurrency=image_options.concurrency,
        )

        with Session(engine) as session:
            image_service = ImageGenerationService(session, config=image_config)

            try:
                generated_ids = await image_service.generate_for_selection(
                    prompt_ids=prompt_ids,
                    quality=image_options.quality,
                    preferred_style=image_options.style,
                    aspect_ratio=image_options.aspect_ratio,
                    dry_run=False,
                    pipeline_run_id=run_id,
                )
                stats.images_generated = len(generated_ids)
                context.created_image_ids.extend(generated_ids)
                logger.info("Generated %d images", stats.images_generated)
            except Exception as exc:
                error_msg = f"Failed to generate images: {exc}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

    # ------------------------------------------------------------------
    # Stage transition helper
    # ------------------------------------------------------------------

    async def _transition_stage(
        self,
        *,
        run_id: UUID,
        stage: str,
        book_slug: str | None,
        diagnostics: RunDiagnosticsTracker,
    ) -> None:
        """Record a stage transition in diagnostics, DB, and logs."""

        stage_started_at = datetime.now(timezone.utc)
        completed_stage, completed_duration_ms = diagnostics.start_stage(
            stage=stage,
            at=stage_started_at,
        )
        if completed_stage is not None:
            log_pipeline_event(
                event="stage_completed",
                run_id=str(run_id),
                book_slug=book_slug,
                stage=completed_stage,
                duration_ms=completed_duration_ms,
            )
        log_pipeline_event(
            event="stage_started",
            run_id=str(run_id),
            book_slug=book_slug,
            stage=stage,
        )
        self._update_run_status(
            run_id=run_id,
            status_value=stage,
            current_stage=stage,
            error_message=None,
        )
        self._set_document_stage_running(run_id=run_id, pipeline_stage=stage)

    # ------------------------------------------------------------------
    # Finalization helpers
    # ------------------------------------------------------------------

    def _finalize_failure(
        self,
        *,
        run_id: UUID,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
        started_at: datetime,
        diagnostics: RunDiagnosticsTracker,
        exc: Exception,
    ) -> PipelineExecutionResult:
        """Handle an exception-based failure."""

        failure_message = _format_failure_message(exc)
        completed_at = datetime.now(timezone.utc)
        error_code = classify_pipeline_error_code(
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
        usage_summary = build_usage_summary(
            prepared=prepared,
            stats=stats,
            status_value="failed",
            started_at=started_at,
            completed_at=completed_at,
            error_message=failure_message,
            error_code=error_code,
            diagnostics=diagnostics_payload,
        )
        log_pipeline_event(
            event="run_failed",
            level=logging.ERROR,
            run_id=str(run_id),
            book_slug=prepared.context.book_slug,
            stage=diagnostics_payload.get("observed_stage") or "pending",
            error_code=error_code,
            error_message=failure_message,
        )
        self._update_run_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=failure_message,
            usage_summary=usage_summary,
            completed=True,
        )
        self._set_document_stage_failed(
            run_id=run_id,
            pipeline_stage=diagnostics.current_stage,
            error_message=failure_message,
        )
        self._sync_document_stage_statuses(
            run_id=run_id,
            preserve_failed_pipeline_stage=diagnostics.current_stage,
        )
        return PipelineExecutionResult(
            run_id=run_id,
            status="failed",
            stats=stats,
            diagnostics=diagnostics_payload,
            usage_summary=usage_summary,
            error_message=failure_message,
            error_code=error_code,
        )

    def _finalize_stats_failure(
        self,
        *,
        run_id: UUID,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
        started_at: datetime,
        diagnostics: RunDiagnosticsTracker,
    ) -> PipelineExecutionResult:
        """Handle failure when stats.errors is non-empty."""

        combined_error = " | ".join(stats.errors)
        completed_at = datetime.now(timezone.utc)
        error_code = classify_pipeline_error_code(
            error_message=combined_error,
            observed_stage=diagnostics.current_stage,
        )
        diagnostics_payload = diagnostics.finalize(
            status_value="failed",
            completed_at=completed_at,
            error_code=error_code,
            error_message=combined_error[:2000],
        )
        usage_summary = build_usage_summary(
            prepared=prepared,
            stats=stats,
            status_value="failed",
            started_at=started_at,
            completed_at=completed_at,
            error_message=combined_error[:2000],
            error_code=error_code,
            diagnostics=diagnostics_payload,
        )
        self._update_run_status(
            run_id=run_id,
            status_value="failed",
            current_stage="failed",
            error_message=combined_error[:2000],
            usage_summary=usage_summary,
            completed=True,
        )
        self._set_document_stage_failed(
            run_id=run_id,
            pipeline_stage=diagnostics.current_stage,
            error_message=combined_error[:2000],
        )
        self._sync_document_stage_statuses(
            run_id=run_id,
            preserve_failed_pipeline_stage=diagnostics.current_stage,
        )
        log_pipeline_event(
            event="run_failed",
            level=logging.ERROR,
            run_id=str(run_id),
            book_slug=prepared.context.book_slug,
            stage=diagnostics_payload.get("observed_stage") or "pending",
            error_code=error_code,
            error_count=len(stats.errors),
            error_message=combined_error[:2000],
        )
        return PipelineExecutionResult(
            run_id=run_id,
            status="failed",
            stats=stats,
            diagnostics=diagnostics_payload,
            usage_summary=usage_summary,
            error_message=combined_error[:2000],
            error_code=error_code,
        )

    def _finalize_success(
        self,
        *,
        run_id: UUID,
        prepared: PreparedPipelineExecution,
        stats: PipelineStats,
        started_at: datetime,
        diagnostics: RunDiagnosticsTracker,
    ) -> PipelineExecutionResult:
        """Handle a successful completion."""

        completed_at = datetime.now(timezone.utc)
        diagnostics_payload = diagnostics.finalize(
            status_value="completed",
            completed_at=completed_at,
        )
        usage_summary = build_usage_summary(
            prepared=prepared,
            stats=stats,
            status_value="completed",
            started_at=started_at,
            completed_at=completed_at,
            diagnostics=diagnostics_payload,
        )
        self._update_run_status(
            run_id=run_id,
            status_value="completed",
            current_stage="completed",
            error_message=None,
            usage_summary=usage_summary,
            completed=True,
        )
        self._sync_document_stage_statuses(
            run_id=run_id,
            preserve_failed_pipeline_stage=None,
        )
        log_pipeline_event(
            event="run_completed",
            run_id=str(run_id),
            book_slug=prepared.context.book_slug,
            stage=diagnostics_payload.get("observed_stage"),
            duration_ms=usage_summary.get("timing", {}).get("duration_ms"),
        )
        return PipelineExecutionResult(
            run_id=run_id,
            status="completed",
            stats=stats,
            diagnostics=diagnostics_payload,
            usage_summary=usage_summary,
        )
