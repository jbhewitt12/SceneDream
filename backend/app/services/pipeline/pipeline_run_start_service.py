"""Service-layer orchestration for launching pipeline runs."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    coerce_prompt_art_style_selection,
)
from app.repositories import (
    AppSettingsRepository,
    DocumentRepository,
    GeneratedImageRepository,
    ImagePromptRepository,
    PipelineRunRepository,
    SceneExtractionRepository,
    SceneRankingRepository,
)
from app.schemas import PipelineRunStartRequest
from app.services.books.book_content_service import BookContentService
from app.services.image_gen_cli import _resolve_default_scenes_per_run
from models.document import Document
from models.pipeline_run import PipelineRun

from .document_stage_status_service import (
    STAGE_STATUS_COMPLETED,
    DocumentStageStatusService,
)
from .exceptions import (
    DocumentNotFoundError,
    PipelineValidationError,
    SourceDocumentMissingError,
)
from .orchestrator_config import (
    CustomRemixTarget,
    DocumentTarget,
    PipelineExecutionConfig,
    PipelineExecutionContext,
    PreparedPipelineExecution,
    RemixTarget,
    SceneTarget,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineRunResolution:
    """Resolved launch inputs used by the route background task."""

    run: PipelineRun
    args: argparse.Namespace
    config_overrides: dict[str, Any]


class PipelineRunStartService:
    """Resolves pipeline start requests and persists pending runs."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings_repo = AppSettingsRepository(session)
        self._document_repo = DocumentRepository(session)
        self._run_repo = PipelineRunRepository(session)
        self._scene_repo = SceneExtractionRepository(session)
        self._document_stage_status_service = DocumentStageStatusService(session)
        self._book_service = BookContentService()

    def resolve_pipeline_request(
        self,
        launch_request: PipelineRunStartRequest,
    ) -> PipelineRunResolution:
        resolved_document: Document | None = None
        resolved_book_slug = launch_request.book_slug
        resolved_book_path = launch_request.book_path

        if launch_request.document_id is not None:
            resolved_document = self._document_repo.get(launch_request.document_id)
            if resolved_document is None:
                raise DocumentNotFoundError()
            if not resolved_book_slug:
                resolved_book_slug = resolved_document.slug
            if not resolved_book_path and resolved_document.source_path:
                resolved_book_path = resolved_document.source_path

        if resolved_document is None and resolved_book_slug:
            resolved_document = self._document_repo.get_by_slug(resolved_book_slug)

        if resolved_document is not None:
            self._document_stage_status_service.sync_document(
                document=resolved_document
            )
            self._session.flush()

        if not resolved_book_slug:
            raise PipelineValidationError(
                "book_slug is required when document_id is not provided"
            )

        should_skip_extraction = launch_request.skip_extraction
        should_skip_ranking = launch_request.skip_ranking
        if resolved_document is not None:
            if resolved_document.extraction_status == STAGE_STATUS_COMPLETED:
                should_skip_extraction = True
            if resolved_document.ranking_status == STAGE_STATUS_COMPLETED:
                should_skip_ranking = True

        has_existing_extractions = bool(
            self._scene_repo.list_for_book(resolved_book_slug)
        )
        source_path_exists = self._source_path_exists(resolved_book_path)

        # Skipping ranking without reusing the existing extracted scenes is
        # internally inconsistent for prompt/image-only launches.
        if (
            should_skip_ranking
            and not should_skip_extraction
            and has_existing_extractions
        ):
            should_skip_extraction = True

        if not should_skip_extraction:
            if source_path_exists:
                pass
            elif has_existing_extractions:
                should_skip_extraction = True
            elif resolved_book_path:
                raise SourceDocumentMissingError(
                    "book_path does not exist and no extracted scenes are available to resume"
                )
            else:
                raise SourceDocumentMissingError(
                    "book_path is required when extraction is enabled"
                )

        if not source_path_exists:
            resolved_book_path = None

        images_for_scenes = launch_request.images_for_scenes
        if images_for_scenes is None:
            images_for_scenes = self._resolve_default_scenes_per_run()

        (
            resolved_prompt_art_style_mode,
            resolved_prompt_art_style_text,
        ) = self._resolve_prompt_art_style(launch_request)

        args = self._build_run_namespace(
            launch_request=launch_request,
            book_slug=resolved_book_slug,
            book_path=resolved_book_path,
            images_for_scenes=images_for_scenes,
            skip_extraction=should_skip_extraction,
            skip_ranking=should_skip_ranking,
            prompt_art_style_mode=resolved_prompt_art_style_mode,
            prompt_art_style_text=resolved_prompt_art_style_text,
        )

        config_overrides = launch_request.model_dump(exclude_none=True, mode="json")
        config_overrides["resolved_book_slug"] = resolved_book_slug
        if resolved_book_path is not None:
            config_overrides["resolved_book_path"] = resolved_book_path
        config_overrides["skip_extraction"] = should_skip_extraction
        config_overrides["skip_ranking"] = should_skip_ranking
        config_overrides["resolved_images_for_scenes"] = images_for_scenes
        config_overrides["resolved_prompt_art_style_mode"] = (
            resolved_prompt_art_style_mode
        )
        config_overrides["resolved_prompt_art_style_text"] = (
            resolved_prompt_art_style_text
        )

        run = self._run_repo.create(
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

        return PipelineRunResolution(
            run=run,
            args=args,
            config_overrides=config_overrides,
        )

    # ------------------------------------------------------------------
    # New orchestrator-oriented preparation
    # ------------------------------------------------------------------

    def prepare_execution(
        self,
        config: PipelineExecutionConfig,
    ) -> PreparedPipelineExecution:
        """Resolve entities, defaults, and sticky skips then create a pending run.

        This is the unified preparation entry point for all target types.
        It returns a ``PreparedPipelineExecution`` that the orchestrator can
        execute without further business-rule resolution.
        """
        errors = config.validate()
        if errors:
            raise PipelineValidationError("; ".join(errors), status_code=422)

        target = config.target

        if isinstance(target, DocumentTarget):
            return self._prepare_document_target(config)
        if isinstance(target, SceneTarget):
            return self._prepare_scene_target(config)
        if isinstance(target, RemixTarget):
            return self._prepare_remix_target(config)
        if isinstance(target, CustomRemixTarget):
            return self._prepare_custom_remix_target(config)

        raise PipelineValidationError(  # pragma: no cover
            f"Unsupported target type: {type(target).__name__}"
        )

    # -- Document target --------------------------------------------------

    def _prepare_document_target(
        self,
        config: PipelineExecutionConfig,
    ) -> PreparedPipelineExecution:
        target: DocumentTarget = config.target  # type: ignore[assignment]

        resolved_document, resolved_book_slug, resolved_book_path = (
            self._resolve_document_identity(
                document_id=target.document_id,
                book_slug=target.book_slug,
                book_path=target.book_path,
            )
        )

        if not resolved_book_slug:
            raise PipelineValidationError(
                "book_slug is required when document_id is not provided"
            )

        # Sync document stage statuses before skip decisions
        if resolved_document is not None:
            self._document_stage_status_service.sync_document(
                document=resolved_document
            )
            self._session.flush()

        # --- Sticky completion skips ---
        run_extraction = config.stages.run_extraction
        run_ranking = config.stages.run_ranking

        if resolved_document is not None:
            if (
                run_extraction
                and resolved_document.extraction_status == STAGE_STATUS_COMPLETED
            ):
                run_extraction = False
            if (
                run_ranking
                and resolved_document.ranking_status == STAGE_STATUS_COMPLETED
            ):
                run_ranking = False

        has_existing_extractions = bool(
            self._scene_repo.list_for_book(resolved_book_slug)
        )
        source_path_exists = self._source_path_exists(resolved_book_path)

        # Skipping ranking without reusing existing scenes is inconsistent
        if not run_ranking and run_extraction and has_existing_extractions:
            run_extraction = False

        if run_extraction:
            if source_path_exists:
                pass
            elif has_existing_extractions:
                run_extraction = False
            elif resolved_book_path:
                raise SourceDocumentMissingError(
                    "book_path does not exist and no extracted scenes are available to resume"
                )
            else:
                raise SourceDocumentMissingError(
                    "book_path is required when extraction is enabled"
                )

        if not source_path_exists:
            resolved_book_path = None

        # --- Resolve defaults ---
        images_for_scenes = config.prompt_options.images_for_scenes
        if images_for_scenes is None:
            images_for_scenes = self._resolve_default_scenes_per_run()

        resolved_art_mode, resolved_art_text = self._resolve_art_style_from_options(
            config.prompt_options
        )

        # --- Resolve extraction resume state ---
        extraction_resume_chapter: int | None = None
        extraction_resume_chunk: int | None = None
        if run_extraction and resolved_book_slug:
            extraction_resume_chapter, extraction_resume_chunk = (
                self._resolve_extraction_resume(resolved_book_slug)
            )

        # --- Resolve ranking resume state ---
        ranking_scene_ids: list[UUID] | None = None
        ranking_resume_scene_id: UUID | None = None
        if run_ranking and resolved_book_slug:
            ranking_scene_ids, ranking_resume_scene_id = self._resolve_ranking_resume(
                resolved_book_slug
            )

        # Apply resolved stage plan
        effective_stages = config.stages.copy_with(
            run_extraction=run_extraction,
            run_ranking=run_ranking,
        )
        effective_prompt_options = config.prompt_options.copy_with(
            images_for_scenes=images_for_scenes,
            prompt_art_style_mode=resolved_art_mode,
            prompt_art_style_text=resolved_art_text,
        )
        effective_config = config.copy_with(
            stages=effective_stages,
            prompt_options=effective_prompt_options,
        )

        # --- Build config_overrides ---
        config_overrides = self._build_config_overrides(
            config=effective_config,
            resolved_book_slug=resolved_book_slug,
            resolved_book_path=resolved_book_path,
            images_for_scenes=images_for_scenes,
            resolved_art_mode=resolved_art_mode,
            resolved_art_text=resolved_art_text,
        )

        # --- Create context ---
        context = PipelineExecutionContext(
            document_id=resolved_document.id if resolved_document else None,
            book_slug=resolved_book_slug,
            book_path=resolved_book_path,
            extraction_resume_from_chapter=extraction_resume_chapter,
            extraction_resume_from_chunk=extraction_resume_chunk,
            ranking_scene_ids=ranking_scene_ids,
            ranking_resume_scene_id=ranking_resume_scene_id,
            requested_image_count=images_for_scenes,
        )

        # --- Persist run ---
        run = self._run_repo.create(
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

        return PreparedPipelineExecution(
            run_id=run.id,
            config=effective_config,
            config_overrides=config_overrides,
            context=context,
        )

    # -- Scene target -----------------------------------------------------

    def _prepare_scene_target(
        self,
        config: PipelineExecutionConfig,
    ) -> PreparedPipelineExecution:
        target: SceneTarget = config.target  # type: ignore[assignment]

        if not target.scene_ids:
            raise PipelineValidationError("SceneTarget requires at least one scene_id.")

        # Resolve first scene to derive document context
        scene_repo = self._scene_repo
        first_scene = scene_repo.get(target.scene_ids[0])
        if first_scene is None:
            raise PipelineValidationError(f"Scene {target.scene_ids[0]} not found.")

        # Validate all scene IDs exist
        for scene_id in target.scene_ids[1:]:
            if scene_repo.get(scene_id) is None:
                raise PipelineValidationError(f"Scene {scene_id} not found.")

        resolved_book_slug = target.book_slug or first_scene.book_slug
        resolved_document_id = target.document_id
        if resolved_document_id is None:
            doc = self._document_repo.get_by_slug(resolved_book_slug)
            if doc is not None:
                resolved_document_id = doc.id

        # Resolve art style and defaults
        resolved_art_mode, resolved_art_text = self._resolve_art_style_from_options(
            config.prompt_options
        )
        effective_prompt_options = config.prompt_options.copy_with(
            prompt_art_style_mode=resolved_art_mode,
            prompt_art_style_text=resolved_art_text,
        )
        effective_config = config.copy_with(prompt_options=effective_prompt_options)

        requested_image_count = config.prompt_options.scene_variant_count
        config_overrides = self._build_config_overrides(
            config=effective_config,
            resolved_book_slug=resolved_book_slug,
            resolved_book_path=None,
            images_for_scenes=None,
            resolved_art_mode=resolved_art_mode,
            resolved_art_text=resolved_art_text,
            extra={
                "scene_ids": [str(sid) for sid in target.scene_ids],
                "scene_variant_count": requested_image_count,
            },
        )

        context = PipelineExecutionContext(
            document_id=resolved_document_id,
            book_slug=resolved_book_slug,
            requested_image_count=requested_image_count,
        )

        run = self._run_repo.create(
            data={
                "document_id": resolved_document_id,
                "book_slug": resolved_book_slug,
                "status": "pending",
                "current_stage": "pending",
                "config_overrides": config_overrides,
            },
            commit=True,
            refresh=True,
        )

        return PreparedPipelineExecution(
            run_id=run.id,
            config=effective_config,
            config_overrides=config_overrides,
            context=context,
        )

    # -- Remix target -----------------------------------------------------

    def _prepare_remix_target(
        self,
        config: PipelineExecutionConfig,
    ) -> PreparedPipelineExecution:
        target: RemixTarget = config.target  # type: ignore[assignment]

        image_repo = GeneratedImageRepository(self._session)
        prompt_repo = ImagePromptRepository(self._session)

        source_image = image_repo.get(target.source_image_id)
        if source_image is None:
            raise PipelineValidationError(
                f"Source image {target.source_image_id} not found."
            )

        source_prompt = prompt_repo.get(target.source_prompt_id)
        if source_prompt is None:
            raise PipelineValidationError(
                f"Source prompt {target.source_prompt_id} not found."
            )

        resolved_book_slug = target.book_slug or source_image.book_slug
        resolved_document_id = target.document_id
        if resolved_document_id is None and resolved_book_slug:
            doc = self._document_repo.get_by_slug(resolved_book_slug)
            if doc is not None:
                resolved_document_id = doc.id

        resolved_art_mode, resolved_art_text = self._resolve_art_style_from_options(
            config.prompt_options
        )
        effective_prompt_options = config.prompt_options.copy_with(
            prompt_art_style_mode=resolved_art_mode,
            prompt_art_style_text=resolved_art_text,
        )
        effective_config = config.copy_with(prompt_options=effective_prompt_options)

        config_overrides = self._build_config_overrides(
            config=effective_config,
            resolved_book_slug=resolved_book_slug,
            resolved_book_path=None,
            images_for_scenes=None,
            resolved_art_mode=resolved_art_mode,
            resolved_art_text=resolved_art_text,
            extra={
                "source_image_id": str(target.source_image_id),
                "source_prompt_id": str(target.source_prompt_id),
            },
        )

        context = PipelineExecutionContext(
            document_id=resolved_document_id,
            book_slug=resolved_book_slug,
        )

        run = self._run_repo.create(
            data={
                "document_id": resolved_document_id,
                "book_slug": resolved_book_slug,
                "status": "pending",
                "current_stage": "pending",
                "config_overrides": config_overrides,
            },
            commit=True,
            refresh=True,
        )

        return PreparedPipelineExecution(
            run_id=run.id,
            config=effective_config,
            config_overrides=config_overrides,
            context=context,
        )

    # -- Custom remix target ----------------------------------------------

    def _prepare_custom_remix_target(
        self,
        config: PipelineExecutionConfig,
    ) -> PreparedPipelineExecution:
        target: CustomRemixTarget = config.target  # type: ignore[assignment]

        image_repo = GeneratedImageRepository(self._session)
        prompt_repo = ImagePromptRepository(self._session)

        source_image = image_repo.get(target.source_image_id)
        if source_image is None:
            raise PipelineValidationError(
                f"Source image {target.source_image_id} not found."
            )

        source_prompt = prompt_repo.get(target.source_prompt_id)
        if source_prompt is None:
            raise PipelineValidationError(
                f"Source prompt {target.source_prompt_id} not found."
            )

        resolved_book_slug = target.book_slug or source_image.book_slug
        resolved_document_id = target.document_id
        if resolved_document_id is None and resolved_book_slug:
            doc = self._document_repo.get_by_slug(resolved_book_slug)
            if doc is not None:
                resolved_document_id = doc.id

        resolved_art_mode, resolved_art_text = self._resolve_art_style_from_options(
            config.prompt_options
        )
        effective_prompt_options = config.prompt_options.copy_with(
            prompt_art_style_mode=resolved_art_mode,
            prompt_art_style_text=resolved_art_text,
        )
        effective_config = config.copy_with(prompt_options=effective_prompt_options)

        config_overrides = self._build_config_overrides(
            config=effective_config,
            resolved_book_slug=resolved_book_slug,
            resolved_book_path=None,
            images_for_scenes=None,
            resolved_art_mode=resolved_art_mode,
            resolved_art_text=resolved_art_text,
            extra={
                "source_image_id": str(target.source_image_id),
                "source_prompt_id": str(target.source_prompt_id),
                "custom_prompt_text": target.custom_prompt_text,
            },
        )

        context = PipelineExecutionContext(
            document_id=resolved_document_id,
            book_slug=resolved_book_slug,
        )

        run = self._run_repo.create(
            data={
                "document_id": resolved_document_id,
                "book_slug": resolved_book_slug,
                "status": "pending",
                "current_stage": "pending",
                "config_overrides": config_overrides,
            },
            commit=True,
            refresh=True,
        )

        return PreparedPipelineExecution(
            run_id=run.id,
            config=effective_config,
            config_overrides=config_overrides,
            context=context,
        )

    # -- Shared resolution helpers ----------------------------------------

    def _resolve_document_identity(
        self,
        *,
        document_id: UUID | None,
        book_slug: str | None,
        book_path: str | None,
    ) -> tuple[Document | None, str | None, str | None]:
        """Resolve document, book_slug, and book_path from target fields."""
        resolved_document: Document | None = None
        resolved_book_slug = book_slug
        resolved_book_path = book_path

        if document_id is not None:
            resolved_document = self._document_repo.get(document_id)
            if resolved_document is None:
                raise DocumentNotFoundError()
            if not resolved_book_slug:
                resolved_book_slug = resolved_document.slug
            if not resolved_book_path and resolved_document.source_path:
                resolved_book_path = resolved_document.source_path

        if resolved_document is None and resolved_book_slug:
            resolved_document = self._document_repo.get_by_slug(resolved_book_slug)

        return resolved_document, resolved_book_slug, resolved_book_path

    def _resolve_extraction_resume(
        self,
        book_slug: str,
    ) -> tuple[int | None, int | None]:
        """Return (resume_from_chapter, resume_from_chunk) for partial extraction."""
        existing_scenes = self._scene_repo.list_for_book(book_slug)
        if not existing_scenes:
            return None, None

        last_scene = max(
            existing_scenes,
            key=lambda s: (
                s.chapter_number or -1,
                s.chunk_index if s.chunk_index is not None else -1,
                s.scene_number or -1,
            ),
        )
        resume_chapter: int | None = None
        resume_chunk: int | None = None
        if last_scene.chapter_number is not None:
            resume_chapter = int(last_scene.chapter_number)
        if last_scene.chunk_index is not None:
            resume_chunk = int(last_scene.chunk_index)
        elif resume_chapter is not None:
            resume_chunk = -1
        return resume_chapter, resume_chunk

    def _resolve_ranking_resume(
        self,
        book_slug: str,
    ) -> tuple[list[UUID] | None, UUID | None]:
        """Return (remaining scene IDs, first unranked scene ID) for partial ranking."""
        from app.services.scene_ranking.scene_ranking_service import (
            SceneRankingConfig,
            SceneRankingService,
        )

        scenes = self._scene_repo.list_for_book(book_slug)
        if not scenes:
            return None, None

        ranking_config = SceneRankingConfig()
        ranking_service = SceneRankingService(self._session, config=ranking_config)
        ranking_repo = SceneRankingRepository(self._session)

        weight_hash = ranking_service.effective_weight_hash()
        ranked_ids = ranking_repo.list_ranked_scene_ids_for_book(
            book_slug=book_slug,
            model_name=ranking_config.model_name,
            prompt_version=ranking_config.prompt_version,
            weight_config_hash=weight_hash,
        )

        remaining = [s.id for s in scenes if s.id not in ranked_ids]
        if not remaining:
            return None, None

        return remaining, remaining[0]

    def _resolve_art_style_from_options(
        self,
        prompt_options: Any,
    ) -> tuple[str, str | None]:
        """Resolve art style mode/text from prompt options + app settings."""
        settings = self._settings_repo.get_global()
        default_mode = (
            settings.default_prompt_art_style_mode
            if settings is not None
            else PROMPT_ART_STYLE_MODE_RANDOM_MIX
        )
        default_text = (
            settings.default_prompt_art_style_text if settings is not None else None
        )

        resolved_mode = prompt_options.prompt_art_style_mode or default_mode
        resolved_text = (
            prompt_options.prompt_art_style_text
            if prompt_options.prompt_art_style_text is not None
            else default_text
        )

        try:
            return coerce_prompt_art_style_selection(
                mode=resolved_mode,
                text=resolved_text,
            )
        except ValueError as exc:
            raise PipelineValidationError(str(exc), status_code=422) from exc

    def _build_config_overrides(
        self,
        *,
        config: PipelineExecutionConfig,
        resolved_book_slug: str | None,
        resolved_book_path: str | None,
        images_for_scenes: int | None,
        resolved_art_mode: str,
        resolved_art_text: str | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the config_overrides dict persisted on the PipelineRun."""
        overrides: dict[str, Any] = {}
        if resolved_book_slug is not None:
            overrides["resolved_book_slug"] = resolved_book_slug
        if resolved_book_path is not None:
            overrides["resolved_book_path"] = resolved_book_path

        stages = config.stages
        overrides["skip_extraction"] = not stages.run_extraction
        overrides["skip_ranking"] = not stages.run_ranking
        overrides["skip_prompts"] = not stages.run_prompt_generation

        if images_for_scenes is not None:
            overrides["resolved_images_for_scenes"] = images_for_scenes
        overrides["resolved_prompt_art_style_mode"] = resolved_art_mode
        overrides["resolved_prompt_art_style_text"] = resolved_art_text

        if extra:
            overrides.update(extra)

        return overrides

    # ------------------------------------------------------------------
    # Legacy preparation (used by existing route + CLI until Phase 5)
    # ------------------------------------------------------------------

    def _build_run_namespace(
        self,
        *,
        launch_request: PipelineRunStartRequest,
        book_slug: str,
        book_path: str | None,
        images_for_scenes: int,
        skip_extraction: bool,
        skip_ranking: bool,
        prompt_art_style_mode: str,
        prompt_art_style_text: str | None,
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
            skip_ranking=skip_ranking,
            skip_prompts=launch_request.skip_prompts,
            prompt_art_style_mode=prompt_art_style_mode,
            prompt_art_style_text=prompt_art_style_text,
            quality=launch_request.quality,
            style=launch_request.style,
            aspect_ratio=launch_request.aspect_ratio,
            mode=launch_request.mode,
            poll_timeout=launch_request.poll_timeout,
            poll_interval=launch_request.poll_interval,
            dry_run=launch_request.dry_run,
            verbose=False,
        )

    def _resolve_default_scenes_per_run(self) -> int:
        return _resolve_default_scenes_per_run()

    def _resolve_prompt_art_style(
        self,
        launch_request: PipelineRunStartRequest,
    ) -> tuple[str, str | None]:
        settings = self._settings_repo.get_global()
        default_mode = (
            settings.default_prompt_art_style_mode
            if settings is not None
            else PROMPT_ART_STYLE_MODE_RANDOM_MIX
        )
        default_text = (
            settings.default_prompt_art_style_text if settings is not None else None
        )

        resolved_mode = launch_request.prompt_art_style_mode or default_mode
        resolved_text = (
            launch_request.prompt_art_style_text
            if "prompt_art_style_text" in launch_request.model_fields_set
            else default_text
        )

        try:
            return coerce_prompt_art_style_selection(
                mode=resolved_mode,
                text=resolved_text,
            )
        except ValueError as exc:
            raise PipelineValidationError(str(exc), status_code=422) from exc

    def _source_path_exists(self, source_path: str | None) -> bool:
        if not source_path:
            return False
        try:
            resolved = self._book_service.resolve_book_path(source_path)
        except Exception:
            return False
        return resolved.exists()
