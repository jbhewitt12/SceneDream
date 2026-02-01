"""Service for generating images from structured prompts using DALL·E 3."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from app.repositories.generated_image import GeneratedImageRepository
from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.image_generation import (
    dalle_image_api,  # noqa: F401 - ensures provider registration
    gpt_image_api,  # noqa: F401 - ensures provider registration
)
from app.services.image_generation.provider_registry import ProviderRegistry
from models.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class ImageGenerationServiceError(RuntimeError):
    """Raised when image generation fails under strict settings."""


@dataclass(slots=True)
class ImageGenerationConfig:
    """Runtime configuration for image generation."""

    provider: str = "openai_gpt_image"
    model: str = "gpt-image-1.5"
    quality: str = "standard"
    preferred_style: str | None = None
    aspect_ratio: str | None = None
    response_format: str = "b64_json"
    concurrency: int = 3
    blocked_warnings: set[str] = field(
        default_factory=lambda: {"violence", "sexual", "drugs", "horror", "hate"}
    )
    skip_scenes_with_warnings: bool = True
    dry_run: bool = False
    api_key: str | None = None
    storage_base: str = "img/generated"

    def copy_with(self, **overrides: Any) -> ImageGenerationConfig:
        """Create a copy with overridden fields."""
        data: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "quality": self.quality,
            "preferred_style": self.preferred_style,
            "aspect_ratio": self.aspect_ratio,
            "response_format": self.response_format,
            "concurrency": self.concurrency,
            "blocked_warnings": set(self.blocked_warnings),
            "skip_scenes_with_warnings": self.skip_scenes_with_warnings,
            "dry_run": self.dry_run,
            "api_key": self.api_key,
            "storage_base": self.storage_base,
        }
        # Handle blocked_warnings specially to preserve set type
        normalized_overrides = {}
        for k, v in overrides.items():
            if k == "blocked_warnings" and v is not None:
                normalized_overrides[k] = set(v)
            elif v is not None:
                normalized_overrides[k] = v
        data.update(normalized_overrides)
        return ImageGenerationConfig(**data)


@dataclass(slots=True)
class GenerationTask:
    """Represents a single image generation task."""

    prompt: ImagePrompt
    variant_index: int
    size: str
    quality: str
    style: str
    aspect_ratio: str | None
    storage_path: str
    file_name: str


@dataclass(slots=True)
class GenerationResult:
    """Result of an image generation attempt."""

    task: GenerationTask
    generated_image_id: UUID | None = None
    error: str | None = None
    skipped: bool = False


def map_aspect_ratio_to_size(
    aspect_ratio: str | None, provider: str = "openai_gpt_image"
) -> str:
    """
    Map aspect ratio to provider-specific size.

    Args:
        aspect_ratio: Aspect ratio string (1:1, 9:16, 16:9) or None
        provider: Image provider name (affects available sizes)

    Returns:
        Size string appropriate for the provider
    """
    # GPT Image uses different sizes than DALL-E 3
    if provider == "openai_gpt_image":
        mapping = {
            "1:1": "1024x1024",
            "9:16": "1024x1536",
            "16:9": "1536x1024",
        }
    else:
        # DALL-E 3 sizes
        mapping = {
            "1:1": "1024x1024",
            "9:16": "1024x1792",
            "16:9": "1792x1024",
        }
    return mapping.get(aspect_ratio or "", "1024x1024")


def derive_style_from_tags(
    style_tags: list[str] | None, preferred: str | None = None
) -> str:
    """
    Derive DALL·E 3 style from prompt style tags.

    Args:
        style_tags: List of style tags from the image prompt
        preferred: Preferred style override

    Returns:
        Style string for DALL·E 3 API ("vivid" or "natural")
    """
    if preferred:
        return preferred

    if style_tags:
        for tag in style_tags:
            if "natural" in tag.lower():
                return "natural"

    return "vivid"


def compute_file_checksum(file_path: Path) -> str:
    """
    Compute SHA256 checksum of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hexadecimal SHA256 checksum string
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


