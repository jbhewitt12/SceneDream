from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.books import BookContentServiceError
from app.services.books.base import BookChapter, BookContent, BookMetadata
from app.services.langchain import gemini_api, openai_api
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    RawScene,
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_extraction.scene_refinement import SceneRefiner


@pytest.fixture
def extractor() -> SceneExtractor:
    return SceneExtractor(SceneExtractionConfig(enable_refinement=False))


def _make_book_content(book_path: Path) -> BookContent:
    metadata = BookMetadata(
        file_path=book_path,
        file_checksum="checksum",
        parser_version="1.0",
        format=book_path.suffix.lstrip(".") or "epub",
    )
    chapters = {
        1: BookChapter(
            number=1,
            title="Chapter 1",
            paragraphs=["Paragraph 1", "Paragraph 2"],
            source_name="chapter1.xhtml",
        ),
        2: BookChapter(
            number=2,
            title="Chapter 2",
            paragraphs=["Paragraph 3"],
            source_name="chapter2.xhtml",
        ),
    }
    return BookContent(
        slug="book",
        title="Book Title",
        chapters=chapters,
        metadata=metadata,
        author="Author",
    )


def test_load_chapters_uses_book_content_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extractor: SceneExtractor,
) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_text("dummy", encoding="utf-8")
    content = _make_book_content(book_path)

    def fake_load_book(path: Path, *, cache: bool = True) -> BookContent:  # noqa: ARG001
        assert path == book_path
        return content

    monkeypatch.setattr(extractor._book_service, "load_book", fake_load_book)

    chapters = extractor._load_chapters(book_path)
    assert isinstance(chapters, list)
    assert [chapter.number for chapter in chapters] == [1, 2]

    first = chapters[0]
    assert isinstance(first, Chapter)
    assert first.title == "Chapter 1"
    assert first.source_name == "chapter1.xhtml"
    assert first.paragraphs == ["Paragraph 1", "Paragraph 2"]

    # Ensure paragraph lists are copied and do not mutate cached content.
    first.paragraphs.append("New paragraph")
    assert content.chapters[1].paragraphs == ["Paragraph 1", "Paragraph 2"]


def test_load_chapters_propagates_service_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extractor: SceneExtractor,
) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_text("dummy", encoding="utf-8")

    def fake_load_book(path: Path, *, cache: bool = True) -> BookContent:  # noqa: ARG001
        raise BookContentServiceError("boom")

    monkeypatch.setattr(extractor._book_service, "load_book", fake_load_book)

    with pytest.raises(RuntimeError, match="Failed to load chapters"):
        extractor._load_chapters(book_path)


def test_extract_chapter_scenes_falls_back_to_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SceneExtractionConfig(enable_refinement=False)
    extractor = SceneExtractor(config)
    chapter = Chapter(
        number=1,
        title="Test Chapter",
        paragraphs=["The sky burned neon over the city."],
        source_name="chapter1.xhtml",
    )

    async def fail_gemini(**_: object) -> dict[str, object]:
        raise AssertionError("Gemini should not be called when key is missing")

    async def fake_openai_json_output(**_: object) -> dict[str, object]:
        return {
            "chapter_title": "Test Chapter",
            "chapter_number": 1,
            "scenes": [
                {
                    "scene_id": 1,
                    "location_marker": "Paragraph 1",
                    "raw_excerpt": "The sky burned neon over the city.",
                }
            ],
        }

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)
    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    scenes = extractor._extract_chapter_scenes(chapter, chunk_limit=1)

    assert len(scenes) == 1
    assert scenes[0].raw_excerpt == "The sky burned neon over the city."


def test_scene_refiner_falls_back_to_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chapter = Chapter(
        number=1,
        title="Test Chapter",
        paragraphs=[],
        source_name="chapter1.xhtml",
    )
    scene = RawScene(
        chapter_number=1,
        chapter_title="Test Chapter",
        provisional_id=1,
        location_marker="Paragraph 1",
        raw_excerpt="A lone pilot watches lightning roll over a fractured moon.",
        chunk_index=0,
        chunk_span=(1, 1),
        scene_id=1,
    )

    async def fail_gemini(**_: object) -> object:
        raise AssertionError("Gemini should not be called when key is missing")

    async def fake_openai_structured_output(**_: object) -> object:
        return SimpleNamespace(
            scenes=[
                {
                    "scene_id": 1,
                    "decision": "keep",
                    "rationale": "Rich visual details are present.",
                }
            ]
        )

    monkeypatch.setattr(gemini_api, "structured_output", fail_gemini)
    monkeypatch.setattr(openai_api, "structured_output", fake_openai_structured_output)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    refiner = SceneRefiner(
        default_vendor="google",
        model="gemini-2.5-flash-lite",
        backup_vendor="openai",
        backup_model="gpt-5-mini",
        temperature=0.1,
        max_tokens=None,
    )
    refinements = refiner.refine(chapter, [scene], fail_on_error=True)

    assert refinements[1].decision == "keep"
    assert refiner.last_model_vendor == "openai"
    assert refiner.last_model_name == "gpt-5-mini"
