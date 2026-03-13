"""Service-layer orchestration for launching pipeline runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    coerce_prompt_art_style_selection,
)
from app.repositories import (
    AppSettingsRepository,
    DocumentRepository,
    PipelineRunRepository,
    SceneExtractionRepository,
)
from app.schemas import PipelineRunStartRequest
from app.services.books.book_content_service import BookContentService
from app.services.image_gen_cli import _resolve_default_scenes_per_run
from models.document import Document
from models.pipeline_run import PipelineRun

from .exceptions import (
    DocumentNotFoundError,
    PipelineValidationError,
    SourceDocumentMissingError,
)


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

        if not resolved_book_slug:
            raise PipelineValidationError(
                "book_slug is required when document_id is not provided"
            )

        should_skip_extraction = launch_request.skip_extraction
        has_existing_extractions = bool(
            self._scene_repo.list_for_book(resolved_book_slug)
        )
        source_path_exists = self._source_path_exists(resolved_book_path)

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
            prompt_art_style_mode=resolved_prompt_art_style_mode,
            prompt_art_style_text=resolved_prompt_art_style_text,
        )

        config_overrides = launch_request.model_dump(exclude_none=True, mode="json")
        config_overrides["resolved_book_slug"] = resolved_book_slug
        if resolved_book_path is not None:
            config_overrides["resolved_book_path"] = resolved_book_path
        config_overrides["skip_extraction"] = should_skip_extraction
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

    def _build_run_namespace(
        self,
        *,
        launch_request: PipelineRunStartRequest,
        book_slug: str,
        book_path: str | None,
        images_for_scenes: int,
        skip_extraction: bool,
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
            skip_ranking=launch_request.skip_ranking,
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
