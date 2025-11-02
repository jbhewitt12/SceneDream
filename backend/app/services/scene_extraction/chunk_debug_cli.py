from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

from app.services.scene_extraction.scene_extraction import (
    Chapter,
    ChapterChunk,
    SceneExtractionConfig,
    SceneExtractor,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect chapter chunks exactly as sent to the LLM."
    )
    parser.add_argument(
        "--book-path",
        required=True,
        help="Path to the source book file (EPUB or MOBI).",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=None,
        help="Limit the number of chapters to inspect (1-indexed order).",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        nargs="+",
        default=None,
        help="Specific chapter numbers to include.",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=None,
        help="Limit how many chunks are displayed per chapter.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=2,
        help="Paragraph overlap between successive chunks.",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=12000,
        help="Maximum characters per chunk (matches extractor config).",
    )
    parser.add_argument(
        "--show-prompts",
        action="store_true",
        help="Print the full LLM prompt for each chunk.",
    )
    parser.add_argument(
        "--show-paragraphs",
        action="store_true",
        help="Print the numbered paragraphs for each chunk.",
    )
    parser.add_argument(
        "--book-slug",
        default=None,
        help="Optional slug override to match existing extractor runs.",
    )
    return parser


def _filter_chapters(
    chapters: Sequence[Chapter],
    *,
    include_numbers: Sequence[int] | None,
    max_chapters: int | None,
) -> list[Chapter]:
    filtered = list(chapters)
    if include_numbers:
        allowed = set(include_numbers)
        filtered = [chapter for chapter in chapters if chapter.number in allowed]
    if max_chapters is not None:
        filtered = filtered[: max(0, max_chapters)]
    return filtered


def _iter_chunks(
    extractor: SceneExtractor,
    chapter: Chapter,
) -> Iterable[ChapterChunk]:
    chunks = extractor._chunk_chapter(chapter)
    for chunk in chunks:
        yield chunk


def _format_prompt(extractor: SceneExtractor, chunk: ChapterChunk) -> str:
    return extractor._build_chunk_prompt(chunk)


def inspect_book_chunks(args: argparse.Namespace) -> int:
    config = SceneExtractionConfig(
        max_chunk_chars=max(args.max_chunk_chars, 1000),
        chunk_overlap_paragraphs=max(args.chunk_overlap, 0),
        book_slug=args.book_slug,
        enable_refinement=False,
    )
    extractor = SceneExtractor(config=config)
    book_path = extractor._resolve_book_path(args.book_path)
    chapters = extractor._load_chapters(book_path)
    selected_chapters = _filter_chapters(
        chapters,
        include_numbers=args.chapters,
        max_chapters=args.max_chapters,
    )

    if not selected_chapters:
        raise SystemExit("No chapters selected for inspection.")

    for chapter in selected_chapters:
        print("=" * 80)
        print(f"Chapter {chapter.number}: {chapter.title}")
        print(f"Source: {chapter.source_name}")
        print("-" * 80)
        chunk_displayed = 0

        for chunk in _iter_chunks(extractor, chapter):
            if args.chunk_limit is not None and chunk_displayed >= args.chunk_limit:
                break

            print(f"Chunk {chunk.index} | Paragraphs {chunk.start_paragraph}-{chunk.end_paragraph}")
            print(f"Paragraph count: {len(chunk.paragraphs)}")

            if args.show_prompts or not args.show_paragraphs:
                prompt = _format_prompt(extractor, chunk)
                print("\n--- Prompt Start ---")
                print(prompt)
                print("--- Prompt End ---\n")

            if args.show_paragraphs:
                print("--- Numbered Paragraphs ---")
                print(chunk.formatted_paragraphs())
                print("--- Paragraphs End ---\n")

            chunk_displayed += 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return inspect_book_chunks(args)


if __name__ == "__main__":
    raise SystemExit(main())
