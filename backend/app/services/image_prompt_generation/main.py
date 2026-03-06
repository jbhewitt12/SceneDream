"""Image prompt generation CLI entry point.

Usage examples:

    preview full prompt for a random scene:
    uv run python -m app.services.image_prompt_generation.main preview

    uv run python -m app.services.image_prompt_generation.main run --limit 10
    uv run python -m app.services.image_prompt_generation.main run --book-slug excession-iain-m-banks --limit 5
    uv run python -m app.services.image_prompt_generation.main run --dry-run --variants 2
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

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.db import engine
from app.repositories import ImagePromptRepository, SceneRankingRepository
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
)
from app.services.image_prompt_generation.models import ImagePromptPreview
from app.services.langchain.model_routing import infer_provider_from_model_name
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Image prompt generation utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help=(
            "Generate prompts for highest-ranked scenes that lack prompts. "
            "By default, looks across all books unless --book-slug is provided."
        ),
    )
    run.add_argument(
        "--book-slug",
        type=str,
        help="Optional book slug to restrict the scope.",
    )
    run.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of scenes to consider (after filtering).",
    )
    run.add_argument(
        "--variants",
        type=int,
        default=3,
        help="Number of prompt variants to generate per scene (default: 3).",
    )
    run.add_argument(
        "--model-name",
        type=str,
        help="Override the generation model name (e.g., gemini-2.5-pro).",
    )
    run.add_argument(
        "--prompt-version",
        type=str,
        help="Override the prompt template version identifier.",
    )
    run.add_argument(
        "--temperature",
        type=float,
        help="Override the sampling temperature for LLM calls.",
    )
    run.add_argument(
        "--max-output-tokens",
        type=int,
        help="Override the maximum tokens the LLM may return.",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Return previews without persisting prompts.",
    )
    run.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing prompt variants for a scene.",
    )
    run.add_argument(
        "--operator",
        type=str,
        help="Operator name for run metadata.",
    )
    run.add_argument(
        "--note",
        type=str,
        help="Optional free-form note to store with run metadata.",
    )
    run.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit immediately if any generation attempt fails.",
    )
    preview = subparsers.add_parser(
        "preview",
        help=(
            "Print the raw prompt text that would be sent to the LLM for a random scene."
        ),
    )
    preview.add_argument(
        "--book-slug",
        type=str,
        help="Optional book slug to limit the random scene selection.",
    )
    preview.add_argument(
        "--variants",
        type=int,
        help="Override the number of variants (disables ranking recommendation).",
    )
    preview.add_argument(
        "--prompt-version",
        type=str,
        help="Override the prompt template version identifier.",
    )
    preview.add_argument(
        "--temperature",
        type=float,
        help="Override the sampling temperature reflected in the prompt metadata.",
    )
    preview.add_argument(
        "--max-output-tokens",
        type=int,
        help="Override the maximum tokens reflected in the prompt metadata.",
    )
    preview.add_argument(
        "--context-before",
        type=int,
        help="Override the number of context paragraphs before the scene.",
    )
    preview.add_argument(
        "--context-after",
        type=int,
        help="Override the number of context paragraphs after the scene.",
    )

    return parser


def _build_metadata(operator: str | None, note: str | None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "cli": "image-prompt-generation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv[1:],
    }
    if operator:
        metadata["operator"] = operator
    if note:
        metadata["note"] = note
    return metadata


def _collect_ranked_scenes(
    *,
    session: Session,
    book_slug: str | None,
    limit: int,
) -> list[SceneExtraction]:
    ranking_repo = SceneRankingRepository(session)
    if book_slug:
        rankings = ranking_repo.list_top_rankings_for_book(
            book_slug=book_slug, limit=limit, include_scene=True
        )
    else:
        rankings = ranking_repo.list_top_rankings(limit=limit, include_scene=True)
    scenes: list[SceneExtraction] = []
    seen: set[UUID] = set()
    for r in rankings:
        scene = r.scene_extraction
        if scene is None:
            continue
        if scene.id in seen:
            continue
        scenes.append(scene)
        seen.add(scene.id)
        if len(scenes) >= limit:
            break
    return scenes


def _filter_scenes_without_prompts(
    *,
    session: Session,
    scenes: Iterable[SceneExtraction],
) -> list[SceneExtraction]:
    repo = ImagePromptRepository(session)
    result: list[SceneExtraction] = []
    for scene in scenes:
        # Skip scenes that have any prompts already, regardless of model/prompt version
        if not repo.has_any_for_scene(scene.id):
            result.append(scene)
    return result


def _summarize_prompts(
    scene: SceneExtraction, prompts: list[ImagePrompt] | list[ImagePromptPreview] | None
) -> dict[str, object]:
    base = {
        "scene_extraction_id": str(scene.id),
        "book_slug": scene.book_slug,
        "chapter": scene.chapter_number,
        "scene_number": scene.scene_number,
    }
    if not prompts:
        base.update({"generated": 0})
        return base
    if isinstance(prompts[0], ImagePrompt):
        # Type narrowing: at this point all elements are ImagePrompt
        image_prompts = [p for p in prompts if isinstance(p, ImagePrompt)]
        return {
            **base,
            "generated": len(prompts),
            "prompt_ids": [str(p.id) for p in image_prompts],
            "committed": True,
        }
    return {
        **base,
        "generated": len(prompts),
        "committed": False,
    }


def _pick_random_scene(
    session: Session,
    *,
    book_slug: str | None = None,
) -> SceneExtraction | None:
    statement = select(SceneExtraction).order_by(func.random()).limit(1)
    if book_slug:
        statement = statement.where(SceneExtraction.book_slug == book_slug)
    return session.exec(statement).first()


async def _handle_run(args: argparse.Namespace) -> int:
    config_kwargs: dict[str, Any] = {}
    if args.model_name:
        config_kwargs["model_name"] = args.model_name
        inferred_vendor = infer_provider_from_model_name(args.model_name)
        if inferred_vendor is not None:
            config_kwargs["model_vendor"] = inferred_vendor
            if inferred_vendor == "openai":
                config_kwargs["backup_model_vendor"] = "google"
                config_kwargs["backup_model_name"] = "gemini-3-pro-preview"
            else:
                config_kwargs["backup_model_vendor"] = "openai"
                config_kwargs["backup_model_name"] = "gpt-5-mini"
    if args.prompt_version:
        config_kwargs["prompt_version"] = args.prompt_version
    if args.temperature is not None:
        config_kwargs["temperature"] = args.temperature
    if args.max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = args.max_output_tokens
    # default variants to 3 unless explicitly overridden
    config_kwargs["variants_count"] = int(args.variants)

    config = ImagePromptGenerationConfig(**config_kwargs)
    metadata = _build_metadata(args.operator, args.note)

    with Session(engine) as session:
        service = ImagePromptGenerationService(session, config=config)

        ranked_scenes = _collect_ranked_scenes(
            session=session, book_slug=args.book_slug, limit=args.limit
        )
        if not ranked_scenes:
            logger.info("No ranked scenes found to process.")
            print(json.dumps([], indent=2))
            return 0

        candidate_scenes = _filter_scenes_without_prompts(
            session=session,
            scenes=ranked_scenes,
        )
        if not candidate_scenes:
            logger.info("All candidate scenes already have prompts.")
            print(json.dumps([], indent=2))
            return 0

        results: list[dict[str, object]] = []
        for scene in candidate_scenes:
            try:
                prompts = await service.generate_for_scene(
                    scene,
                    dry_run=args.dry_run,
                    overwrite=args.overwrite,
                    metadata=metadata,
                )
            except ImagePromptGenerationServiceError as exc:
                logger.error("Failed to generate prompts for %s: %s", scene.id, exc)
                if args.fail_on_error:
                    return 1
                continue
            results.append(_summarize_prompts(scene, prompts))

    print(json.dumps(results, indent=2, default=str))
    return 0


def _handle_preview(args: argparse.Namespace) -> int:
    config_kwargs: dict[str, Any] = {}
    if args.prompt_version:
        config_kwargs["prompt_version"] = args.prompt_version
    if args.temperature is not None:
        config_kwargs["temperature"] = args.temperature
    if args.max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = args.max_output_tokens
    if args.context_before is not None:
        config_kwargs["context_before"] = args.context_before
    if args.context_after is not None:
        config_kwargs["context_after"] = args.context_after
    if args.variants is not None:
        config_kwargs["variants_count"] = int(args.variants)
        config_kwargs["use_ranking_recommendation"] = False

    config = ImagePromptGenerationConfig(**config_kwargs)

    with Session(engine) as session:
        service = ImagePromptGenerationService(session, config=config)
        last_error: Exception | None = None
        for _ in range(5):
            scene = _pick_random_scene(session, book_slug=args.book_slug)
            if scene is None:
                break
            try:
                prompt, *_ = service.render_prompt_template(
                    scene,
                    prompt_version=args.prompt_version,
                    variants_count=args.variants,
                    temperature=args.temperature,
                    max_output_tokens=args.max_output_tokens,
                )
                print(prompt)
                return 0
            except ImagePromptGenerationServiceError as exc:
                last_error = exc
                logger.info(
                    "Skipping scene %s for preview due to validation error: %s",
                    getattr(scene, "id", "unknown"),
                    exc,
                )
                continue

    if last_error is not None:
        logger.error("Unable to render prompt preview: %s", last_error)
    else:
        logger.error("No scenes available for prompt preview.")
    return 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return asyncio.run(_handle_run(args))
    if args.command == "preview":
        return _handle_preview(args)
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
