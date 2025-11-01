#!/usr/bin/env python3
"""
Preview MOBI chapter extraction for manual inspection.

This script loads a MOBI (or EPUB) file using the SceneExtractor and prints
the first few chapter chunks so you can verify that parsing works as expected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scene_extraction.scene_extraction import (  # noqa: E402
    Chapter,
    ChapterChunk,
    SceneExtractionConfig,
    SceneExtractor,
)


DEFAULT_BOOK = (
    PROJECT_ROOT
    / "books"
    / "James Clavell"
    / "Shogun"
    / "Shogun - James Clavell.mobi"
)


def clamp_positive(value: int, *, minimum: int, fallback: int) -> int:
    if value < minimum:
        return fallback
    return value


def abbreviate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def describe_chapter(chapter: Chapter) -> str:
    paragraph_count = len(chapter.paragraphs)
    return (
        f"Chapter {chapter.number}: {chapter.title} "
        f"(source='{chapter.source_name}', paragraphs={paragraph_count})"
    )


def describe_chunk(chunk: ChapterChunk) -> str:
    paragraph_count = len(chunk.paragraphs)
    chars = sum(len(p) for p in chunk.paragraphs)
    return (
        f"Chunk {chunk.index}: paragraphs {chunk.start_paragraph}-{chunk.end_paragraph} "
        f"(paragraphs={paragraph_count}, characters={chars})"
    )


def print_chunk_preview(
    chunk: ChapterChunk,
    *,
    max_paragraphs: int,
    paragraph_char_limit: int,
) -> None:
    print(f"  {describe_chunk(chunk)}")
    limit = clamp_positive(max_paragraphs, minimum=1, fallback=3)
    for offset, paragraph in enumerate(chunk.paragraphs[:limit]):
        paragraph_number = chunk.start_paragraph + offset
        snippet = abbreviate(paragraph, paragraph_char_limit)
        print(f"    [{paragraph_number}] {snippet}")
    remaining = len(chunk.paragraphs) - limit
    if remaining > 0:
        print(f"    ... ({remaining} more paragraph(s) in this chunk)")


def preview_book(
    book_path: Path,
    *,
    max_chapters: int,
    max_chunks: int,
    max_paragraphs: int,
    paragraph_char_limit: int,
) -> None:
    extractor = SceneExtractor(
        config=SceneExtractionConfig(enable_refinement=False)
    )
    chapters = extractor._load_chapters(book_path)  # pylint: disable=protected-access
    if not chapters:
        print("No chapters were parsed from the supplied book.")
        return

    limited_chapters = chapters[: clamp_positive(max_chapters, minimum=1, fallback=1)]
    print(f"Loaded {len(chapters)} chapter(s); showing the first {len(limited_chapters)}.")

    for chapter in limited_chapters:
        print(describe_chapter(chapter))
        chunks = extractor._chunk_chapter(  # pylint: disable=protected-access
            chapter
        )
        if not chunks:
            print("  No chunks produced for this chapter.")
            continue
        limited_chunks = chunks[: clamp_positive(max_chunks, minimum=1, fallback=1)]
        for chunk in limited_chunks:
            print_chunk_preview(
                chunk,
                max_paragraphs=max_paragraphs,
                paragraph_char_limit=paragraph_char_limit,
            )
        if len(chunks) > len(limited_chunks):
            print(
                f"  ... skipped {len(chunks) - len(limited_chunks)} additional chunk(s) "
                "for brevity"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview parsed chapter chunks for a MOBI or EPUB book."
    )
    parser.add_argument(
        "book",
        nargs="?",
        default=str(DEFAULT_BOOK),
        help=(
            "Path to the book file to preview. Defaults to the Shogun MOBI if not supplied."
        ),
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=1,
        help="Number of chapters to display.",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=2,
        help="Number of chunks to show per chapter.",
    )
    parser.add_argument(
        "--paragraphs",
        type=int,
        default=5,
        help="Number of paragraphs to print per chunk.",
    )
    parser.add_argument(
        "--paragraph-char-limit",
        type=int,
        default=320,
        help="Maximum number of characters to display per paragraph.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    book_path = Path(args.book).expanduser().resolve()
    if not book_path.exists():
        print(f"Book not found: {book_path}")
        return 1
    preview_book(
        book_path,
        max_chapters=args.chapters,
        max_chunks=args.chunks,
        max_paragraphs=args.paragraphs,
        paragraph_char_limit=args.paragraph_char_limit,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
