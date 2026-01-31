"""Image generation CLI entry point.

Usage examples (run from backend/ directory):
    # Generate images for the top 10 scenes by ranking (skips scenes with existing images)
    uv run python -m app.services.image_generation.main --book excession-iain-m-banks --top-scenes 10

    # Preview what will be generated for top scenes
    uv run python -m app.services.image_generation.main --book excession-iain-m-banks --top-scenes 10 --dry-run

    # Generate images for top 5 scenes with HD quality
    uv run python -m app.services.image_generation.main --book excession-iain-m-banks --top-scenes 5 --quality hd --style vivid

    # Generate images for a book with limit
    uv run python -m app.services.image_generation.main --book excession-iain-m-banks --limit 10 --dry-run

    # Generate images for specific scenes with HD quality
    uv run python -m app.services.image_generation.main --scene-ids <uuid1>,<uuid2> --quality hd --style vivid

    # Generate images for a chapter range with specific aspect ratio
    uv run python -m app.services.image_generation.main --book excession-iain-m-banks --chapter-range 1:5 --aspect-ratio 16:9

    # Generate images for specific prompts
    uv run python -m app.services.image_generation.main --prompt-ids <uuid1>,<uuid2>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
    ImageGenerationServiceError,
)

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate images from prompts using DALL·E 3. "
        "Filters can be combined to select specific prompts."
    )

    # Selection filters
    parser.add_argument(
        "--book",
        "--book-slug",
        dest="book_slug",
        type=str,
        help="Filter by book slug (e.g., excession-iain-m-banks).",
    )
    parser.add_argument(
        "--chapter-range",
        type=str,
        help="Filter by chapter range in format 'start:end' (e.g., '1:5' for chapters 1-4, inclusive start, exclusive end).",
    )
    parser.add_argument(
        "--scene-ids",
        type=str,
        help="Comma-separated list of scene extraction UUIDs.",
    )
    parser.add_argument(
        "--prompt-ids",
        type=str,
        help="Comma-separated list of image prompt UUIDs.",
    )
    parser.add_argument(
        "--top-scenes",
        type=int,
        help="Generate images for the top N scenes by overall_priority ranking. "
        "Automatically skips scenes that already have generated images. "
        "Requires --book to be specified.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of images to generate.",
    )

    # Image generation parameters
    parser.add_argument(
        "--quality",
        type=str,
        choices=["standard", "hd"],
        default="standard",
        help="Image quality (default: standard).",
    )
    parser.add_argument(
        "--style",
        "--preferred-style",
        dest="preferred_style",
        type=str,
        choices=["vivid", "natural"],
        help="Preferred style override (default: derived from prompt style_tags).",
    )
    parser.add_argument(
        "--aspect-ratio",
        type=str,
        choices=["1:1", "9:16", "16:9"],
        help="Aspect ratio (default: derived from prompt attributes or 1:1).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        help="Image generation provider (default: openai).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="dall-e-3",
        help="Model to use (default: dall-e-3).",
    )
    parser.add_argument(
        "--response-format",
        type=str,
        choices=["b64_json", "url"],
        default="b64_json",
        help="Response format (default: b64_json).",
    )

    # Execution control
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent generation tasks (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned operations without executing API calls.",
    )

    # API configuration
    parser.add_argument(
        "--api-key",
        type=str,
        help="OpenAI API key (default: OPENAI_API_KEY environment variable).",
    )

    return parser


def _parse_chapter_range(range_str: str) -> tuple[int, int]:
    """Parse chapter range string in format 'start:end'."""
    try:
        parts = range_str.split(":")
        if len(parts) != 2:
            raise ValueError("Chapter range must be in format 'start:end'")
        start = int(parts[0])
        end = int(parts[1])
        if start < 0 or end < 0 or start >= end:
            raise ValueError(
                "Invalid chapter range (start must be < end and both >= 0)"
            )
        return (start, end)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid chapter range: {exc}") from exc


def _parse_uuid_list(uuid_str: str) -> list[UUID]:
    """Parse comma-separated list of UUIDs."""
    try:
        return [UUID(s.strip()) for s in uuid_str.split(",") if s.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid UUID in list: {exc}") from exc


async def _handle_generate(args: argparse.Namespace) -> int:
    """Handle the generate command."""
    # Validate top-scenes requires book
    if args.top_scenes and not args.book_slug:
        logger.error("--top-scenes requires --book to be specified")
        return 1

    # Parse selection filters
    chapter_range = None
    if args.chapter_range:
        chapter_range = _parse_chapter_range(args.chapter_range)

    scene_ids = None
    if args.scene_ids:
        scene_ids = _parse_uuid_list(args.scene_ids)

    prompt_ids = None
    if args.prompt_ids:
        prompt_ids = _parse_uuid_list(args.prompt_ids)

    # Validate API key (check args, then settings, then os.environ as fallback)
    api_key = args.api_key or settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        logger.error(
            "OPENAI_API_KEY environment variable or --api-key argument required for image generation"
        )
        return 1

    # Create configuration
    config = ImageGenerationConfig(
        provider=args.provider,
        model=args.model,
        quality=args.quality,
        preferred_style=args.preferred_style,
        aspect_ratio=args.aspect_ratio,
        response_format=args.response_format,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        api_key=api_key,
    )

    # Run generation
    with Session(engine) as session:
        service = ImageGenerationService(session, config=config, api_key=api_key)

        try:
            generated_ids = await service.generate_for_selection(
                book_slug=args.book_slug,
                chapter_range=chapter_range,
                scene_ids=scene_ids,
                prompt_ids=prompt_ids,
                top_scenes=args.top_scenes,
                limit=args.limit,
                quality=args.quality,
                preferred_style=args.preferred_style,
                aspect_ratio=args.aspect_ratio,
                provider=args.provider,
                model=args.model,
                response_format=args.response_format,
                concurrency=args.concurrency,
                dry_run=args.dry_run,
            )

            # Output results
            if args.dry_run:
                logger.info("Dry-run completed. No images generated.")
                result = {
                    "dry_run": True,
                    "message": "See logs above for planned operations",
                }
            else:
                logger.info("Generated %d images", len(generated_ids))
                result = {
                    "generated_count": len(generated_ids),
                    "generated_ids": [str(gid) for gid in generated_ids],
                }

            print(json.dumps(result, indent=2))
            return 0

        except ImageGenerationServiceError as exc:
            logger.error("Image generation failed: %s", exc)
            return 1
        except Exception as exc:
            logger.exception("Unexpected error during image generation: %s", exc)
            return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the image generation CLI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Trigger settings loading (which automatically loads .env from project root)
    # This ensures environment variables are available via os.getenv()
    _ = settings.ENVIRONMENT

    parser = _build_parser()
    args = parser.parse_args(argv)

    return asyncio.run(_handle_generate(args))


if __name__ == "__main__":
    raise SystemExit(main())
