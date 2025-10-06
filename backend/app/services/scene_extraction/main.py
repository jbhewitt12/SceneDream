"""Scene extraction CLI entry point.

To run: uv run python -m app.services.scene_extraction.main preview-excession <no. of chapters>
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from app.services.scene_extraction.scene_extraction import (
    EXCESSION_EPUB_PATH,
    SceneExtractionConfig,
    SceneExtractor,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SceneDream convenience CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser(
        "preview-excession",
        help="Extract scenes from the first N chapters of Excession.",
    )
    preview.add_argument(
        "chapters",
        type=int,
        help="Number of leading chapters to process.",
    )
    preview.add_argument(
        "--refine",
        action="store_true",
        help="Enable refinement when extracting.",
    )

    full = subparsers.add_parser(
        "extract-excession",
        help="Extract scenes from the entire Excession EPUB.",
    )
    full.add_argument(
        "--refine",
        action="store_true",
        help="Enable refinement when extracting.",
    )

    return parser


def _create_extractor(enable_refinement: bool) -> SceneExtractor:
    config = SceneExtractionConfig(enable_refinement=enable_refinement)
    return SceneExtractor(config=config)


def _handle_preview(chapters: int, enable_refinement: bool) -> dict[str, object]:
    extractor = _create_extractor(enable_refinement)
    chapters_to_process = max(chapters, 0)
    return extractor.extract_preview(
        EXCESSION_EPUB_PATH,
        max_chapters=chapters_to_process,
        max_chunks_per_chapter=0,
    )


def _handle_full(enable_refinement: bool) -> dict[str, object]:
    extractor = _create_extractor(enable_refinement)
    return extractor.extract_book(EXCESSION_EPUB_PATH)


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "preview-excession":
        stats = _handle_preview(args.chapters, args.refine)
    elif args.command == "extract-excession":
        stats = _handle_full(args.refine)
    else:
        parser.error("Unknown command")
        return 2

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