class ImageGenerationService:
    """Generate images from prompts using DALL·E 3 with idempotency and concurrency control."""

    def __init__(
        self,
        session: Session,
        config: ImageGenerationConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        self._session = session
        self._config = config or ImageGenerationConfig()
        self._api_key = (
            api_key
            or self._config.api_key
            or settings.OPENAI_API_KEY
            or os.getenv("OPENAI_API_KEY", "")
        )
        self._image_repo = GeneratedImageRepository(session)
        self._prompt_repo = ImagePromptRepository(session)
        self._scene_repo = SceneExtractionRepository(session)
        self._ranking_repo = SceneRankingRepository(session)

    async def generate_for_selection(
        self,
        *,
        book_slug: str | None = None,
        chapter_range: tuple[int, int] | None = None,
        scene_ids: list[UUID] | None = None,
        prompt_ids: list[UUID] | None = None,
        top_scenes: int | None = None,
        limit: int | None = None,
        quality: str = "standard",
        preferred_style: str | None = None,
        aspect_ratio: str | None = None,
        provider: str = "openai_gpt_image",
        model: str = "gpt-image-1.5",
        response_format: str = "b64_json",
        concurrency: int = 3,
        dry_run: bool = False,
    ) -> list[UUID]:
        """
        Generate images for a selection of prompts.

        Args:
            book_slug: Filter prompts by book slug
            chapter_range: Filter by chapter range (inclusive start, exclusive end)
            scene_ids: Filter by specific scene extraction IDs
            prompt_ids: Filter by specific image prompt IDs
            top_scenes: Generate for top N scenes by ranking (skips scenes with existing images)
            limit: Maximum number of images to generate
            quality: Image quality ("standard" or "hd")
            preferred_style: Preferred style override ("vivid" or "natural")
            aspect_ratio: Preferred aspect ratio ("1:1", "9:16", or "16:9")
            provider: Image generation provider (default: "openai")
            model: Model to use (default: "dall-e-3")
            response_format: Response format ("b64_json" or "url")
            concurrency: Number of concurrent generation tasks
            dry_run: If True, plan tasks without executing them

        Returns:
            List of generated image IDs (or empty list in dry-run mode)
        """
        config = self._config.copy_with(
            provider=provider,
            model=model,
            quality=quality,
            preferred_style=preferred_style,
            aspect_ratio=aspect_ratio,
            response_format=response_format,
            concurrency=concurrency,
            dry_run=dry_run,
        )

        # Fetch prompts based on filters
        prompts = await self._fetch_prompts(
            book_slug=book_slug,
            chapter_range=chapter_range,
            scene_ids=scene_ids,
            prompt_ids=prompt_ids,
            top_scenes=top_scenes,
            limit=limit,
        )

        if not prompts:
            logger.info("No prompts found matching the selection criteria")
            return []

        # Build generation tasks
        tasks = self._build_tasks(prompts, config)

        if config.dry_run:
            self._log_dry_run(tasks, config)
            return []

        # Execute tasks with concurrency control
        results = await self._execute_tasks(tasks, config)

        # Collect successful generation IDs
        generated_ids = [
            r.generated_image_id for r in results if r.generated_image_id is not None
        ]

        logger.info(
            "Generated %d images (%d skipped, %d errors)",
            len(generated_ids),
            sum(1 for r in results if r.skipped),
            sum(1 for r in results if r.error),
        )

        return generated_ids

    async def _fetch_prompts(
        self,
        *,
        book_slug: str | None,
        chapter_range: tuple[int, int] | None,
        scene_ids: list[UUID] | None,
        prompt_ids: list[UUID] | None,
        top_scenes: int | None,
        limit: int | None,
    ) -> list[ImagePrompt]:
        """Fetch prompts based on selection criteria."""
        # Handle top_scenes mode first (priority over other filters)
        if top_scenes is not None and book_slug:
            return await self._fetch_prompts_for_top_scenes(
                book_slug=book_slug,
                top_scenes_count=top_scenes,
            )

        if prompt_ids:
            # Direct prompt ID lookup
            prompts = []
            for prompt_id in prompt_ids:
                prompt = self._prompt_repo.get(prompt_id)
                if prompt:
                    prompts.append(prompt)
            if limit:
                prompts = prompts[:limit]
            return prompts

        if scene_ids:
            # Fetch prompts for specific scenes
            prompts = []
            for scene_id in scene_ids:
                scene_prompts = self._prompt_repo.list_for_scene(
                    scene_id,
                    include_scene=True,
                )
                prompts.extend(scene_prompts)
            if limit:
                prompts = prompts[:limit]
            return prompts

        if book_slug:
            # Fetch prompts for book/chapters
            prompts = self._prompt_repo.list_for_book(
                book_slug=book_slug,
                include_scene=True,
            )

            # Apply chapter range filter if specified
            if chapter_range:
                start_chapter, end_chapter = chapter_range
                prompts = [
                    p
                    for p in prompts
                    if p.scene_extraction
                    and start_chapter <= p.scene_extraction.chapter_number < end_chapter
                ]

            if limit:
                prompts = prompts[:limit]
            return prompts

        return []

    async def _fetch_prompts_for_top_scenes(
        self,
        *,
        book_slug: str,
        top_scenes_count: int,
    ) -> list[ImagePrompt]:
        """
        Fetch prompts for top-ranked scenes, skipping scenes with existing images or missing prompts.

        Args:
            book_slug: Book slug to filter by
            top_scenes_count: Number of top scenes to process (actual scenes with prompts and images generated)

        Returns:
            List of prompts for scenes without existing images
        """
        # Fetch many more rankings than needed to account for:
        # - scenes with existing images
        # - scenes with content warnings
        # - scenes without prompts
        # We'll fetch 10x the requested amount to have a good buffer
        fetch_limit = top_scenes_count * 10

        logger.info(
            "Fetching top %d rankings for book '%s' (will filter to %d scenes with prompts and no images)",
            fetch_limit,
            book_slug,
            top_scenes_count,
        )

        # Get top-ranked scenes
        rankings = self._ranking_repo.list_top_rankings_for_book(
            book_slug=book_slug,
            limit=fetch_limit,
            include_scene=True,
        )

        if not rankings:
            logger.warning("No rankings found for book '%s'", book_slug)
            return []

        logger.info("Found %d rankings for book '%s'", len(rankings), book_slug)

        # Iterate through rankings and collect prompts until we have enough scenes
        prompts: list[ImagePrompt] = []
        scenes_with_prompts_added = 0

        for ranking in rankings:
            # Check if we've collected prompts for enough scenes
            if scenes_with_prompts_added >= top_scenes_count:
                logger.info(
                    "Reached target of %d scenes with prompts",
                    top_scenes_count,
                )
                break

            scene_id = ranking.scene_extraction_id

            # Check for content warnings first
            if (
                self._config.skip_scenes_with_warnings
                and self._ranking_has_blocked_warnings(ranking)
            ):
                problematic = self._get_problematic_warnings_from_ranking(ranking)
                logger.debug(
                    "Skipping scene %s (priority=%.3f) due to content warnings: %s",
                    scene_id,
                    ranking.overall_priority,
                    ", ".join(problematic),
                )
                continue

            # Check if this scene already has generated images
            existing_images = self._image_repo.list_for_scene(
                scene_id,
                limit=1,
            )

            if existing_images:
                logger.debug(
                    "Skipping scene %s (priority=%.3f) - already has %d generated image(s)",
                    scene_id,
                    ranking.overall_priority,
                    len(existing_images),
                )
                continue

            # Check if scene has prompts
            scene_prompts = self._prompt_repo.list_for_scene(
                scene_id,
                include_scene=True,
            )

            if not scene_prompts:
                logger.warning(
                    "No prompts found for scene %s (priority=%.3f)",
                    scene_id,
                    ranking.overall_priority,
                )
                continue

            # This scene is valid - add its prompts
            prompts.extend(scene_prompts)
            scenes_with_prompts_added += 1
            logger.debug(
                "Selected %d prompt(s) for scene %s (priority=%.3f) [%d/%d scenes]",
                len(scene_prompts),
                scene_id,
                ranking.overall_priority,
                scenes_with_prompts_added,
                top_scenes_count,
            )

        logger.info(
            "Selected %d prompts from %d scenes (target: %d scenes)",
            len(prompts),
            scenes_with_prompts_added,
            top_scenes_count,
        )

        if scenes_with_prompts_added < top_scenes_count:
            logger.warning(
                "Only found %d scenes with prompts out of target %d (may need to generate more prompts or rank more scenes)",
                scenes_with_prompts_added,
                top_scenes_count,
            )

        return prompts

    def _build_tasks(
        self,
        prompts: list[ImagePrompt],
        config: ImageGenerationConfig,
    ) -> list[GenerationTask]:
        """Build generation tasks from prompts."""
        tasks: list[GenerationTask] = []

        # Track fallback variant indices per scene (used only if prompt.variant_index is missing)
        scene_variant_counters: dict[UUID, int] = {}

        for prompt in prompts:
            if not prompt.scene_extraction:
                logger.warning(
                    "Prompt %s has no scene_extraction; skipping",
                    prompt.id,
                )
                continue

            scene = prompt.scene_extraction
            scene_id = scene.id

            # Determine aspect ratio, size, and style
            prompt_aspect = (
                prompt.attributes.get("aspect_ratio") if prompt.attributes else None
            )
            aspect_ratio = config.aspect_ratio or prompt_aspect
            size = map_aspect_ratio_to_size(aspect_ratio, config.provider)
            style = derive_style_from_tags(prompt.style_tags, config.preferred_style)

            if prompt.variant_index is not None:
                variant_index = prompt.variant_index
                scene_variant_counters[scene_id] = max(
                    scene_variant_counters.get(scene_id, variant_index + 1),
                    variant_index + 1,
                )
            else:
                # Fallback to sequential counter if prompt lacks explicit variant index
                variant_index = scene_variant_counters.get(scene_id, 0)
                scene_variant_counters[scene_id] = variant_index + 1

            # Build storage path and filename
            storage_path = f"{config.storage_base}/{scene.book_slug}/chapter-{scene.chapter_number}"
            file_name = f"scene-{scene.scene_number}-v{variant_index}.png"

            # Check for idempotency
            existing = self._image_repo.find_existing_by_params(
                image_prompt_id=prompt.id,
                variant_index=variant_index,
                provider=config.provider,
                model=config.model,
                size=size,
                quality=config.quality,
                style=style,
            )
            if existing:
                logger.debug(
                    "Skipping prompt %s (image already exists: %s)",
                    prompt.id,
                    existing.id,
                )
                continue

            tasks.append(
                GenerationTask(
                    prompt=prompt,
                    variant_index=variant_index,
                    size=size,
                    quality=config.quality,
                    style=style,
                    aspect_ratio=aspect_ratio,
                    storage_path=storage_path,
                    file_name=file_name,
                )
            )

        return tasks

    def _log_dry_run(
        self,
        tasks: list[GenerationTask],
        config: ImageGenerationConfig,
    ) -> None:
        """Log planned operations in dry-run mode."""
        logger.info("=== DRY RUN MODE ===")
        logger.info("Planned generation tasks: %d", len(tasks))
        logger.info("Provider: %s", config.provider)
        logger.info("Model: %s", config.model)
        logger.info("Quality: %s", config.quality)
        logger.info("Response format: %s", config.response_format)
        logger.info("Concurrency: %d", config.concurrency)

        for i, task in enumerate(tasks[:10]):  # Show first 10
            logger.info(
                "Task %d: prompt=%s, size=%s, style=%s, path=%s/%s",
                i + 1,
                task.prompt.id,
                task.size,
                task.style,
                task.storage_path,
                task.file_name,
            )

        if len(tasks) > 10:
            logger.info("... and %d more tasks", len(tasks) - 10)

    async def _execute_tasks(
        self,
        tasks: list[GenerationTask],
        config: ImageGenerationConfig,
    ) -> list[GenerationResult]:
        """Execute generation tasks with bounded concurrency."""
        semaphore = asyncio.Semaphore(config.concurrency)
        results: list[GenerationResult] = []

        async def bounded_generate(task: GenerationTask) -> GenerationResult:
            async with semaphore:
                return await self._generate_single(task, config)

        # Execute all tasks concurrently (bounded by semaphore)
        results = await asyncio.gather(
            *[bounded_generate(task) for task in tasks],
            return_exceptions=False,
        )

        return results

    async def _generate_single(
        self,
        task: GenerationTask,
        config: ImageGenerationConfig,
    ) -> GenerationResult:
        """Generate a single image from a task."""
        try:
            # Check idempotency again (in case of race conditions)
            existing = self._image_repo.find_existing_by_params(
                image_prompt_id=task.prompt.id,
                variant_index=task.variant_index,
                provider=config.provider,
                model=config.model,
                size=task.size,
                quality=task.quality,
                style=task.style,
            )
            if existing:
                return GenerationResult(task=task, skipped=True)

            # Log the prompt being used
            logger.info(
                "Generating image with prompt (ID: %s):\n%s",
                task.prompt.id,
                task.prompt.prompt_text,
            )

            # Get the provider from registry
            provider = ProviderRegistry.get(config.provider)
            if not provider:
                raise ImageGenerationServiceError(
                    f"Unknown provider: {config.provider}. "
                    f"Available: {ProviderRegistry.list_providers()}"
                )

            # Validate API key
            if not self._api_key:
                raise ImageGenerationServiceError(
                    "API key is required for image generation"
                )

            # Call provider's generate_image method
            result = await provider.generate_image(
                prompt=task.prompt.prompt_text,
                model=config.model,
                size=task.size,
                quality=task.quality,
                style=task.style,
                response_format=config.response_format,
                api_key=self._api_key,
            )

            if result.error:
                raise ImageGenerationServiceError(result.error)

            # Save image to disk
            storage_dir = _PROJECT_ROOT / task.storage_path
            storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = storage_dir / task.file_name

            loop = asyncio.get_event_loop()
            if result.image_data:
                # Save from bytes directly
                await loop.run_in_executor(
                    None,
                    lambda: file_path.write_bytes(result.image_data),  # type: ignore[arg-type]
                )
            elif result.image_url:
                # Save from URL
                success = await loop.run_in_executor(
                    None,
                    lambda: dalle_image_api.save_image_from_url(
                        result.image_url, str(file_path)  # type: ignore[arg-type]
                    ),
                )
                if not success:
                    raise ImageGenerationServiceError("Failed to save image from URL")
            else:
                raise ImageGenerationServiceError("No image data or URL in result")

            # Compute file metadata
            file_size = file_path.stat().st_size
            checksum = await loop.run_in_executor(
                None,
                lambda: compute_file_checksum(file_path),
            )

            # Parse dimensions from size string
            width, height = map(int, task.size.split("x"))

            # Create database record
            assert task.prompt.scene_extraction is not None
            image_data = {
                "scene_extraction_id": task.prompt.scene_extraction_id,
                "image_prompt_id": task.prompt.id,
                "book_slug": task.prompt.scene_extraction.book_slug,
                "chapter_number": task.prompt.scene_extraction.chapter_number,
                "variant_index": task.variant_index,
                "provider": config.provider,
                "model": config.model,
                "size": task.size,
                "quality": task.quality,
                "style": task.style,
                "aspect_ratio": task.aspect_ratio,
                "response_format": config.response_format,
                "storage_path": task.storage_path,
                "file_name": task.file_name,
                "width": width,
                "height": height,
                "bytes_approx": file_size,
                "checksum_sha256": checksum,
                "request_id": None,  # Could extract from API response if available
            }

            generated_image = self._image_repo.create(
                data=image_data,
                commit=True,
                refresh=True,
            )

            logger.info(
                "Generated image %s for prompt %s (%s, %s)",
                generated_image.id,
                task.prompt.id,
                task.size,
                task.style,
            )

            return GenerationResult(
                task=task,
                generated_image_id=generated_image.id,
            )

        except Exception as exc:
            error_msg = f"Failed to generate image: {exc}"
            logger.error(
                "Error generating image for prompt %s: %s",
                task.prompt.id,
                exc,
            )

            # Try to create a failed record
            try:
                assert task.prompt.scene_extraction is not None
                failed_data = {
                    "scene_extraction_id": task.prompt.scene_extraction_id,
                    "image_prompt_id": task.prompt.id,
                    "book_slug": task.prompt.scene_extraction.book_slug,
                    "chapter_number": task.prompt.scene_extraction.chapter_number,
                    "variant_index": task.variant_index,
                    "provider": config.provider,
                    "model": config.model,
                    "size": task.size,
                    "quality": task.quality,
                    "style": task.style,
                    "aspect_ratio": task.aspect_ratio,
                    "response_format": config.response_format,
                    "storage_path": task.storage_path,
                    "file_name": task.file_name,
                    "error": error_msg,
                }
                failed_image = self._image_repo.create(
                    data=failed_data,
                    commit=True,
                    refresh=True,
                )
                logger.info("Created failed image record: %s", failed_image.id)
            except Exception as db_exc:
                logger.error("Failed to create error record: %s", db_exc)

            return GenerationResult(task=task, error=error_msg)

    def _ranking_has_blocked_warnings(self, ranking: Any) -> bool:
        """Check if ranking has any blocked content warnings."""
        if not self._config.blocked_warnings:
            return False

        if not ranking or not hasattr(ranking, "warnings") or not ranking.warnings:
            return False

        # Check if any warning matches a blocked warning (case-insensitive)
        scene_warnings = {w.lower() for w in ranking.warnings}
        blocked_warnings = {w.lower() for w in self._config.blocked_warnings}
        return bool(scene_warnings & blocked_warnings)

    def _get_problematic_warnings_from_ranking(self, ranking: Any) -> list[str]:
        """Get list of problematic warnings from a ranking."""
        if not ranking or not hasattr(ranking, "warnings") or not ranking.warnings:
            return []

        scene_warnings = {w.lower(): w for w in ranking.warnings}
        blocked_warnings = {w.lower() for w in self._config.blocked_warnings}
        problematic = scene_warnings.keys() & blocked_warnings
        return [scene_warnings[w] for w in problematic]


__all__ = [
    "ImageGenerationService",
    "ImageGenerationConfig",
    "ImageGenerationServiceError",
    "GenerationTask",
    "GenerationResult",
    "map_aspect_ratio_to_size",
    "derive_style_from_tags",
    "compute_file_checksum",
]
