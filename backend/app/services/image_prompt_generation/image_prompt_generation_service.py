"""Service for generating structured image prompts from book scenes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
    PromptArtStyleMode,
    normalize_prompt_art_style_text,
)
from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.art_style import ArtStyleService
from app.services.books import BookContentService
from app.services.langchain import gemini_api, openai_api
from app.services.langchain.model_routing import LLMRoutingConfig, resolve_llm_model
from app.services.prompt_metadata import (
    PromptMetadataConfig,
    PromptMetadataGenerationService,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

from .context_builder import SceneContextBuilder
from .core import StyleSampler
from .models import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationServiceError,
    ImagePromptPreview,
    PromptArtStylePlan,
)
from .prompt_builder import PromptBuilder
from .strategies import PromptStrategyRegistry
from .variant_processing import VariantProcessor

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

REMIX_VARIANTS_COUNT = 2


class ImagePromptGenerationService:
    """Generate structured image prompts for scenes using LLM (Gemini or OpenAI)."""

    _system_instruction = (
        "Respond only with strict JSON matching the requested array schema. "
        "Do not include commentary, markdown fences, or trailing text."
    )
    _remix_system_instruction = (
        "You are refining existing DALLE3 prompts. Respond only with valid JSON. "
        "Do not include commentary, markdown, or explanations."
    )

    def __init__(
        self,
        session: Session,
        config: ImagePromptGenerationConfig | None = None,
    ) -> None:
        self._session = session
        self._config = config or ImagePromptGenerationConfig()
        self._scene_repo = SceneExtractionRepository(session)
        self._prompt_repo = ImagePromptRepository(session)
        self._ranking_repo = SceneRankingRepository(session)
        self._art_style_service = ArtStyleService(session)
        self._book_service = BookContentService()
        self._context_builder = SceneContextBuilder(self._book_service)
        self._prompt_builder = PromptBuilder(style_sampler=self._build_style_sampler())

    def _build_style_sampler(self) -> StyleSampler:
        """Build a style sampler using active DB catalog values."""
        recommended, other = self._art_style_service.get_sampling_distribution()
        return StyleSampler(
            recommended_styles=tuple(recommended),
            other_styles=tuple(other),
        )

    def _resolve_prompt_art_style_plan(
        self,
        *,
        config: ImagePromptGenerationConfig,
    ) -> PromptArtStylePlan:
        """Resolve prompt art-style behavior for prompt assembly."""

        if config.prompt_art_style_mode == PROMPT_ART_STYLE_MODE_SINGLE_STYLE:
            return PromptArtStylePlan(
                mode=config.prompt_art_style_mode,
                style_text=config.prompt_art_style_text,
            )

        sampled_styles = self._prompt_builder.sample_styles(config.variants_count)
        if not sampled_styles:
            raise ImagePromptGenerationServiceError(
                "Art style catalog is empty. Add at least one active style in Settings."
            )
        return PromptArtStylePlan(
            mode=cast(PromptArtStyleMode, PROMPT_ART_STYLE_MODE_RANDOM_MIX),
            sampled_styles=sampled_styles,
        )

    def _get_variant_processor(self, target_provider: str) -> VariantProcessor:
        """Get a VariantProcessor configured with the provider's aspect ratios."""
        strategy = PromptStrategyRegistry.get(target_provider)
        return VariantProcessor(
            allowed_aspect_ratios=strategy.get_supported_aspect_ratios()
        )

    async def generate_for_scene(
        self,
        scene: SceneExtraction | UUID,
        *,
        prompt_version: str | None = None,
        variants_count: int | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
        pipeline_run_id: UUID | None = None,
    ) -> list[ImagePrompt] | list[ImagePromptPreview]:
        target_scene = self._resolve_scene(scene)
        config = self._resolve_config(
            prompt_version=prompt_version,
            variants_count=variants_count,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            overwrite=overwrite,
            dry_run=dry_run,
            metadata=metadata,
        )
        try:
            config = self._resolve_active_llm_config(config)
        except Exception as exc:
            raise ImagePromptGenerationServiceError(str(exc)) from exc

        # Check for blocked content warnings
        if config.skip_scenes_with_warnings and self._scene_has_blocked_warnings(
            target_scene, config
        ):
            problematic_warnings = self._get_problematic_warnings(target_scene, config)
            logger.info(
                "Skipping scene %s due to content warnings: %s",
                target_scene.id,
                ", ".join(problematic_warnings),
            )
            return []

        # Determine final variant count (may override config based on ranking recommendation)
        final_count, count_rationale = self._determine_variant_count(
            target_scene, config
        )

        # Override config with final determination
        merged_metadata = dict(config.metadata)
        merged_metadata["variant_count_source"] = count_rationale
        config = config.copy_with(
            variants_count=final_count,
            metadata=merged_metadata,
        )

        if config.variants_count <= 0:
            raise ImagePromptGenerationServiceError("variants_count must be positive")

        if config.allow_overwrite:
            variant_indices = self._determine_next_variant_indices_for_scene(
                target_scene.id,
                config.variants_count,
            )
        else:
            variant_indices = list(range(config.variants_count))

        existing: list[ImagePrompt] = []
        if not config.allow_overwrite:
            existing = self._prompt_repo.get_latest_set_for_scene(
                target_scene.id, config.model_name, config.prompt_version
            )
            if existing:
                if self._existing_prompt_set_matches_config(existing, config):
                    return existing
                logger.info(
                    "Regenerating prompt set for scene %s because the stored prompts "
                    "do not match the requested art-style selection or target provider.",
                    target_scene.id,
                )

        context_window, context_text = self._context_builder.build_scene_context(
            target_scene, config
        )
        style_plan = self._resolve_prompt_art_style_plan(config=config)
        prompt, sampled_styles = self._build_prompt(
            scene=target_scene,
            config=config,
            context_text=context_text,
            context_window=context_window,
            style_plan=style_plan,
        )
        raw_payload, llm_request_id, execution_time_ms = await self._invoke_llm(
            prompt=prompt,
            config=config,
        )
        variant_processor = self._get_variant_processor(config.target_provider)
        variants = variant_processor.extract_variants(raw_payload, config)
        if len(variants) != len(variant_indices):
            raise ImagePromptGenerationServiceError(
                "Variant count mismatch while assigning variant indices"
            )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        service_payload = {
            "prompt_version": config.prompt_version,
            "model_name": config.model_name,
            "model_vendor": config.model_vendor,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "variants_count": config.variants_count,
            "prompt_hash": prompt_hash,
            "target_provider": config.target_provider,
            "context_window": dict(context_window),
            "cheatsheet_path": config.include_cheatsheet_path,
            "prompt_art_style": style_plan.to_metadata(),
            "prompt_art_style_mode": style_plan.mode,
            "prompt_art_style_text": style_plan.style_text,
        }
        if sampled_styles:
            service_payload["sampled_styles"] = sampled_styles
        if config.metadata:
            service_payload["run_metadata"] = dict(config.metadata)
        raw_bundle = {
            "response": raw_payload,
            "service": service_payload,
        }
        records = variant_processor.build_records(
            scene=target_scene,
            config=config,
            variants=variants,
            variant_indices=variant_indices,
            context_window=context_window,
            raw_payload=raw_bundle,
            llm_request_id=llm_request_id,
            execution_time_ms=execution_time_ms,
        )
        if pipeline_run_id is not None:
            for record in records:
                record["pipeline_run_id"] = pipeline_run_id

        if config.dry_run:
            preview_prompts = variant_processor.instantiate_prompts_from_records(
                records
            )
            metadata_results = await self._run_metadata_generation(
                preview_prompts,
                dry_run=True,
                autocommit=False,
            )
            previews: list[ImagePromptPreview] = []
            for index, record in enumerate(records):
                preview_payload = dict(record["raw_response"])
                preview_payload["prompt"] = prompt
                preview_payload["context_excerpt"] = context_text
                preview = ImagePromptPreview(
                    scene_extraction_id=record["scene_extraction_id"],
                    variant_index=record["variant_index"],
                    title=record["title"],
                    flavour_text=None,
                    prompt_text=record["prompt_text"],
                    style_tags=record["style_tags"],
                    attributes=record["attributes"],
                    prompt_version=record["prompt_version"],
                    model_name=record["model_name"],
                    model_vendor=record["model_vendor"],
                    context_window=record["context_window"],
                    raw_response=preview_payload,
                    temperature=record["temperature"],
                    max_output_tokens=record["max_output_tokens"],
                    execution_time_ms=record["execution_time_ms"],
                    llm_request_id=record["llm_request_id"],
                )
                if metadata_results and index < len(metadata_results):
                    metadata_payload = metadata_results[index]
                    if isinstance(metadata_payload, dict):
                        preview.title = metadata_payload.get("title") or preview.title
                        preview.flavour_text = metadata_payload.get("flavour_text")
                previews.append(preview)
            return previews

        should_replace_existing = config.allow_overwrite or (
            not config.dry_run and not config.allow_overwrite and bool(existing)
        )

        if should_replace_existing:
            deleted = self._prompt_repo.delete_for_scene(
                target_scene.id,
                prompt_version=config.prompt_version,
                model_name=config.model_name,
                commit=False,
            )
            if deleted:
                logger.info(
                    "Deleted %s existing image prompt variants for scene %s",
                    deleted,
                    target_scene.id,
                )

        try:
            created = self._prompt_repo.bulk_create(
                records,
                commit=config.autocommit,
                refresh=True,
            )
            if not config.autocommit:
                self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            if self._is_duplicate_prompt_variant_error(exc):
                logger.warning(
                    "Existing image prompt variants detected for scene %s "
                    "(model=%s, version=%s); returning stored variants instead.",
                    target_scene.id,
                    config.model_name,
                    config.prompt_version,
                )
                existing_prompts = self._prompt_repo.get_latest_set_for_scene(
                    target_scene.id,
                    config.model_name,
                    config.prompt_version,
                )
                if existing_prompts and self._existing_prompt_set_matches_config(
                    existing_prompts, config
                ):
                    return existing_prompts
            raise
        await self._run_metadata_generation(
            created,
            dry_run=False,
            autocommit=config.autocommit,
        )
        return created

    def render_prompt_template(
        self,
        scene: SceneExtraction | UUID,
        *,
        prompt_version: str | None = None,
        variants_count: int | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[str, ImagePromptGenerationConfig, Mapping[str, Any], str, list[str]]:
        """
        Build the full prompt text exactly as it will be sent to the LLM.

        Returns a tuple of
        (prompt_text, resolved_config, context_window, context_excerpt, sampled_styles).
        """
        target_scene = self._resolve_scene(scene)
        config = self._resolve_config(
            prompt_version=prompt_version,
            variants_count=variants_count,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            overwrite=None,
            dry_run=None,
            metadata=metadata,
        )

        if config.skip_scenes_with_warnings and self._scene_has_blocked_warnings(
            target_scene, config
        ):
            problematic_warnings = self._get_problematic_warnings(target_scene, config)
            raise ImagePromptGenerationServiceError(
                "Scene has blocked warnings: " + ", ".join(problematic_warnings)
            )

        final_count, count_rationale = self._determine_variant_count(
            target_scene, config
        )
        merged_metadata = dict(config.metadata)
        merged_metadata["variant_count_source"] = count_rationale
        resolved_config = config.copy_with(
            variants_count=final_count,
            metadata=merged_metadata,
        )

        context_window, context_text = self._context_builder.build_scene_context(
            target_scene, resolved_config
        )
        style_plan = self._resolve_prompt_art_style_plan(config=resolved_config)
        prompt, sampled_styles = self._build_prompt(
            scene=target_scene,
            config=resolved_config,
            context_text=context_text,
            context_window=context_window,
            style_plan=style_plan,
        )
        return prompt, resolved_config, context_window, context_text, sampled_styles

    async def generate_for_scenes(
        self,
        scenes: Sequence[SceneExtraction | UUID],
        *,
        pipeline_run_id: UUID | None = None,
        **overrides: Any,
    ) -> list[list[ImagePrompt] | list[ImagePromptPreview] | None]:
        results: list[list[ImagePrompt] | list[ImagePromptPreview] | None] = []
        for scene in scenes:
            try:
                result = await self.generate_for_scene(
                    scene, pipeline_run_id=pipeline_run_id, **overrides
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                if self._config.fail_on_error or overrides.get("fail_on_error"):
                    raise
                logger.error("Image prompt generation failed for %s: %s", scene, exc)
                results.append(None)
                continue
            results.append(result)
        return results

    async def generate_for_book(
        self,
        book_slug: str,
        *,
        scene_filter: Mapping[str, Any] | None = None,
        ranked_only: bool = False,
        top_n: int | None = None,
        pipeline_run_id: UUID | None = None,
        **overrides: Any,
    ) -> list[list[ImagePrompt] | list[ImagePromptPreview] | None]:
        scene_filter = scene_filter or {}
        chapter_number = scene_filter.get("chapter_number")
        candidate_scenes = self._scene_repo.list_for_book(
            book_slug, chapter_number=chapter_number
        )
        if ranked_only:
            candidate_scenes = self._filter_ranked_scenes(
                candidate_scenes,
                top_n=top_n,
            )
        elif top_n is not None:
            candidate_scenes = candidate_scenes[:top_n]
        if not candidate_scenes:
            return []
        return await self.generate_for_scenes(
            candidate_scenes, pipeline_run_id=pipeline_run_id, **overrides
        )

    async def generate_remix_variants(
        self,
        source_prompt: ImagePrompt | UUID,
        *,
        variants_count: int = REMIX_VARIANTS_COUNT,
        dry_run: bool = False,
        pipeline_run_id: UUID | None = None,
    ) -> list[ImagePrompt] | list[ImagePromptPreview]:
        if variants_count <= 0:
            raise ImagePromptGenerationServiceError(
                "variants_count must be positive for remix generation"
            )

        prompt_record = self._resolve_prompt(source_prompt)
        scene = self._scene_repo.get(prompt_record.scene_extraction_id)
        if scene is None:
            raise ImagePromptGenerationServiceError(
                f"Scene {prompt_record.scene_extraction_id} for prompt {prompt_record.id} was not found"
            )

        metadata = dict(self._config.metadata)
        modes = metadata.get("modes")
        if isinstance(modes, list):
            modes_list = list(modes)
        elif modes is None:
            modes_list = []
        else:
            modes_list = [modes]
        if "remix" not in modes_list:
            modes_list.append("remix")
        metadata["modes"] = modes_list
        metadata["remix_source_prompt_id"] = str(prompt_record.id)

        config = self._config.copy_with(
            variants_count=variants_count,
            temperature=0.7,
            use_ranking_recommendation=False,
            dry_run=dry_run,
            metadata=metadata,
        )
        try:
            config = self._resolve_active_llm_config(config)
        except Exception as exc:
            raise ImagePromptGenerationServiceError(str(exc)) from exc

        variant_indices = self._determine_next_variant_indices_for_scene(
            scene.id, variants_count
        )

        remix_prompt = self._build_remix_prompt(
            source_prompt=prompt_record,
            variants_count=variants_count,
        )
        raw_payload, llm_request_id, execution_time_ms = await self._invoke_llm(
            prompt=remix_prompt,
            config=config,
            system_instruction=self._remix_system_instruction,
        )
        target_provider = prompt_record.target_provider or config.target_provider
        variant_processor = self._get_variant_processor(target_provider)
        variants = variant_processor.extract_variants(raw_payload, config)

        service_payload = {
            "mode": "remix",
            "source_prompt_id": str(prompt_record.id),
            "variants_count": variants_count,
            "model_name": config.model_name,
            "model_vendor": config.model_vendor,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
        }
        if config.metadata:
            service_payload["run_metadata"] = dict(config.metadata)

        remix_metadata = {
            "remix_source_prompt_id": str(prompt_record.id),
            "remix_generation_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        raw_bundle = {
            "response": raw_payload,
            "service": service_payload,
            "remix": remix_metadata,
        }

        records: list[dict[str, Any]] = []
        for position, variant in enumerate(variants):
            variant_index = variant_indices[position]
            style_tags = list(variant.style_tags) if variant.style_tags else None
            attributes = dict(variant.attributes)
            records.append(
                {
                    "scene_extraction_id": prompt_record.scene_extraction_id,
                    "model_vendor": config.model_vendor,
                    "model_name": config.model_name,
                    "prompt_version": prompt_record.prompt_version,
                    "target_provider": prompt_record.target_provider
                    or config.target_provider,
                    "variant_index": variant_index,
                    "title": variant.title,
                    "prompt_text": variant.prompt_text,
                    "style_tags": style_tags,
                    "attributes": attributes,
                    "context_window": dict(prompt_record.context_window),
                    "raw_response": raw_bundle,
                    "temperature": config.temperature,
                    "max_output_tokens": config.max_output_tokens,
                    "llm_request_id": llm_request_id,
                    "execution_time_ms": execution_time_ms,
                }
            )
        if pipeline_run_id is not None:
            for record in records:
                record["pipeline_run_id"] = pipeline_run_id

        if config.dry_run:
            preview_prompts = variant_processor.instantiate_prompts_from_records(
                records
            )
            metadata_results = await self._run_metadata_generation(
                preview_prompts,
                dry_run=True,
                autocommit=False,
            )
            previews: list[ImagePromptPreview] = []
            for index, record in enumerate(records):
                preview_payload = dict(record["raw_response"])
                preview_payload["prompt"] = remix_prompt
                preview = ImagePromptPreview(
                    scene_extraction_id=record["scene_extraction_id"],
                    variant_index=record["variant_index"],
                    title=record["title"],
                    flavour_text=None,
                    prompt_text=record["prompt_text"],
                    style_tags=record["style_tags"],
                    attributes=record["attributes"],
                    prompt_version=record["prompt_version"],
                    model_name=record["model_name"],
                    model_vendor=record["model_vendor"],
                    context_window=record["context_window"],
                    raw_response=preview_payload,
                    temperature=record["temperature"],
                    max_output_tokens=record["max_output_tokens"],
                    execution_time_ms=record["execution_time_ms"],
                    llm_request_id=record["llm_request_id"],
                )
                if metadata_results and index < len(metadata_results):
                    metadata_payload = metadata_results[index]
                    if isinstance(metadata_payload, dict):
                        preview.title = metadata_payload.get("title") or preview.title
                        preview.flavour_text = metadata_payload.get("flavour_text")
                previews.append(preview)
            return previews

        created = self._prompt_repo.bulk_create(
            records,
            commit=config.autocommit,
            refresh=True,
        )
        if not config.autocommit:
            self._session.flush()
        await self._run_metadata_generation(
            created,
            dry_run=False,
            autocommit=config.autocommit,
        )
        return created

    async def create_custom_remix_variant(
        self,
        source_prompt: ImagePrompt | UUID,
        custom_prompt_text: str,
        *,
        dry_run: bool = False,
        pipeline_run_id: UUID | None = None,
    ) -> ImagePrompt | ImagePromptPreview:
        prompt_record = self._resolve_prompt(source_prompt)

        if not custom_prompt_text or not custom_prompt_text.strip():
            raise ImagePromptGenerationServiceError(
                "Custom prompt text must not be empty"
            )

        scene = self._scene_repo.get(prompt_record.scene_extraction_id)
        if scene is None:
            raise ImagePromptGenerationServiceError(
                f"Scene {prompt_record.scene_extraction_id} for prompt {prompt_record.id} was not found"
            )

        variant_index = self._determine_next_variant_indices_for_scene(scene.id, 1)[0]
        timestamp = datetime.now(timezone.utc).isoformat()

        record: dict[str, Any] = {
            "scene_extraction_id": prompt_record.scene_extraction_id,
            "model_vendor": prompt_record.model_vendor,
            "model_name": prompt_record.model_name,
            "prompt_version": prompt_record.prompt_version,
            "target_provider": prompt_record.target_provider
            or self._config.target_provider,
            "variant_index": variant_index,
            "title": None,
            "flavour_text": None,
            "prompt_text": custom_prompt_text,
            "negative_prompt": prompt_record.negative_prompt,
            "style_tags": list(prompt_record.style_tags)
            if prompt_record.style_tags
            else None,
            "attributes": dict(prompt_record.attributes),
            "notes": None,
            "context_window": dict(prompt_record.context_window),
            "raw_response": {
                "custom_remix": True,
                "custom_remix_source_prompt_id": str(prompt_record.id),
                "custom_remix_timestamp": timestamp,
                "custom_prompt_text": custom_prompt_text,
            },
            "temperature": (
                prompt_record.temperature
                if prompt_record.temperature is not None
                else self._config.temperature
            ),
            "max_output_tokens": prompt_record.max_output_tokens,
            "llm_request_id": None,
            "execution_time_ms": 0,
        }
        if pipeline_run_id is not None:
            record["pipeline_run_id"] = pipeline_run_id

        if dry_run:
            target_provider = (
                prompt_record.target_provider or self._config.target_provider
            )
            variant_processor = self._get_variant_processor(target_provider)
            preview_prompts = variant_processor.instantiate_prompts_from_records(
                [record]
            )
            metadata_results = await self._run_metadata_generation(
                preview_prompts,
                dry_run=True,
                autocommit=False,
            )
            preview_prompt = preview_prompts[0]
            preview = ImagePromptPreview(
                scene_extraction_id=preview_prompt.scene_extraction_id,
                variant_index=preview_prompt.variant_index,
                title=preview_prompt.title,
                flavour_text=preview_prompt.flavour_text,
                prompt_text=preview_prompt.prompt_text,
                style_tags=preview_prompt.style_tags,
                attributes=preview_prompt.attributes,
                prompt_version=preview_prompt.prompt_version,
                model_name=preview_prompt.model_name,
                model_vendor=preview_prompt.model_vendor,
                context_window=preview_prompt.context_window,
                raw_response=preview_prompt.raw_response,
                temperature=float(preview_prompt.temperature or 0.0),
                max_output_tokens=preview_prompt.max_output_tokens,
                execution_time_ms=preview_prompt.execution_time_ms
                if preview_prompt.execution_time_ms is not None
                else 0,
                llm_request_id=preview_prompt.llm_request_id,
            )
            if metadata_results:
                metadata_payload = metadata_results[0]
                if isinstance(metadata_payload, ImagePrompt):
                    preview.title = metadata_payload.title
                    preview.flavour_text = metadata_payload.flavour_text
                elif isinstance(metadata_payload, dict):
                    preview.title = metadata_payload.get("title") or preview.title
                    preview.flavour_text = metadata_payload.get("flavour_text")
            logger.info(
                "Custom remix preview generated for prompt %s (variant_index=%s)",
                prompt_record.id,
                variant_index,
            )
            return preview

        created = self._prompt_repo.bulk_create(
            [record],
            commit=self._config.autocommit,
            refresh=True,
        )
        if not self._config.autocommit:
            self._session.flush()
        await self._run_metadata_generation(
            created,
            dry_run=False,
            autocommit=self._config.autocommit,
        )
        prompt = created[0]
        logger.info(
            "Custom remix variant %s created for prompt %s (variant_index=%s, text_length=%s)",
            prompt.id,
            prompt_record.id,
            prompt.variant_index,
            len(custom_prompt_text),
        )
        return prompt

    def _resolve_scene(self, scene: SceneExtraction | UUID) -> SceneExtraction:
        if isinstance(scene, SceneExtraction):
            return scene
        resolved = self._scene_repo.get(scene)
        if resolved is None:
            raise ImagePromptGenerationServiceError(f"Scene {scene} was not found")
        return resolved

    def _resolve_prompt(self, prompt: ImagePrompt | UUID) -> ImagePrompt:
        if isinstance(prompt, ImagePrompt):
            return prompt
        resolved = self._prompt_repo.get(prompt)
        if resolved is None:
            raise ImagePromptGenerationServiceError(f"Prompt {prompt} was not found")
        return resolved

    def _resolve_config(
        self,
        *,
        prompt_version: str | None,
        variants_count: int | None,
        temperature: float | None,
        max_output_tokens: int | None,
        overwrite: bool | None,
        dry_run: bool | None,
        metadata: Mapping[str, Any] | None,
    ) -> ImagePromptGenerationConfig:
        overrides: dict[str, Any] = {}
        if prompt_version is not None:
            overrides["prompt_version"] = prompt_version
        if variants_count is not None:
            # Explicit count provided = disable recommendation
            overrides["variants_count"] = variants_count
            overrides["use_ranking_recommendation"] = False
        if temperature is not None:
            overrides["temperature"] = temperature
        if max_output_tokens is not None:
            overrides["max_output_tokens"] = max_output_tokens
        if overwrite is not None:
            overrides["allow_overwrite"] = overwrite
        if dry_run is not None:
            overrides["dry_run"] = dry_run
        if metadata is not None:
            overrides["metadata"] = dict(metadata)
        return self._config.copy_with(**overrides)

    def _determine_variant_count(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> tuple[int, str]:
        """
        Determine how many variants to generate, returning (count, rationale).

        Priority:
        1. Config variants_count if use_ranking_recommendation=False
        2. Scene ranking recommendation if available
        3. Config variants_count as fallback
        """
        if not config.use_ranking_recommendation:
            return config.variants_count, "config_override"

        # Query latest ranking for this scene
        ranking = self._ranking_repo.get_latest_for_scene(scene.id)

        if ranking and ranking.recommended_prompt_count is not None:
            count = ranking.recommended_prompt_count
            rationale = f"ranking_recommendation (complexity: {ranking.complexity_rationale or 'N/A'})"
            logger.info(
                "Using ranking recommendation for scene %s: %d variants (rationale: %s)",
                scene.id,
                count,
                ranking.complexity_rationale or "N/A",
            )
            return count, rationale

        # Fallback to config
        logger.info(
            "No ranking recommendation found for scene %s, using config default: %d",
            scene.id,
            config.variants_count,
        )
        return config.variants_count, "config_default"

    def _resolve_active_llm_config(
        self,
        config: ImagePromptGenerationConfig,
    ) -> ImagePromptGenerationConfig:
        resolved = resolve_llm_model(
            LLMRoutingConfig(
                default_vendor=config.model_vendor,
                default_model=config.model_name,
                backup_vendor=config.backup_model_vendor,
                backup_model=config.backup_model_name,
            ),
            context="ImagePromptGenerationService.generate",
        )
        metadata = dict(config.metadata)
        metadata.update(
            {
                "llm_default_vendor": config.model_vendor,
                "llm_default_model": config.model_name,
                "llm_backup_vendor": config.backup_model_vendor,
                "llm_backup_model": config.backup_model_name,
                "llm_selected_vendor": resolved.vendor,
                "llm_selected_model": resolved.model,
                "llm_used_backup_model": resolved.used_backup,
            }
        )
        return config.copy_with(
            model_vendor=resolved.vendor,
            model_name=resolved.model,
            metadata=metadata,
        )

    def _build_prompt(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        context_text: str,
        context_window: Mapping[str, Any],
        style_plan: PromptArtStylePlan,
    ) -> tuple[str, list[str]]:
        prompt = self._prompt_builder.build_prompt(
            scene=scene,
            config=config,
            context_text=context_text,
            context_window=context_window,
            style_plan=style_plan,
            target_provider=config.target_provider,
        )
        return prompt, list(style_plan.sampled_styles)

    def _existing_prompt_set_matches_config(
        self,
        prompts: Sequence[ImagePrompt],
        config: ImagePromptGenerationConfig,
    ) -> bool:
        """Return True when stored prompts are safe to reuse for the requested config."""

        if len(prompts) != config.variants_count:
            return False

        expected_style_text = normalize_prompt_art_style_text(
            config.prompt_art_style_text
        )

        for prompt in prompts:
            service_payload = (
                prompt.raw_response.get("service")
                if isinstance(prompt.raw_response, dict)
                else None
            )
            if not isinstance(service_payload, dict):
                return False

            stored_mode = service_payload.get("prompt_art_style_mode")
            stored_text = normalize_prompt_art_style_text(
                service_payload.get("prompt_art_style_text")
                if isinstance(service_payload.get("prompt_art_style_text"), str)
                else None
            )
            stored_provider = prompt.target_provider or service_payload.get(
                "target_provider"
            )

            if stored_mode != config.prompt_art_style_mode:
                return False
            if stored_text != expected_style_text:
                return False
            if stored_provider != config.target_provider:
                return False

        return True

    def _build_remix_prompt(
        self,
        *,
        source_prompt: ImagePrompt,
        variants_count: int,
    ) -> str:
        original_prompt_text = source_prompt.prompt_text.strip()
        style_tags = source_prompt.style_tags or []
        serialized_attributes = json.dumps(
            source_prompt.attributes, indent=2, ensure_ascii=False
        )
        serialized_context = json.dumps(
            source_prompt.context_window, indent=2, ensure_ascii=False
        )
        schema_example = json.dumps(
            {
                "title": "string or null",
                "prompt_text": "string",
                "style_tags": ["string"],
                "attributes": source_prompt.attributes or {},
            },
            indent=2,
        )
        prompt_lines = [
            "You are an elite prompt remixer for DALLE3.",
            "Produce subtle, high-quality variations of an existing prompt without changing its core identity.",
            "",
            "## Remix Goals",
            "- Preserve the same subject, composition intent, and narrative focus as the original prompt.",
            "- Explore only small adjustments such as lighting, camera placement, atmosphere, or supporting sensory details.",
            "- Maintain the existing style family and artistic intent. Do not change genre, time period, or medium.",
            "- Change at most 2-3 elements per variant and ensure they remain coherent with the source.",
            "",
            f"Return exactly {variants_count} variants.",
            "",
            "## Original Prompt",
            original_prompt_text,
            "",
            "## Original Style Tags",
            ", ".join(style_tags) or "None provided",
            "",
            "## Original Attributes",
            serialized_attributes,
            "",
            "## Scene Context Window",
            serialized_context,
            "",
            "## Output Requirements",
            "- Respond with a JSON array of objects. No markdown, comments, or trailing text.",
            "- Each object must include: title (nullable), prompt_text, style_tags (list), attributes (object).",
            "- prompt_text must remain self-contained and ready for DALLE3.",
            "- style_tags should largely mirror the original list, adjusting only when necessary to reflect subtle changes.",
            "- attributes must update only the fields affected by the variation.",
            "- Ensure all entries are polished and free of placeholders.",
            "",
            f"The expected schema resembles: {schema_example}",
        ]
        return "\n".join(prompt_lines)

    async def _invoke_llm(
        self,
        *,
        prompt: str,
        config: ImagePromptGenerationConfig,
        system_instruction: str | None = None,
    ) -> tuple[Any, str | None, int]:
        attempts = max(config.retry_attempts, 0) + 1
        last_error: Exception | None = None
        use_gemini = config.model_vendor.lower() == "google"
        for attempt in range(1, attempts + 1):
            start_time = time.perf_counter()
            try:
                if use_gemini:
                    response = await gemini_api.json_output(
                        prompt=prompt,
                        system_instruction=system_instruction
                        or self._system_instruction,
                        model=config.model_name,
                        temperature=config.temperature,
                        max_tokens=config.max_output_tokens,
                    )
                else:
                    response = await openai_api.json_output(
                        prompt=prompt,
                        system_instruction=system_instruction
                        or self._system_instruction,
                        model=config.model_name,
                        temperature=config.temperature,
                        max_tokens=config.max_output_tokens,
                        force_json_object=False,
                    )
                execution_time_ms = int((time.perf_counter() - start_time) * 1000)
                llm_request_id = None
                if isinstance(response, dict):
                    maybe_id = response.get("request_id") or response.get("id")
                    if isinstance(maybe_id, str):
                        llm_request_id = maybe_id
                return response, llm_request_id, execution_time_ms
            except Exception as exc:  # pragma: no cover - retry path
                last_error = exc
                logger.warning(
                    "LLM prompt generation failed (attempt %s/%s, vendor=%s): %s",
                    attempt,
                    attempts,
                    config.model_vendor,
                    exc,
                )
                if attempt >= attempts:
                    break
                await asyncio.sleep(max(config.retry_backoff_seconds, 0))
        assert last_error is not None
        if config.fail_on_error:
            raise ImagePromptGenerationServiceError(
                f"LLM prompt generation failed: {last_error}"
            ) from last_error
        raise ImagePromptGenerationServiceError(
            "LLM prompt generation failed after retries"
        ) from last_error

    async def _run_metadata_generation(
        self,
        prompts: Sequence[ImagePrompt],
        *,
        dry_run: bool,
        autocommit: bool,
    ) -> list[ImagePrompt | dict[str, Any] | None] | None:
        if not prompts:
            return None
        service = PromptMetadataGenerationService(
            self._session,
            PromptMetadataConfig(
                fail_on_error=False,
                dry_run=dry_run,
            ),
        )
        try:
            results = await service.generate_metadata_for_prompts(
                prompts,
                overwrite=True,
                dry_run=dry_run,
            )
            if not dry_run and autocommit:
                self._session.commit()
            return results
        except Exception as exc:  # pragma: no cover - safety valve
            logger.warning(
                "Prompt metadata generation failed for %s prompts: %s",
                len(prompts),
                exc,
            )
            if not dry_run:
                self._session.rollback()
            return None

    @staticmethod
    def _is_duplicate_prompt_variant_error(error: IntegrityError) -> bool:
        """Return True when an IntegrityError is triggered by the unique variant constraint."""
        constraint_name = "uq_image_prompt_unique_variant"
        messages: list[str] = []
        if getattr(error, "orig", None) is not None:
            messages.append(str(error.orig))
        messages.append(str(error))
        return any(constraint_name in message for message in messages)

    def _determine_next_variant_indices_for_scene(
        self,
        scene_extraction_id: UUID,
        count: int,
    ) -> list[int]:
        prompts = self._prompt_repo.list_for_scene(
            scene_extraction_id,
            newest_first=False,
        )
        max_variant = -1
        for prompt in prompts:
            max_variant = max(max_variant, int(prompt.variant_index))
        return [max_variant + offset + 1 for offset in range(count)]

    def _scene_has_blocked_warnings(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> bool:
        """Check if scene has any blocked content warnings."""
        if not config.blocked_warnings:
            return False

        ranking = self._ranking_repo.get_latest_for_scene(scene.id)
        if not ranking or not ranking.warnings:
            return False

        # Check if any warning matches a blocked warning (case-insensitive)
        scene_warnings = {w.lower() for w in ranking.warnings}
        blocked_warnings = {w.lower() for w in config.blocked_warnings}
        return bool(scene_warnings & blocked_warnings)

    def _get_problematic_warnings(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> list[str]:
        """Get list of problematic warnings for a scene."""
        ranking = self._ranking_repo.get_latest_for_scene(scene.id)
        if not ranking or not ranking.warnings:
            return []

        scene_warnings = {w.lower(): w for w in ranking.warnings}
        blocked_warnings = {w.lower() for w in config.blocked_warnings}
        problematic = scene_warnings.keys() & blocked_warnings
        return [scene_warnings[w] for w in problematic]

    def _filter_ranked_scenes(
        self,
        scenes: Sequence[SceneExtraction],
        *,
        top_n: int | None,
    ) -> list[SceneExtraction]:
        if not scenes:
            return []
        book_slug = scenes[0].book_slug
        if top_n is not None and top_n > 0:
            rankings = self._ranking_repo.list_top_rankings_for_book(
                book_slug=book_slug,
                limit=top_n,
                include_scene=True,
            )
            ranked_scenes: list[SceneExtraction] = []
            seen_ids: set[UUID] = set()
            for ranking in rankings:
                scene = ranking.scene_extraction
                if scene is None:
                    scene = self._scene_repo.get(ranking.scene_extraction_id)
                if scene is None:
                    continue
                if scene.id in seen_ids:
                    continue
                ranked_scenes.append(scene)
                seen_ids.add(scene.id)
                if len(ranked_scenes) >= top_n:
                    break
            if ranked_scenes:
                return ranked_scenes
        filtered: list[SceneExtraction] = []
        for scene in scenes:
            scene_ranking = self._ranking_repo.get_latest_for_scene(scene.id)
            if scene_ranking is not None:
                filtered.append(scene)
        if top_n is not None and top_n > 0:
            filtered = filtered[:top_n]
        return filtered


__all__ = [
    "ImagePromptGenerationConfig",
    "ImagePromptGenerationService",
    "ImagePromptGenerationServiceError",
    "ImagePromptPreview",
]
