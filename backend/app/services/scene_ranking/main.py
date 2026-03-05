"""Scene ranking CLI entry point.

Usage examples:
    uv run python -m app.services.scene_ranking.main rank --book-slug excession-iain-m-banks
    uv run python -m app.services.scene_ranking.main rank --scene-id <uuid> --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.db import engine
from app.repositories import SceneExtractionRepository
from app.services.langchain.model_routing import infer_provider_from_model_name
from app.services.scene_ranking import (
    SceneRankingConfig,
    SceneRankingPreview,
    SceneRankingService,
    SceneRankingServiceError,
)
from models.scene_ranking import SceneRanking

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scene ranking utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rank = subparsers.add_parser(
        "rank", help="Run scene rankings for a book, chapter, or specific scenes."
    )
    rank.add_argument(
        "--book-slug",
        type=str,
        help="Book slug to target when ranking scenes.",
    )
    rank.add_argument(
        "--chapter",
        type=int,
        help="Optional chapter number to restrict the ranking scope.",
    )
    rank.add_argument(
        "--scene-id",
        action="append",
        type=lambda value: UUID(value),
        help="Explicit scene extraction IDs to rank (can be passed multiple times).",
    )
    rank.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of scenes to process (ignored when --scene-id is used).",
    )
    rank.add_argument(
        "--model-name",
        type=str,
        help="Override the default model name (e.g., gemini-2.5-pro).",
    )
    rank.add_argument(
        "--prompt-version",
        type=str,
        help="Override the prompt template version identifier.",
    )
    rank.add_argument(
        "--temperature",
        type=float,
        help="Override the sampling temperature for LLM calls.",
    )
    rank.add_argument(
        "--max-output-tokens",
        type=int,
        help="Override the maximum tokens the LLM may return (default uses model limit).",
    )
    rank.add_argument(
        "--weight",
        action="append",
        default=[],
        help="Weight override in the form criterion=value (can be repeated).",
    )
    rank.add_argument(
        "--dry-run",
        action="store_true",
        help="Return previews without persisting rankings.",
    )
    rank.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing rankings that match the weight hash.",
    )
    rank.add_argument(
        "--include-discarded",
        action="store_true",
        help="Rank scenes even if refinement marked them as discarded.",
    )
    rank.add_argument(
        "--operator",
        type=str,
        help="Operator name for run metadata.",
    )
    rank.add_argument(
        "--note",
        type=str,
        help="Optional free-form note to store with run metadata.",
    )
    rank.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit immediately if any ranking attempt fails.",
    )

    return parser


def _parse_weights(raw_weights: Iterable[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for entry in raw_weights:
        if "=" not in entry:
            raise ValueError(
                f"Weight override must be in the form criterion=value (got: {entry!r})"
            )
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(
                f"Weight override must include both key and value (got: {entry!r})"
            )
        overrides[key] = float(value)
    return overrides


def _collect_scenes(
    *,
    session: Session,
    scene_ids: list[UUID] | None,
    book_slug: str | None,
    chapter: int | None,
    limit: int,
) -> list[Any]:
    repository = SceneExtractionRepository(session)
    if scene_ids:
        scenes = []
        for scene_id in scene_ids:
            scene = repository.get(scene_id)
            if scene is None:
                logger.warning("Scene %s was not found and will be skipped.", scene_id)
                continue
            scenes.append(scene)
        return scenes
    if not book_slug:
        raise ValueError("--book-slug is required when --scene-id is not provided")
    scenes = repository.list_for_book(book_slug, chapter_number=chapter)
    if limit > 0:
        scenes = scenes[:limit]
    return scenes


def _build_metadata(operator: str | None, note: str | None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "cli": "scene-ranking",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv[1:],
    }
    if operator:
        metadata["operator"] = operator
    if note:
        metadata["note"] = note
    return metadata


def _summarize_result(result: SceneRanking | SceneRankingPreview) -> dict[str, object]:
    base = {
        "scene_extraction_id": str(result.scene_extraction_id),
        "overall_priority": result.overall_priority,
        "model_name": result.model_name,
        "prompt_version": result.prompt_version,
        "weight_config_hash": result.weight_config_hash,
        "execution_time_ms": result.execution_time_ms,
    }
    if isinstance(result, SceneRanking):
        base.update(
            {
                "ranking_id": str(result.id),
                "justification": result.justification,
                "committed": True,
            }
        )
    else:
        base.update(
            {
                "ranking_id": None,
                "justification": result.justification,
                "committed": False,
            }
        )

    # Add complexity fields if present
    if (
        hasattr(result, "recommended_prompt_count")
        and result.recommended_prompt_count is not None
    ):
        base["recommended_prompt_count"] = result.recommended_prompt_count
    if (
        hasattr(result, "complexity_rationale")
        and result.complexity_rationale is not None
    ):
        base["complexity_rationale"] = result.complexity_rationale
    if (
        hasattr(result, "distinct_visual_moments")
        and result.distinct_visual_moments is not None
    ):
        base["distinct_visual_moments"] = result.distinct_visual_moments

    return base


async def _handle_rank(args: argparse.Namespace) -> int:
    try:
        weight_overrides = _parse_weights(args.weight)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    config_kwargs: dict[str, Any] = {
        "skip_discarded_scenes": not args.include_discarded,
        "fail_on_error": args.fail_on_error,
    }
    if args.model_name:
        config_kwargs["model_name"] = args.model_name
        inferred_vendor = infer_provider_from_model_name(args.model_name)
        if inferred_vendor is not None:
            config_kwargs["model_vendor"] = inferred_vendor
            if inferred_vendor == "openai":
                config_kwargs["backup_model_vendor"] = "google"
                config_kwargs["backup_model_name"] = "gemini-2.5-flash-lite"
            else:
                config_kwargs["backup_model_vendor"] = "openai"
                config_kwargs["backup_model_name"] = "gpt-5-mini"
    if args.prompt_version:
        config_kwargs["prompt_version"] = args.prompt_version
    if args.temperature is not None:
        config_kwargs["temperature"] = args.temperature
    if args.max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = args.max_output_tokens
    if weight_overrides:
        config_kwargs["weight_config"] = weight_overrides

    config = SceneRankingConfig(**config_kwargs)
    metadata = _build_metadata(args.operator, args.note)

    with Session(engine) as session:
        service = SceneRankingService(session, config=config)
        try:
            scenes = _collect_scenes(
                session=session,
                scene_ids=args.scene_id,
                book_slug=args.book_slug,
                chapter=args.chapter,
                limit=args.limit,
            )
        except ValueError as exc:
            logger.error("%s", exc)
            return 2

        if not scenes:
            logger.info("No scenes matched the provided filters.")
            return 0

        total_scenes = len(scenes)
        results: list[dict[str, object]] = []
        for idx, scene in enumerate(scenes, start=1):
            try:
                outcome = await service.rank_scene(
                    scene,
                    dry_run=args.dry_run,
                    overwrite=args.overwrite,
                    metadata=metadata,
                )
            except SceneRankingServiceError as exc:
                logger.error("Failed to rank scene %s: %s", scene.id, exc)
                if args.fail_on_error:
                    return 1
                continue
            if outcome is None:
                logger.info(
                    "Skipped scene %s based on service configuration.", scene.id
                )
                continue
            results.append(_summarize_result(outcome))

            # Progress update every 10 scenes
            if idx % 10 == 0:
                print(f"{idx} of {total_scenes} scenes ranked", file=sys.stderr)

    print(json.dumps(results, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "rank":
        return asyncio.run(_handle_rank(args))
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
