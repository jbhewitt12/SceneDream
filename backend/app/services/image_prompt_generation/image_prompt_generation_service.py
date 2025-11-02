"""Service for generating structured image prompts from book scenes."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.books import BookContentService, BookContentServiceError
from app.services.langchain import gemini_api
from app.services.prompt_metadata import (
    PromptMetadataConfig,
    PromptMetadataGenerationService,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CHEATSHEET_PATH = (
    "backend/app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md"
)
REMIX_VARIANTS_COUNT = 2


@dataclass(slots=True)
class ImagePromptGenerationConfig:
    """Runtime configuration for image prompt generation."""

    model_vendor: str = "google"
    model_name: str = "gemini-2.5-pro"
    prompt_version: str = "image-prompts-v1"
    variants_count: int = 4
    use_ranking_recommendation: bool = True
    temperature: float = 0.4
    max_output_tokens: int | None = 8192
    context_before: int = 3
    context_after: int = 1
    include_cheatsheet_path: str = DEFAULT_CHEATSHEET_PATH
    blocked_warnings: set[str] = field(
        default_factory=lambda: {"violence", "sexual", "drugs", "horror", "hate"}
    )
    skip_scenes_with_warnings: bool = True
    dry_run: bool = False
    allow_overwrite: bool = False
    autocommit: bool = True
    retry_attempts: int = 2
    retry_backoff_seconds: float = 2.0
    fail_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def copy_with(self, **overrides: Any) -> ImagePromptGenerationConfig:
        data = {
            "model_vendor": self.model_vendor,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "variants_count": self.variants_count,
            "use_ranking_recommendation": self.use_ranking_recommendation,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "include_cheatsheet_path": self.include_cheatsheet_path,
            "blocked_warnings": set(self.blocked_warnings),
            "skip_scenes_with_warnings": self.skip_scenes_with_warnings,
            "dry_run": self.dry_run,
            "allow_overwrite": self.allow_overwrite,
            "autocommit": self.autocommit,
            "retry_attempts": self.retry_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "fail_on_error": self.fail_on_error,
            "metadata": dict(self.metadata),
        }
        normalized_overrides: dict[str, Any] = {}
        for key, value in overrides.items():
            if key == "metadata":
                normalized_overrides[key] = dict(value) if value is not None else {}
            elif key == "blocked_warnings":
                normalized_overrides[key] = set(value) if value is not None else set()
            elif value is not None:
                normalized_overrides[key] = value
            elif key in {"max_output_tokens"}:
                normalized_overrides[key] = None
        data.update(normalized_overrides)
        return ImagePromptGenerationConfig(**data)


@dataclass(slots=True)
class ImagePromptPreview:
    """In-memory preview of generated image prompt variants."""

    scene_extraction_id: UUID
    variant_index: int
    title: str | None
    flavour_text: str | None
    prompt_text: str
    style_tags: list[str] | None
    attributes: dict[str, Any]
    prompt_version: str
    model_name: str
    model_vendor: str
    context_window: dict[str, Any]
    raw_response: dict[str, Any]
    temperature: float
    max_output_tokens: int | None
    execution_time_ms: int
    llm_request_id: str | None


class ImagePromptGenerationServiceError(RuntimeError):
    """Raised when image prompt generation fails under strict settings."""


@dataclass(slots=True)
class _ChapterContext:
    number: int
    title: str
    paragraphs: list[str]
    source_name: str


class _VariantModel(BaseModel):
    """Validate the structure returned by the LLM."""

    title: str | None = None
    prompt_text: str
    style_tags: list[str] | None = None
    attributes: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> _VariantModel:
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover - raised with context
            raise ImagePromptGenerationServiceError(
                "LLM response did not match the required variant schema"
            ) from exc


class ImagePromptGenerationService:
    """Generate structured image prompts for scenes using Gemini."""

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
        self._cheatsheet_text: dict[str, str] = {}
        self._book_cache: MutableMapping[str, dict[int, _ChapterContext]] = {}
        self._book_service = BookContentService()

    def generate_for_scene(
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

        if not config.allow_overwrite:
            existing = self._prompt_repo.get_latest_set_for_scene(
                target_scene.id, config.model_name, config.prompt_version
            )
            if existing:
                return existing

        context_window, context_text = self._build_scene_context(target_scene, config)
        prompt = self._build_prompt(
            scene=target_scene,
            config=config,
            context_text=context_text,
            context_window=context_window,
        )
        raw_payload, llm_request_id, execution_time_ms = self._invoke_llm(
            prompt=prompt,
            config=config,
        )
        variants = self._extract_variants(raw_payload, config)
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
            "context_window": dict(context_window),
            "cheatsheet_path": config.include_cheatsheet_path,
        }
        if config.metadata:
            service_payload["run_metadata"] = dict(config.metadata)
        raw_bundle = {
            "response": raw_payload,
            "service": service_payload,
        }
        records = self._build_records(
            scene=target_scene,
            config=config,
            variants=variants,
            variant_indices=variant_indices,
            context_window=context_window,
            raw_payload=raw_bundle,
            llm_request_id=llm_request_id,
            execution_time_ms=execution_time_ms,
        )

        if config.dry_run:
            preview_prompts = self._instantiate_prompts_from_records(records)
            metadata_results = self._run_metadata_generation(
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

        if config.allow_overwrite:
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

        created = self._prompt_repo.bulk_create(
            records,
            commit=config.autocommit,
            refresh=True,
        )
        if not config.autocommit:
            self._session.flush()
        self._run_metadata_generation(
            created,
            dry_run=False,
            autocommit=config.autocommit,
        )
        return created

    def generate_for_scenes(
        self,
        scenes: Sequence[SceneExtraction | UUID],
        **overrides: Any,
    ) -> list[list[ImagePrompt] | list[ImagePromptPreview] | None]:
        results: list[list[ImagePrompt] | list[ImagePromptPreview] | None] = []
        for scene in scenes:
            try:
                result = self.generate_for_scene(scene, **overrides)
            except Exception as exc:  # pragma: no cover - defensive logging
                if self._config.fail_on_error or overrides.get("fail_on_error"):
                    raise
                logger.error("Image prompt generation failed for %s: %s", scene, exc)
                results.append(None)
                continue
            results.append(result)
        return results

    def generate_for_book(
        self,
        book_slug: str,
        *,
        scene_filter: Mapping[str, Any] | None = None,
        ranked_only: bool = False,
        top_n: int | None = None,
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
        return self.generate_for_scenes(candidate_scenes, **overrides)

    def generate_remix_variants(
        self,
        source_prompt: ImagePrompt | UUID,
        *,
        variants_count: int = REMIX_VARIANTS_COUNT,
        dry_run: bool = False,
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

        variant_indices = self._determine_next_variant_indices_for_scene(
            scene.id, variants_count
        )

        remix_prompt = self._build_remix_prompt(
            source_prompt=prompt_record,
            variants_count=variants_count,
        )
        raw_payload, llm_request_id, execution_time_ms = self._invoke_llm(
            prompt=remix_prompt,
            config=config,
            system_instruction=self._remix_system_instruction,
        )
        variants = self._extract_variants(raw_payload, config)

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

        if config.dry_run:
            preview_prompts = self._instantiate_prompts_from_records(records)
            metadata_results = self._run_metadata_generation(
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
        self._run_metadata_generation(
            created,
            dry_run=False,
            autocommit=config.autocommit,
        )
        return created

    def create_custom_remix_variant(
        self,
        source_prompt: ImagePrompt | UUID,
        custom_prompt_text: str,
        *,
        dry_run: bool = False,
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

        if dry_run:
            preview_prompts = self._instantiate_prompts_from_records([record])
            metadata_results = self._run_metadata_generation(
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
        self._run_metadata_generation(
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

    def _build_scene_context(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> tuple[dict[str, Any], str]:
        if scene.scene_paragraph_start is None or scene.scene_paragraph_end is None:
            base_start = max(scene.chunk_paragraph_start or 1, 1)
            base_end = max(scene.chunk_paragraph_end or base_start, base_start)
        else:
            base_start = max(int(scene.scene_paragraph_start), 1)
            base_end = max(int(scene.scene_paragraph_end), base_start)
        chapters = self._load_book_context(scene.source_book_path)
        chapter_context = chapters.get(int(scene.chapter_number))
        if chapter_context is None:
            raise ImagePromptGenerationServiceError(
                f"Chapter {scene.chapter_number} not found in {scene.source_book_path}"
            )
        before = max(config.context_before, 0)
        after = max(config.context_after, 0)
        total_paragraphs = len(chapter_context.paragraphs)
        start = max(1, base_start - before)
        end = min(total_paragraphs, base_end + after)
        formatted_lines: list[str] = []
        for index in range(start, end + 1):
            paragraph_text = chapter_context.paragraphs[index - 1]
            formatted_lines.append(f"[Paragraph {index}] {paragraph_text}")
        context_text = "\n".join(formatted_lines)
        context_window = {
            "chapter_number": scene.chapter_number,
            "chapter_title": chapter_context.title,
            "paragraph_span": [start, end],
            "paragraphs_before": before,
            "paragraphs_after": after,
        }
        return context_window, context_text

    def _build_prompt(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        context_text: str,
        context_window: Mapping[str, Any],
    ) -> str:
        cheatsheet = self._load_cheatsheet_text(config.include_cheatsheet_path)
        scene_excerpt = scene.raw.strip()
        if not scene_excerpt:
            raise ImagePromptGenerationServiceError(
                f"Scene {scene.id} is missing raw excerpt text"
            )
        metadata_lines = [
            f"- Book slug: {scene.book_slug}",
            f"- Chapter number: {scene.chapter_number}",
            f"- Chapter title: {scene.chapter_title}",
            f"- Scene number: {scene.scene_number}",
            f"- Location marker: {scene.location_marker}",
            f"- Paragraph span: {context_window['paragraph_span'][0]}-{context_window['paragraph_span'][1]}",
            f"- Context paragraphs: {config.context_before} before, {config.context_after} after",
        ]
        metadata_block = "\n".join(metadata_lines)
        guidance = (
            "Transform the excerpt into world-class DALLE3 prompts that read like senior concept art direction. "
            "Anchor every variant in the scene's emotional core and weave in concrete sensory cues (textures, weather, ambient sounds) that make the moment feel inhabitable. "
            "Favor evocative verbs and precise nouns over vague adjectives, highlighting movement, tension, or stillness as appropriate. "
            "Respect the excerpt's cultural and temporal signals while elevating them with imaginative yet coherent embellishments."
        )
        style_strategy = (
            "- Diagnose the dominant mood, genre, and sensory anchors in the excerpt before writing prompts.\n"
            "- Brainstorm at least three distinct visual treatments that could elevate the scene (e.g., painterly illustration, stylized animation, analog film photography, surreal collage, moody charcoal sketch, 3D cinematic render).\n"
            "- Assign one treatment to each variant; never repeat the same medium, art movement, or stylistic era across variants.\n"
            "- Balance the set with both photorealistic and non-photorealistic approaches when they suit the story, embracing bold experimentation that heightens the scene's core emotion.\n"
            "- Fuse palette, texture, lighting, and composition choices directly with narrative details so every style feels purposeful rather than arbitrary."
        )
        quality_objectives = (
            "- Each prompt must read like expert art direction, emphasising decisive verbs and tangible nouns over filler language.\n"
            "- Embed the chosen style and medium directly into the prompt_text and style_tags, and justify the match inside attributes.style_intent.\n"
            "- Spotlight unique facets of the scene per variant (alternate subjects, emotional beats, or spatial scales) so the set feels complementary, not redundant.\n"
            "- Leverage camera language (shot type, lens, framing) that supports the selected aesthetic and story beat.\n"
            "- Keep prompts within 20-40 words while remaining vivid, specific, and free of contradictions."
        )
        output_schema = json.dumps(
            {
                "title": "string",
                "prompt_text": "string",
                "style_tags": ["string"],
                "attributes": {
                    "camera": "string",
                    "lens": "string",
                    "composition": "string",
                    "lighting": "string",
                    "palette": "string",
                    "atmosphere": "string",
                    "aspect_ratio": "string",
                    "style_intent": "string",
                    "references": ["string"],
                },
            },
            indent=2,
        )
        prompt_lines = [
            "You are an elite prompt engineer who converts novel scenes into world-class AI image prompts.",
            f"Your goal is to produce exactly {config.variants_count} distinct prompt variants that produce exceptional images when fed into the DALLE3 model.",
            "",
            "## Scene Metadata",
            metadata_block,
            "",
            "## Scene Excerpt (verbatim)",
            scene_excerpt,
        ]
        prompt = "\n".join(prompt_lines)
        prompt += (
            "\n\n## Surrounding Context Paragraphs\n"
            f"{context_text}\n\n"
            "## Prompting Cheat Sheet\n"
            f"{cheatsheet}\n\n"
            "## Creative Guidance\n"
            f"{guidance}\n\n"
            "## Style Variation Strategy\n"
            f"{style_strategy}\n\n"
            "## Quality Objectives\n"
            f"{quality_objectives}\n\n"
            "## Output Requirements\n"
            f"- Return ONLY strict JSON (no markdown) representing an array of {config.variants_count} objects.\n"
            "- Each array element must contain the keys: title, prompt_text, style_tags, attributes.\n"
            "- title can be null; prompt_text must be richly descriptive and self-contained.\n"
            "- style_tags must be a list of short descriptors (2-5 entries).\n"
            "- attributes must detail composition, camera, lens, lighting, palette, atmosphere, aspect_ratio, style_intent, and references (list of influences or movements).\n"
            "- Ensure each variant explores a different angle, subject emphasis, or aesthetic; do not reuse the same style family or medium twice.\n"
            "- Include at least one variant that leans into an imaginative or stylised treatment instead of strict photorealism unless the scene clearly forbids it.\n"
            "- Do not include notes, warnings, or additional keys.\n"
            f"- The expected object shape is similar to: {output_schema}.\n"
            "- Never include copyrighted text beyond the provided excerpts."
        )
        return prompt

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

    def _invoke_llm(
        self,
        *,
        prompt: str,
        config: ImagePromptGenerationConfig,
        system_instruction: str | None = None,
    ) -> tuple[Any, str | None, int]:
        attempts = max(config.retry_attempts, 0) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            start_time = time.perf_counter()
            try:
                response = gemini_api.json_output(
                    prompt=prompt,
                    system_instruction=system_instruction or self._system_instruction,
                    model=config.model_name,
                    temperature=config.temperature,
                    max_tokens=config.max_output_tokens,
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
                    "Gemini prompt generation failed (attempt %s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt >= attempts:
                    break
                time.sleep(max(config.retry_backoff_seconds, 0))
        assert last_error is not None
        if config.fail_on_error:
            raise ImagePromptGenerationServiceError(
                f"Gemini prompt generation failed: {last_error}"
            ) from last_error
        raise ImagePromptGenerationServiceError(
            "Gemini prompt generation failed after retries"
        ) from last_error

    def _extract_variants(
        self,
        payload: Any,
        config: ImagePromptGenerationConfig,
    ) -> list[_VariantModel]:
        if isinstance(payload, dict) and "variants" in payload:
            payload = payload["variants"]
        if not isinstance(payload, Sequence):
            raise ImagePromptGenerationServiceError(
                "Gemini response must be a JSON array of variant objects"
            )
        variants = []
        for index, item in enumerate(payload):
            if not isinstance(item, Mapping):
                raise ImagePromptGenerationServiceError(
                    f"Variant {index} is not a JSON object"
                )
            variants.append(_VariantModel.from_payload(item))
        if len(variants) != config.variants_count:
            raise ImagePromptGenerationServiceError(
                f"Expected {config.variants_count} variants, received {len(variants)}"
            )
        return variants

    def _build_records(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        variants: Sequence[_VariantModel],
        variant_indices: Sequence[int],
        context_window: Mapping[str, Any],
        raw_payload: Mapping[str, Any],
        llm_request_id: str | None,
        execution_time_ms: int,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, variant in enumerate(variants):
            try:
                variant_index = variant_indices[index]
            except IndexError as exc:  # pragma: no cover - defensive
                raise ImagePromptGenerationServiceError(
                    "Variant indices length did not match variant payloads"
                ) from exc
            style_tags = list(variant.style_tags) if variant.style_tags else None
            attributes = dict(variant.attributes)
            records.append(
                {
                    "scene_extraction_id": scene.id,
                    "model_vendor": config.model_vendor,
                    "model_name": config.model_name,
                    "prompt_version": config.prompt_version,
                    "variant_index": variant_index,
                    "title": variant.title.strip()
                    if isinstance(variant.title, str)
                    else None,
                    "prompt_text": variant.prompt_text.strip(),
                    "negative_prompt": None,
                    "style_tags": style_tags,
                    "attributes": attributes,
                    "notes": None,
                    "context_window": dict(context_window),
                    "raw_response": dict(raw_payload),
                    "temperature": config.temperature,
                    "max_output_tokens": config.max_output_tokens,
                    "llm_request_id": llm_request_id,
                    "execution_time_ms": execution_time_ms,
                }
            )
        return records

    def _instantiate_prompts_from_records(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> list[ImagePrompt]:
        """Create transient ImagePrompt models from in-memory records."""
        prompts: list[ImagePrompt] = []
        for record in records:
            prompts.append(ImagePrompt(**record))  # type: ignore[arg-type]
        return prompts

    def _run_metadata_generation(
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
            results = service.generate_metadata_for_prompts(
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

    def _load_cheatsheet_text(self, path_str: str) -> str:
        if path_str in self._cheatsheet_text:
            return self._cheatsheet_text[path_str]
        path = Path(path_str)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not path.exists():
            raise ImagePromptGenerationServiceError(
                f"Cheat sheet file not found: {path_str}"
            )
        text = path.read_text(encoding="utf-8")
        self._cheatsheet_text[path_str] = text.strip()
        return self._cheatsheet_text[path_str]

    def _load_book_context(
        self,
        source_book_path: str,
    ) -> dict[int, _ChapterContext]:
        if source_book_path in self._book_cache:
            return self._book_cache[source_book_path]
        try:
            content = self._book_service.load_book(source_book_path)
        except BookContentServiceError as exc:
            raise ImagePromptGenerationServiceError(str(exc)) from exc

        chapters: dict[int, _ChapterContext] = {}
        for chapter_number, chapter in content.chapters.items():
            chapters[chapter_number] = _ChapterContext(
                number=chapter.number,
                title=chapter.title,
                paragraphs=list(chapter.paragraphs),
                source_name=chapter.source_name,
            )

        if not chapters:
            raise ImagePromptGenerationServiceError(
                f"No chapters extracted from book: {source_book_path}"
            )

        self._book_cache[source_book_path] = chapters
        return chapters

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
            ranking = self._ranking_repo.get_latest_for_scene(scene.id)
            if ranking is not None:
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
