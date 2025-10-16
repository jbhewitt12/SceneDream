"""Complete image generation pipeline orchestrator CLI.

This CLI orchestrates the full pipeline from scene extraction through image generation:
1. Extract and refine scenes from a book
2. Rank all extracted scenes
3. Generate prompts for top-ranked scenes
4. Generate images for top-ranked scenes with prompts

Usage examples:
    # Run full pipeline with automatic variant counts from scene complexity analysis
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --book-path "books/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub" --images-for-scenes 5

    # Run full pipeline for top 10 scenes only (prompts and images)
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --book-path "books/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub" --prompts-for-scenes 10 --images-for-scenes 10

    # Generate prompts using scene complexity recommendations (default behavior)
    uv run python -m app.services.image_gen_cli prompts --book-slug look-to-windward-iain-m-banks --top-scenes 10

    # Override with fixed count for all scenes
    uv run python -m app.services.image_gen_cli prompts --book-slug look-to-windward-iain-m-banks --top-scenes 10 --prompts-per-scene 5 --ignore-ranking-recommendations

    # Extract and refine only
    uv run python -m app.services.image_gen_cli extract --book-slug look-to-windward-iain-m-banks --book-path "books/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub"

    # Rank existing scenes (no book-path needed, works from database)
    uv run python -m app.services.image_gen_cli rank --book-slug look-to-windward-iain-m-banks

    # Generate images for top 5 scenes (no book-path needed, works from database)
    uv run python -m app.services.image_gen_cli images --book-slug look-to-windward-iain-m-banks --top-scenes 5

    # Dry run to preview what would happen
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --book-path "books/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub" --images-for-scenes 3 --dry-run

    # Skip extraction and run remaining steps (useful if scenes already extracted)
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --skip-extraction --images-for-scenes 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from sqlmodel import Session

from app.core.db import engine
from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
)
from app.services.scene_extraction.scene_extraction import (
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_ranking.scene_ranking_service import (
    SceneRankingConfig,
    SceneRankingService,
)

logger = logging.getLogger(__name__)


class PipelineStats:
    """Track statistics across the pipeline."""

    def __init__(self) -> None:
        self.scenes_extracted = 0
        self.scenes_refined = 0
        self.scenes_ranked = 0
        self.prompts_generated = 0
        self.images_generated = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "scenes_extracted": self.scenes_extracted,
            "scenes_refined": self.scenes_refined,
            "scenes_ranked": self.scenes_ranked,
            "prompts_generated": self.prompts_generated,
            "images_generated": self.images_generated,
            "errors": self.errors,
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orchestrate the complete image generation pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Full pipeline command
    run = subparsers.add_parser(
        "run",
        help="Run the complete pipeline: extract -> rank -> prompts -> images",
    )
    _add_book_args(run)
    run.add_argument(
        "--prompts-per-scene",
        type=int,
        help="Override number of prompt variants per scene (ignores ranking recommendations when provided)",
    )
    run.add_argument(
        "--ignore-ranking-recommendations",
        action="store_true",
        help="Always use --prompts-per-scene value, ignoring scene complexity analysis",
    )
    run.add_argument(
        "--prompts-for-scenes",
        type=int,
        help="Number of top-ranked scenes to generate prompts for (default: all scenes without prompts)",
    )
    run.add_argument(
        "--images-for-scenes",
        type=int,
        default=5,
        help="Number of top-ranked scenes to generate images for (default: 5)",
    )
    run.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip scene extraction (use existing scenes)",
    )
    run.add_argument(
        "--skip-ranking",
        action="store_true",
        help="Skip scene ranking (use existing rankings)",
    )
    run.add_argument(
        "--skip-prompts",
        action="store_true",
        help="Skip prompt generation (use existing prompts)",
    )
    _add_quality_args(run)
    _add_common_args(run)

    # Extract-only command
    extract = subparsers.add_parser(
        "extract",
        help="Extract and refine scenes from a book",
    )
    _add_book_args(extract)
    extract.add_argument(
        "--no-refine",
        action="store_true",
        help="Disable scene refinement",
    )
    _add_common_args(extract)

    # Rank-only command
    rank = subparsers.add_parser(
        "rank",
        help="Rank extracted scenes",
    )
    rank.add_argument(
        "--book-slug",
        required=True,
        help="Book slug to rank scenes for",
    )
    rank.add_argument(
        "--limit",
        type=int,
        help="Maximum number of scenes to rank",
    )
    rank.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-rank scenes even if they already have rankings",
    )
    _add_common_args(rank)

    # Prompts-only command
    prompts = subparsers.add_parser(
        "prompts",
        help="Generate image prompts for ranked scenes",
    )
    prompts.add_argument(
        "--book-slug",
        required=True,
        help="Book slug to generate prompts for",
    )
    prompts.add_argument(
        "--prompts-per-scene",
        type=int,
        help="Override number of prompt variants per scene (ignores ranking recommendations when provided)",
    )
    prompts.add_argument(
        "--ignore-ranking-recommendations",
        action="store_true",
        help="Always use --prompts-per-scene value, ignoring scene complexity analysis",
    )
    prompts.add_argument(
        "--top-scenes",
        type=int,
        help="Only generate prompts for top N ranked scenes",
    )
    prompts.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate prompts even if they exist",
    )
    _add_common_args(prompts)

    # Images-only command
    images = subparsers.add_parser(
        "images",
        help="Generate images from prompts",
    )
    images.add_argument(
        "--book-slug",
        required=True,
        help="Book slug to generate images for",
    )
    images.add_argument(
        "--top-scenes",
        type=int,
        required=True,
        help="Number of top-ranked scenes to generate images for",
    )
    _add_quality_args(images)
    images.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent image generation tasks (default: 3)",
    )
    _add_common_args(images)

    return parser


def _add_book_args(parser: argparse.ArgumentParser) -> None:
    """Add book-related arguments."""
    parser.add_argument(
        "--book-slug",
        help="Book slug (e.g., look-to-windward-iain-m-banks). If provided without --book-path, book extraction will be skipped.",
    )
    parser.add_argument(
        "--book-path",
        help="Path to EPUB file. Required for scene extraction. Can be absolute or relative to project root.",
    )


def _add_quality_args(parser: argparse.ArgumentParser) -> None:
    """Add image quality arguments."""
    parser.add_argument(
        "--quality",
        choices=["standard", "hd"],
        default="standard",
        help="Image quality (default: standard)",
    )
    parser.add_argument(
        "--style",
        choices=["vivid", "natural"],
        help="Image style preference",
    )
    parser.add_argument(
        "--aspect-ratio",
        choices=["1:1", "9:16", "16:9"],
        help="Image aspect ratio",
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )


async def _run_full_pipeline(args: argparse.Namespace) -> PipelineStats:
    """Run the complete pipeline."""
    stats = PipelineStats()

    # Validate book_path is provided if extraction is needed
    if not args.skip_extraction and not args.book_path:
        logger.error(
            "--book-path is required for scene extraction. Either provide --book-path or use --skip-extraction."
        )
        raise ValueError("--book-path is required for scene extraction")

    book_path = Path(args.book_path) if args.book_path else None

    # Step 1: Extract scenes (if not skipped)
    if not args.skip_extraction:
        logger.info("=" * 60)
        logger.info("STEP 1: EXTRACTING SCENES")
        logger.info("=" * 60)

        if args.dry_run:
            logger.info("DRY RUN: Would extract scenes from %s", book_path)
        else:
            config = SceneExtractionConfig(
                enable_refinement=True,
                book_slug=args.book_slug,
            )
            extractor = SceneExtractor(config=config)
            extraction_stats = extractor.extract_book(book_path)
            stats.scenes_extracted = extraction_stats.get("scenes", 0)
            logger.info("Extracted %d scenes", stats.scenes_extracted)
    else:
        logger.info("Skipping scene extraction (--skip-extraction)")

    # Determine book slug
    book_slug = args.book_slug
    if not book_slug:
        if book_path and not args.dry_run:
            config = SceneExtractionConfig()
            extractor = SceneExtractor(config=config)
            book_slug = extractor._resolve_book_slug(book_path)
            logger.info("Resolved book slug: %s", book_slug)
        else:
            logger.error(
                "--book-slug is required when --skip-extraction is used without --book-path"
            )
            raise ValueError("--book-slug is required")

    # Step 2: Rank scenes (if not skipped)
    if not args.skip_ranking:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 2: RANKING SCENES")
        logger.info("=" * 60)

        if args.dry_run:
            logger.info("DRY RUN: Would rank scenes for book: %s", book_slug)
        else:
            with Session(engine) as session:
                scene_repo = SceneExtractionRepository(session)
                scenes = scene_repo.list_for_book(book_slug)

                if not scenes:
                    logger.warning("No scenes found for book: %s", book_slug)
                else:
                    ranking_config = SceneRankingConfig()
                    ranking_service = SceneRankingService(
                        session, config=ranking_config
                    )

                    for scene in scenes:
                        try:
                            result = ranking_service.rank_scene(
                                scene,
                                overwrite=False,
                                dry_run=False,
                            )
                            if result:
                                stats.scenes_ranked += 1
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
    else:
        logger.info("Skipping scene ranking (--skip-ranking)")

    # Step 3: Generate prompts (if not skipped)
    if not args.skip_prompts:
        logger.info("\n" + "=" * 60)
        logger.info("STEP 3: GENERATING PROMPTS")
        logger.info("=" * 60)

        if args.dry_run:
            top_scenes_msg = ""
            if hasattr(args, "prompts_for_scenes") and args.prompts_for_scenes:
                top_scenes_msg = f" for top {args.prompts_for_scenes} scenes"

            if (
                hasattr(args, "prompts_per_scene")
                and args.prompts_per_scene is not None
            ):
                if (
                    hasattr(args, "ignore_ranking_recommendations")
                    and args.ignore_ranking_recommendations
                ):
                    logger.info(
                        "DRY RUN: Would generate %d prompts per scene%s for book: %s (ignoring ranking recommendations)",
                        args.prompts_per_scene,
                        top_scenes_msg,
                        book_slug,
                    )
                else:
                    logger.info(
                        "DRY RUN: Would generate prompts using ranking recommendations (fallback: %d)%s for book: %s",
                        args.prompts_per_scene,
                        top_scenes_msg,
                        book_slug,
                    )
            else:
                logger.info(
                    "DRY RUN: Would generate prompts using ranking recommendations (fallback: 4)%s for book: %s",
                    top_scenes_msg,
                    book_slug,
                )
        else:
            with Session(engine) as session:
                # Get top-ranked scenes without prompts
                ranking_repo = SceneRankingRepository(session)
                prompt_repo = ImagePromptRepository(session)

                # Determine limit based on --prompts-for-scenes parameter
                limit = (
                    args.prompts_for_scenes
                    if hasattr(args, "prompts_for_scenes") and args.prompts_for_scenes
                    else 100
                )

                rankings = ranking_repo.list_top_rankings_for_book(
                    book_slug=book_slug,
                    limit=limit,
                    include_scene=True,
                )

                scenes_needing_prompts = []
                for ranking in rankings:
                    if ranking.scene_extraction:
                        # Check if scene already has prompts
                        existing_prompts = prompt_repo.has_any_for_scene(
                            ranking.scene_extraction.id
                        )
                        if not existing_prompts:
                            scenes_needing_prompts.append(ranking.scene_extraction)

                logger.info(
                    "Found %d scenes needing prompts (out of %d ranked)",
                    len(scenes_needing_prompts),
                    len(rankings),
                )

                if scenes_needing_prompts:
                    # Determine config based on flags
                    config_kwargs = {}

                    if (
                        hasattr(args, "prompts_per_scene")
                        and args.prompts_per_scene is not None
                    ):
                        if (
                            hasattr(args, "ignore_ranking_recommendations")
                            and args.ignore_ranking_recommendations
                        ):
                            # Explicit override mode
                            config_kwargs["variants_count"] = args.prompts_per_scene
                            config_kwargs["use_ranking_recommendation"] = False
                            logger.info(
                                "Using fixed variant count: %d (ignoring rankings)",
                                args.prompts_per_scene,
                            )
                        else:
                            # Fallback for scenes without rankings
                            config_kwargs["variants_count"] = args.prompts_per_scene
                            config_kwargs["use_ranking_recommendation"] = True
                            logger.info(
                                "Using ranking recommendations (fallback: %d variants)",
                                args.prompts_per_scene,
                            )
                    else:
                        # Full auto mode
                        config_kwargs["use_ranking_recommendation"] = True
                        logger.info(
                            "Using ranking recommendations (fallback: 4 variants)"
                        )

                    prompt_config = ImagePromptGenerationConfig(**config_kwargs)
                    prompt_service = ImagePromptGenerationService(
                        session, config=prompt_config
                    )

                    for scene in scenes_needing_prompts:
                        try:
                            prompts = prompt_service.generate_for_scene(
                                scene,
                                dry_run=False,
                                overwrite=False,
                                metadata={"cli": "image_gen_cli"},
                            )
                            if prompts:
                                stats.prompts_generated += len(prompts)
                                logger.info(
                                    "Generated %d prompts for scene %d (chapter %d)",
                                    len(prompts),
                                    scene.scene_number,
                                    scene.chapter_number,
                                )
                        except Exception as exc:
                            error_msg = f"Failed to generate prompts for scene {scene.id}: {exc}"
                            logger.error(error_msg)
                            stats.errors.append(error_msg)

                    logger.info("Generated %d prompts total", stats.prompts_generated)
    else:
        logger.info("Skipping prompt generation (--skip-prompts)")

    # Step 4: Generate images
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: GENERATING IMAGES")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info(
            "DRY RUN: Would generate images for top %d scenes from book: %s",
            args.images_for_scenes,
            book_slug,
        )
    else:
        image_config = ImageGenerationConfig(
            quality=args.quality,
            preferred_style=args.style,
            aspect_ratio=args.aspect_ratio,
            concurrency=3,
        )

        with Session(engine) as session:
            image_service = ImageGenerationService(session, config=image_config)

            try:
                generated_ids = await image_service.generate_for_selection(
                    book_slug=book_slug,
                    top_scenes=args.images_for_scenes,
                    quality=args.quality,
                    preferred_style=args.style,
                    aspect_ratio=args.aspect_ratio,
                    dry_run=False,
                )
                stats.images_generated = len(generated_ids)
                logger.info("Generated %d images", stats.images_generated)
            except Exception as exc:
                error_msg = f"Failed to generate images: {exc}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

    return stats


async def _run_extract(args: argparse.Namespace) -> PipelineStats:
    """Extract scenes from a book."""
    stats = PipelineStats()

    # Require book_path for extraction
    if not args.book_path:
        logger.error("--book-path is required for scene extraction")
        raise ValueError("--book-path is required for scene extraction")

    book_path = Path(args.book_path)

    if args.dry_run:
        logger.info("DRY RUN: Would extract scenes from %s", book_path)
        return stats

    config = SceneExtractionConfig(
        enable_refinement=not args.no_refine,
        book_slug=args.book_slug,
    )
    extractor = SceneExtractor(config=config)
    extraction_stats = extractor.extract_book(book_path)
    stats.scenes_extracted = extraction_stats.get("scenes", 0)

    logger.info("Extraction complete: %d scenes", stats.scenes_extracted)
    return stats


async def _run_rank(args: argparse.Namespace) -> PipelineStats:
    """Rank extracted scenes."""
    stats = PipelineStats()

    if args.dry_run:
        logger.info("DRY RUN: Would rank scenes for book: %s", args.book_slug)
        return stats

    with Session(engine) as session:
        scene_repo = SceneExtractionRepository(session)
        scenes = scene_repo.list_for_book(args.book_slug)

        if args.limit and args.limit > 0:
            scenes = scenes[: args.limit]

        if not scenes:
            logger.warning("No scenes found for book: %s", args.book_slug)
            return stats

        ranking_config = SceneRankingConfig()
        ranking_service = SceneRankingService(session, config=ranking_config)

        for scene in scenes:
            try:
                result = ranking_service.rank_scene(
                    scene,
                    overwrite=args.overwrite,
                    dry_run=False,
                )
                if result:
                    stats.scenes_ranked += 1
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

        logger.info("Ranking complete: %d scenes ranked", stats.scenes_ranked)

    return stats


async def _run_prompts(args: argparse.Namespace) -> PipelineStats:
    """Generate prompts for ranked scenes."""
    stats = PipelineStats()

    if args.dry_run:
        if args.prompts_per_scene is not None:
            if args.ignore_ranking_recommendations:
                logger.info(
                    "DRY RUN: Would generate %d prompts per scene for book: %s (ignoring ranking recommendations)",
                    args.prompts_per_scene,
                    args.book_slug,
                )
            else:
                logger.info(
                    "DRY RUN: Would generate prompts using ranking recommendations (fallback: %d) for book: %s",
                    args.prompts_per_scene,
                    args.book_slug,
                )
        else:
            logger.info(
                "DRY RUN: Would generate prompts using ranking recommendations (fallback: 4) for book: %s",
                args.book_slug,
            )
        return stats

    with Session(engine) as session:
        ranking_repo = SceneRankingRepository(session)
        prompt_repo = ImagePromptRepository(session)

        # Determine limit
        limit = args.top_scenes if args.top_scenes else 100

        rankings = ranking_repo.list_top_rankings_for_book(
            book_slug=args.book_slug,
            limit=limit,
            include_scene=True,
        )

        scenes_to_process = []
        for ranking in rankings:
            if ranking.scene_extraction:
                if args.overwrite:
                    scenes_to_process.append(ranking.scene_extraction)
                else:
                    existing_prompts = prompt_repo.has_any_for_scene(
                        ranking.scene_extraction.id
                    )
                    if not existing_prompts:
                        scenes_to_process.append(ranking.scene_extraction)

        logger.info(
            "Processing %d scenes (out of %d ranked)",
            len(scenes_to_process),
            len(rankings),
        )

        if scenes_to_process:
            # Determine config based on flags
            config_kwargs = {}

            if (
                args.prompts_per_scene is not None
                and args.ignore_ranking_recommendations
            ):
                # Explicit override mode
                config_kwargs["variants_count"] = args.prompts_per_scene
                config_kwargs["use_ranking_recommendation"] = False
                logger.info(
                    "Using fixed variant count: %d (ignoring rankings)",
                    args.prompts_per_scene,
                )
            elif args.prompts_per_scene is not None:
                # Fallback for scenes without rankings
                config_kwargs["variants_count"] = args.prompts_per_scene
                config_kwargs["use_ranking_recommendation"] = True
                logger.info(
                    "Using ranking recommendations (fallback: %d variants)",
                    args.prompts_per_scene,
                )
            else:
                # Full auto mode (use recommendations, fallback to default of 4)
                config_kwargs["use_ranking_recommendation"] = True
                logger.info("Using ranking recommendations (fallback: 4 variants)")

            prompt_config = ImagePromptGenerationConfig(**config_kwargs)
            prompt_service = ImagePromptGenerationService(session, config=prompt_config)

            for scene in scenes_to_process:
                try:
                    prompts = prompt_service.generate_for_scene(
                        scene,
                        dry_run=False,
                        overwrite=args.overwrite,
                        metadata={"cli": "image_gen_cli"},
                    )
                    if prompts:
                        stats.prompts_generated += len(prompts)
                        logger.info(
                            "Generated %d prompts for scene %d (chapter %d)",
                            len(prompts),
                            scene.scene_number,
                            scene.chapter_number,
                        )
                except Exception as exc:
                    error_msg = (
                        f"Failed to generate prompts for scene {scene.id}: {exc}"
                    )
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

            logger.info(
                "Prompt generation complete: %d prompts", stats.prompts_generated
            )

    return stats


async def _run_images(args: argparse.Namespace) -> PipelineStats:
    """Generate images from prompts."""
    stats = PipelineStats()

    if args.dry_run:
        logger.info(
            "DRY RUN: Would generate images for top %d scenes from book: %s",
            args.top_scenes,
            args.book_slug,
        )
        return stats

    image_config = ImageGenerationConfig(
        quality=args.quality,
        preferred_style=args.style,
        aspect_ratio=args.aspect_ratio,
        concurrency=getattr(args, "concurrency", 3),
    )

    with Session(engine) as session:
        image_service = ImageGenerationService(session, config=image_config)

        try:
            generated_ids = await image_service.generate_for_selection(
                book_slug=args.book_slug,
                top_scenes=args.top_scenes,
                quality=args.quality,
                preferred_style=args.style,
                aspect_ratio=args.aspect_ratio,
                dry_run=False,
            )
            stats.images_generated = len(generated_ids)
            logger.info("Image generation complete: %d images", stats.images_generated)
        except Exception as exc:
            error_msg = f"Failed to generate images: {exc}"
            logger.error(error_msg)
            stats.errors.append(error_msg)

    return stats


async def async_main(argv: list[str] | None = None) -> int:
    """Async main entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Route to appropriate handler
    if args.command == "run":
        stats = await _run_full_pipeline(args)
    elif args.command == "extract":
        stats = await _run_extract(args)
    elif args.command == "rank":
        stats = await _run_rank(args)
    elif args.command == "prompts":
        stats = await _run_prompts(args)
    elif args.command == "images":
        stats = await _run_images(args)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(json.dumps(stats.to_dict(), indent=2))

    if stats.errors:
        logger.error("Pipeline completed with %d error(s)", len(stats.errors))
        return 1

    logger.info("Pipeline completed successfully")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
