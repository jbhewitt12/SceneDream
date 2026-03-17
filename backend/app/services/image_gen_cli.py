"""Complete image generation pipeline orchestrator CLI.

This CLI orchestrates the full pipeline from scene extraction through image generation:
1. Extract and refine scenes from a book
2. Rank all extracted scenes
3. Generate prompts for top-ranked scenes
4. Generate images for top-ranked scenes with prompts

Book paths may reference .epub, .mobi/.azw, .txt, .md, or .docx files.

Usage examples:
    # Run full pipeline with automatic variant counts from scene complexity analysis
    uv run python -m app.services.image_gen_cli run --book-slug shogun-james-clavell --book-path "documents/James Clavell/Shogun/Shogun - James Clavell.mobi" --images-for-scenes 5

    # Run full pipeline for top 10 scenes only (prompts and images)
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --book-path "documents/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub" --prompts-for-scenes 10 --images-for-scenes 10

    # Extract and refine only
    uv run python -m app.services.image_gen_cli extract --book-slug look-to-windward-iain-m-banks --book-path "documents/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub"

    # Rank existing scenes (no book-path needed, works from database)
    uv run python -m app.services.image_gen_cli rank --book-slug look-to-windward-iain-m-banks

    # Dry run to preview what would happen
    uv run python -m app.services.image_gen_cli run --book-slug look-to-windward-iain-m-banks --book-path "documents/Iain Banks/Look to Windward/Look to Windward - Iain M. Banks.epub" --images-for-scenes 3 --dry-run

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
from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
)
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.pipeline.orchestrator_config import PipelineStats as PipelineStats
from app.services.scene_extraction.scene_extraction import (
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_ranking.scene_ranking_service import (
    SceneRankingConfig,
    SceneRankingService,
)
from models.scene_extraction import SceneExtraction

logger = logging.getLogger(__name__)


def _extract_book_with_session(
    config: SceneExtractionConfig,
    book_path: Path,
) -> dict[str, object]:
    with Session(engine) as session:
        extractor = SceneExtractor(session=session, config=config)
        stats = extractor.extract_book(book_path)
        session.commit()
        return stats


def _filter_scenes_for_ranking(
    *,
    session: Session,
    scenes: list[SceneExtraction],
    book_slug: str,
    ranking_service: SceneRankingService,
    overwrite: bool,
    limit: int | None = None,
) -> list[SceneExtraction]:
    """Return the subset of scenes that still require ranking."""
    if not scenes:
        return []

    selected = scenes
    if not overwrite:
        ranking_repo = SceneRankingRepository(session)
        weight_hash = ranking_service.effective_weight_hash()
        ranked_ids = ranking_repo.list_ranked_scene_ids_for_book(
            book_slug=book_slug,
            model_name=ranking_service.config.model_name,
            prompt_version=ranking_service.config.prompt_version,
            weight_config_hash=weight_hash,
        )
        if ranked_ids:
            total_scenes = len(scenes)
            total_ranked = sum(1 for scene in scenes if scene.id in ranked_ids)
            if total_ranked:
                logger.info(
                    "%d of %d scenes already ranked for '%s' with current configuration.",
                    total_ranked,
                    total_scenes,
                    book_slug,
                )
            first_unranked_index = next(
                (idx for idx, scene in enumerate(scenes) if scene.id not in ranked_ids),
                None,
            )
            if first_unranked_index is None:
                logger.info(
                    "No unranked scenes remain for '%s'; skipping ranking step.",
                    book_slug,
                )
                return []
            resume_scene = scenes[first_unranked_index]
            if first_unranked_index > 0:
                logger.info(
                    "Resuming ranking at chapter %d scene %d.",
                    resume_scene.chapter_number,
                    resume_scene.scene_number,
                )
            selected = [scene for scene in scenes if scene.id not in ranked_ids]

    if limit and limit > 0:
        selected = selected[:limit]

    return selected


async def _run_full_pipeline(
    args: argparse.Namespace,
) -> PipelineStats:
    """Run the complete pipeline via the orchestrator."""
    from app.services.pipeline import (
        DocumentTarget,
        ImageExecutionOptions,
        PipelineExecutionConfig,
        PipelineOrchestrator,
        PipelineRunStartService,
        PipelineStagePlan,
        PromptExecutionOptions,
    )

    book_slug = args.book_slug
    book_path = getattr(args, "book_path", None)

    if args.dry_run:
        stats = PipelineStats()
        skip_extraction = getattr(args, "skip_extraction", False)
        skip_ranking = getattr(args, "skip_ranking", False)
        skip_prompts = getattr(args, "skip_prompts", False)
        images_for_scenes = getattr(args, "images_for_scenes", None)

        if not skip_extraction:
            logger.info("DRY RUN: Would extract scenes from %s", book_path)
        if not skip_ranking:
            logger.info("DRY RUN: Would rank scenes for book: %s", book_slug)
        if not skip_prompts:
            logger.info("DRY RUN: Would generate prompts for book: %s", book_slug)
            logger.info(
                "DRY RUN: Would generate images for top %s scenes from book: %s",
                images_for_scenes,
                book_slug,
            )
        return stats

    run_prompts = not getattr(args, "skip_prompts", False)
    target = DocumentTarget(
        book_slug=book_slug,
        book_path=book_path,
    )
    stages = PipelineStagePlan(
        run_extraction=not getattr(args, "skip_extraction", False),
        run_ranking=not getattr(args, "skip_ranking", False),
        run_prompt_generation=run_prompts,
        run_image_generation=run_prompts,
    )
    prompt_options = PromptExecutionOptions(
        prompts_per_scene=getattr(args, "prompts_per_scene", None),
        ignore_ranking_recommendations=getattr(
            args, "ignore_ranking_recommendations", False
        ),
        prompts_for_scenes=getattr(args, "prompts_for_scenes", None),
        images_for_scenes=getattr(args, "images_for_scenes", None),
        prompt_art_style_mode=getattr(args, "prompt_art_style_mode", None),
        prompt_art_style_text=getattr(args, "prompt_art_style_text", None),
    )
    image_options = ImageExecutionOptions(
        quality=getattr(args, "quality", "standard"),
        style=getattr(args, "style", None),
        aspect_ratio=getattr(args, "aspect_ratio", None),
    )
    config = PipelineExecutionConfig(
        target=target,
        stages=stages,
        prompt_options=prompt_options,
        image_options=image_options,
    )

    with Session(engine) as session:
        service = PipelineRunStartService(session)
        prepared = service.prepare_execution(config)

    orchestrator = PipelineOrchestrator()
    result = await orchestrator.execute(prepared)

    return result.stats


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
    loop = asyncio.get_running_loop()
    extraction_stats = await loop.run_in_executor(
        None,
        _extract_book_with_session,
        config,
        book_path,
    )
    scenes_count = extraction_stats.get("scenes", 0)
    stats.scenes_extracted = scenes_count if isinstance(scenes_count, int) else 0

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

        if not scenes:
            logger.warning("No scenes found for book: %s", args.book_slug)
            return stats

        ranking_config = SceneRankingConfig()
        ranking_service = SceneRankingService(session, config=ranking_config)

        scenes_to_rank = _filter_scenes_for_ranking(
            session=session,
            scenes=scenes,
            book_slug=args.book_slug,
            ranking_service=ranking_service,
            overwrite=args.overwrite,
            limit=args.limit,
        )

        if not scenes_to_rank:
            logger.info(
                "No scenes require ranking for book: %s (overwrite=%s)",
                args.book_slug,
                args.overwrite,
            )
            return stats

        for scene in scenes_to_rank:
            try:
                result = await ranking_service.rank_scene(
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
        help="Number of top-ranked scenes to generate prompts for (default: match --images-for-scenes)",
    )
    run.add_argument(
        "--images-for-scenes",
        type=int,
        default=None,
        help="Number of top-ranked scenes to generate images for (default: app settings value)",
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
    _add_prompt_art_style_args(run)
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

    return parser


def _add_book_args(parser: argparse.ArgumentParser) -> None:
    """Add book-related arguments."""
    parser.add_argument(
        "--book-slug",
        help="Book slug (e.g., look-to-windward-iain-m-banks). If provided without --book-path, book extraction will be skipped.",
    )
    parser.add_argument(
        "--book-path",
        help="Path to source document file for scene extraction. Can be absolute or relative to project root.",
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


def _add_prompt_art_style_args(parser: argparse.ArgumentParser) -> None:
    """Add prompt art style mode/text arguments."""
    parser.add_argument(
        "--prompt-art-style-mode",
        choices=[
            PROMPT_ART_STYLE_MODE_RANDOM_MIX,
            PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
        ],
        help="Prompt art style mode: random mix or one fixed style for all variants",
    )
    parser.add_argument(
        "--prompt-art-style-text",
        help="Required when --prompt-art-style-mode is single_style",
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
