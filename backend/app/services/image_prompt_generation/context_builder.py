"""Utilities for assembling scene context windows."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

from app.services.books import BookContentService, BookContentServiceError
from models.scene_extraction import SceneExtraction

from .models import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationServiceError,
)

logger = logging.getLogger(__name__)


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
        effective_start = base_start
        effective_end = base_end

        if total_paragraphs > 0:
            effective_start = min(base_start, total_paragraphs)
            effective_end = min(base_end, total_paragraphs)
            if effective_end < effective_start:
                effective_end = effective_start

        if effective_start != base_start or effective_end != base_end:
            logger.warning(
                "Clamped scene paragraph span for scene %s in chapter %s from %s-%s to %s-%s because the parsed chapter has %s paragraphs",
                scene.id,
                scene.chapter_number,
                base_start,
                base_end,
                effective_start,
                effective_end,
                total_paragraphs,
            )

        # Only include paragraphs OUTSIDE the scene span as context.
        # The scene content is already provided verbatim in the "Scene Excerpt" section,
        # so we only need the surrounding context (before/after) here.
        before_start = max(1, effective_start - before)
        before_end = effective_start - 1  # Stop before the scene starts
        after_start = effective_end + 1  # Start after the scene ends
        after_end = min(total_paragraphs, effective_end + after)

        formatted_lines: list[str] = []
        # Add context paragraphs BEFORE the scene
        if before_end >= before_start:
            formatted_lines.append("### Context Before Scene")
            for index in range(before_start, before_end + 1):
                paragraph_text = chapter_context.paragraphs[index - 1]
                formatted_lines.append(f"[Paragraph {index}] {paragraph_text}")

        # Add context paragraphs AFTER the scene
        if after_end >= after_start:
            if formatted_lines:
                formatted_lines.append("")  # blank line separator
            formatted_lines.append("### Context After Scene")
            for index in range(after_start, after_end + 1):
                paragraph_text = chapter_context.paragraphs[index - 1]
                formatted_lines.append(f"[Paragraph {index}] {paragraph_text}")

        context_text = (
            "\n".join(formatted_lines)
            if formatted_lines
            else "(No surrounding context paragraphs available)"
        )
        context_window = {
            "chapter_number": scene.chapter_number,
            "chapter_title": chapter_context.title,
            "paragraph_span": [effective_start, effective_end],
            "context_before_span": [before_start, before_end]
            if before_end >= before_start
            else None,
            "context_after_span": [after_start, after_end]
            if after_end >= after_start
            else None,
            "paragraphs_before": before,
            "paragraphs_after": after,
        }
        if effective_start != base_start or effective_end != base_end:
            context_window["requested_paragraph_span"] = [base_start, base_end]
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
