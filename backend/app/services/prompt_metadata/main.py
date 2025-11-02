"""CLI utilities for prompt metadata backfill."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime
from typing import Iterator, Sequence

from sqlmodel import Session

from app.core.db import engine
from app.repositories.image_prompt import ImagePromptRepository
from app.services.prompt_metadata.prompt_metadata_service import (
    PromptMetadataConfig,
    PromptMetadataGenerationService,
)

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prompt metadata generation utilities",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill = subparsers.add_parser(
        "backfill",
        help="Generate title + flavour text for existing image prompts.",
    )
    backfill.add_argument(
        "--book-slug",
        type=str,
        help="Optional book slug to scope prompts.",
    )
    backfill.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of prompts to process (default: all).",
    )
    backfill.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of prompts to process per batch (default: 10).",
    )
    backfill.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate metadata even if fields already exist.",
    )
    backfill.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview metadata without writing to the database.",
    )
    backfill.add_argument(
        "--created-after",
        type=str,
        help="Filter prompts created on/after this ISO timestamp (e.g., 2024-10-25T00:00:00).",
    )
    return parser


def _batched(sequence: Sequence, size: int) -> Iterator[Sequence]:
    size = max(size, 1)
    for start in range(0, len(sequence), size):
        yield sequence[start : start + size]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argument validation
        raise SystemExit(f"Invalid --created-after value: {value}") from exc


async def _handle_backfill(args: argparse.Namespace) -> int:
    created_after = _parse_timestamp(args.created_after)
    with Session(engine) as session:
        repository = ImagePromptRepository(session)
        prompts = repository.list_for_metadata(
            book_slug=args.book_slug,
            limit=args.limit,
            created_after=created_after,
            missing_metadata=not args.overwrite,
        )
        total = len(prompts)
        if not prompts:
            summary = {
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "skipped": 0,
                "dryRun": args.dry_run,
            }
            print(json.dumps(summary, indent=2))
            return 0

        service = PromptMetadataGenerationService(
            session,
            PromptMetadataConfig(
                fail_on_error=False,
                dry_run=args.dry_run,
            ),
        )

        processed = 0
        updated = 0
        failed = 0
        skipped = 0

        for batch in _batched(prompts, args.batch_size):
            results = await service.generate_metadata_for_prompts(
                batch,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
            processed += len(batch)
            if results is None:
                failed += len(batch)
            else:
                for result in results:
                    if result is None:
                        failed += 1
                    elif isinstance(result, dict) and result.get("skipped"):
                        skipped += 1
                    else:
                        updated += 1
            if not args.dry_run:
                session.commit()
            logger.info("Processed %s/%s prompts", processed, total)

        summary = {
            "processed": processed,
            "updated": updated,
            "failed": failed,
            "skipped": skipped,
            "dryRun": args.dry_run,
            "bookSlug": args.book_slug,
        }
        print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "backfill":
        return asyncio.run(_handle_backfill(args))
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
