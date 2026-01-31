"""Utilities for assembling scene context windows."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

from app.services.books import BookContentService, BookContentServiceError
from models.scene_extraction import SceneExtraction

from .models import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationServiceError,
)


@dataclass(slots=True)
class ChapterContext:
    number: int
    title: str
    paragraphs: list[str]
    source_name: str


class SceneContextBuilder:
    """Build context windows and excerpts for scenes."""

    def __init__(
        self,
        book_service: BookContentService | None = None,
        book_cache: MutableMapping[str, dict[int, ChapterContext]] | None = None,
    ) -> None:
        self._book_service = book_service or BookContentService()
        self._book_cache: MutableMapping[str, dict[int, ChapterContext]] = (
            book_cache if book_cache is not None else {}
        )

    def build_scene_context(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> tuple[dict[str, Any], str]:
        if scene.scene_paragraph_start is None or scene.scene_paragraph_end is None:
            base_start = max(scene.chunk_paragraph_start or 1, 1)
            base_end = max(scene.chunk_paragraph_end or base_start, base_start)
        else:
            base_start = max(int(scene.scene_paragraph_start), 1)
            base_end = max(int(scene.scene_paragraph_end), base_start)

        chapters = self._load_book_context(scene.source_book_path)
        chapter_context = chapters.get(int(scene.chapter_number))
        if chapter_context is None:
            raise ImagePromptGenerationServiceError(
                f"Chapter {scene.chapter_number} not found in {scene.source_book_path}"
            )

        before = max(config.context_before, 0)
        after = max(config.context_after, 0)
        total_paragraphs = len(chapter_context.paragraphs)
        start = max(1, base_start - before)
        end = min(total_paragraphs, base_end + after)

        formatted_lines: list[str] = []
        for index in range(start, end + 1):
            paragraph_text = chapter_context.paragraphs[index - 1]
            formatted_lines.append(f"[Paragraph {index}] {paragraph_text}")
        context_text = "\n".join(formatted_lines)
        context_window = {
            "chapter_number": scene.chapter_number,
            "chapter_title": chapter_context.title,
            "paragraph_span": [start, end],
            "paragraphs_before": before,
            "paragraphs_after": after,
        }
        return context_window, context_text

    def _load_book_context(
        self,
        source_book_path: str,
    ) -> dict[int, ChapterContext]:
        if source_book_path in self._book_cache:
            return self._book_cache[source_book_path]
        try:
            content = self._book_service.load_book(source_book_path)
        except BookContentServiceError as exc:
            raise ImagePromptGenerationServiceError(str(exc)) from exc

        chapters: dict[int, ChapterContext] = {}
        for chapter_number, chapter in content.chapters.items():
            chapters[chapter_number] = ChapterContext(
                number=chapter.number,
                title=chapter.title,
                paragraphs=list(chapter.paragraphs),
                source_name=chapter.source_name,
            )

        if not chapters:
            raise ImagePromptGenerationServiceError(
                f"No chapters extracted from book: {source_book_path}"
            )

        self._book_cache[source_book_path] = chapters
        return chapters


__all__ = [
    "ChapterContext",
    "SceneContextBuilder",
]
