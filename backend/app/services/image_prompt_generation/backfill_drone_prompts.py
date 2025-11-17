"""Backfill Culture drone prompts by generating new variants and images per scene.

This script finds all scenes that already have a prompt containing the word
\"drone\" and, for each scene, generates two fresh prompt variants (using a
backfill-specific prompt_version) and immediately produces images from those
prompts before moving to the next scene.

Run from the backend directory:
    uv run python -m app.services.image_prompt_generation.backfill_drone_prompts
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.db import engine
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
    ImageGenerationServiceError,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_VERSION = "image-prompts-v3-drone-backfill"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate replacement prompts and images for scenes whose existing "
            "prompts contain the word 'drone'."
        )
    )
    parser.add_argument(
        "--book-slug",
        help="Optional book slug filter to limit scope (e.g., look-to-windward-iain-m-banks).",
    )
    parser.add_argument(
        "--scene-id",
        help="Optional specific scene UUID to process (overrides book filter).",
    )
    parser.add_argument(
        "--prompt-version",
        default=DEFAULT_PROMPT_VERSION,
        help=f"Prompt version to use for backfill (default: {DEFAULT_PROMPT_VERSION}).",
    )
    parser.add_argument(
        "--quality",
        choices=["standard", "hd"],
        default="standard",
        help="Image quality for generation (default: standard).",
    )
    parser.add_argument(
        "--style",
        "--preferred-style",
        dest="preferred_style",
        choices=["vivid", "natural"],
        help="Optional preferred image style.",
    )
    parser.add_argument(
        "--aspect-ratio",
        choices=["1:1", "9:16", "16:9"],
        help="Optional aspect ratio override for image generation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which scenes would be processed without persisting prompts or generating images.",
    )
    return parser


def _find_scenes_with_drone_prompts(
    session: Session, book_slug: str | None, scene_id: str | None
) -> list[SceneExtraction]:
    """Return distinct scenes that already have a prompt containing 'drone'."""
    stmt = (
        select(SceneExtraction)
        .join(ImagePrompt, ImagePrompt.scene_extraction_id == SceneExtraction.id)
        .where(func.lower(ImagePrompt.prompt_text).contains("drone"))
        .distinct(SceneExtraction.id)
    )
    if book_slug:
        stmt = stmt.where(SceneExtraction.book_slug == book_slug)
    if scene_id:
        try:
            scene_uuid = UUID(scene_id)
        except ValueError as exc:  # pragma: no cover - CLI validation
            raise SystemExit(f"Invalid scene-id UUID: {scene_id}") from exc
        stmt = stmt.where(SceneExtraction.id == scene_uuid)
    scenes = list(session.exec(stmt))
    scenes.sort(
        key=lambda s: (
            s.book_slug or "",
            s.chapter_number or 0,
            s.scene_number or 0,
        )
    )
    return scenes


async def _generate_for_scene(
    *,
    scene: SceneExtraction,
    prompt_service: ImagePromptGenerationService,
    prompt_version: str,
    image_service: ImageGenerationService,
    quality: str,
    preferred_style: str | None,
    aspect_ratio: str | None,
    dry_run: bool,
) -> None:
    logger.info(
        "Processing scene %s (book=%s ch=%s scene=%s)",
        scene.id,
        scene.book_slug,
        scene.chapter_number,
        scene.scene_number,
    )

    try:
        prompts = await prompt_service.generate_for_scene(
            scene,
            prompt_version=prompt_version,
            variants_count=2,
            overwrite=False,
            dry_run=dry_run,
            metadata={"backfill": "drone_prompt_cleanup"},
        )
    except ImagePromptGenerationServiceError as exc:
        logger.error("Prompt generation failed for scene %s: %s", scene.id, exc)
        return

    # Dry-run path returns previews; skip image generation.
    if dry_run:
        logger.info(
            "DRY RUN: Would generate images for %s prompt variants on scene %s",
            len(prompts),
            scene.id,
        )
        return

    prompt_ids: list[UUID] = [p.id for p in prompts] if prompts else []
    if not prompt_ids:
        logger.warning("No prompts returned for scene %s; skipping images", scene.id)
        return

    try:
        await image_service.generate_for_selection(
            prompt_ids=prompt_ids,
            quality=quality,
            preferred_style=preferred_style,
            aspect_ratio=aspect_ratio,
            concurrency=1,  # sequential per scene
            dry_run=dry_run,
        )
    except ImageGenerationServiceError as exc:
        logger.error("Image generation failed for scene %s: %s", scene.id, exc)


async def main() -> int:
    args = _build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with Session(engine) as session:
        scenes = _find_scenes_with_drone_prompts(session, args.book_slug, args.scene_id)
        if not scenes:
            logger.info("No scenes found with prompts containing 'drone'.")
            return 0

        if args.dry_run:
            logger.info(
                "DRY RUN: Found %s scenes with existing drone prompts%s%s",
                len(scenes),
                f" (book={args.book_slug})" if args.book_slug else "",
                f" (scene={args.scene_id})" if args.scene_id else "",
            )
            for scene in scenes:
                logger.info(
                    "DRY RUN: scene %s book=%s chapter=%s scene=%s",
                    scene.id,
                    scene.book_slug,
                    scene.chapter_number,
                    scene.scene_number,
                )
            return 0

        prompt_service = ImagePromptGenerationService(
            session,
            ImagePromptGenerationConfig(
                variants_count=2,
                use_ranking_recommendation=False,
                prompt_version=args.prompt_version,
                allow_overwrite=False,
                fail_on_error=False,
            ),
        )
        image_service = ImageGenerationService(
            session,
            ImageGenerationConfig(
                quality=args.quality,
                preferred_style=args.preferred_style,
                aspect_ratio=args.aspect_ratio,
                concurrency=1,
                dry_run=args.dry_run,
            ),
        )

        logger.info(
            "Found %s scenes with existing drone prompts%s",
            len(scenes),
            f" (book={args.book_slug})" if args.book_slug else "",
        )
        for scene in scenes:
            await _generate_for_scene(
                scene=scene,
                prompt_service=prompt_service,
                prompt_version=args.prompt_version,
                image_service=image_service,
                quality=args.quality,
                preferred_style=args.preferred_style,
                aspect_ratio=args.aspect_ratio,
                dry_run=args.dry_run,
            )

    return 0


if __name__ == "__main__":
    asyncio.run(main())
