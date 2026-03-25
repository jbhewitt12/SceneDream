from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session

from app.services.books import BookContentServiceError
from app.services.books.base import BookChapter, BookContent, BookMetadata
from app.services.langchain import gemini_api, openai_api
from app.services.scene_extraction.provider_errors import (
    ExtractionProviderAccessError,
    ExtractionQuotaError,
    ExtractionSetupError,
    classify_extraction_provider_error,
)
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    RawScene,
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_extraction.scene_refinement import SceneRefiner


@pytest.fixture
def extractor(db: Session) -> SceneExtractor:
    return SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=False),
    )


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
    db: Session,
) -> None:
    config = SceneExtractionConfig(enable_refinement=False)
    extractor = SceneExtractor(session=db, config=config)
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
    )
    refinements = refiner.refine(chapter, [scene], fail_on_error=True)

    assert refinements[1].decision == "keep"
    assert refiner.last_model_vendor == "openai"
    assert refiner.last_model_name == "gpt-5-mini"


@pytest.mark.parametrize(
    ("error", "provider", "model", "expected_type", "expected_code"),
    [
        (
            ValueError("OPENAI_API_KEY not found in .env file."),
            "openai",
            "gpt-5-mini",
            ExtractionSetupError,
            "extraction_setup_error",
        ),
        (
            RuntimeError("Incorrect API key provided: invalid key"),
            "openai",
            "gpt-5-mini",
            ExtractionProviderAccessError,
            "extraction_auth_error",
        ),
        (
            RuntimeError(
                "You exceeded your current quota, please check your plan and billing details."
            ),
            "openai",
            "gpt-5-mini",
            ExtractionQuotaError,
            "extraction_quota_error",
        ),
        (
            RuntimeError(
                "The model `gpt-5` does not exist or you do not have access to it."
            ),
            "openai",
            "gpt-5",
            ExtractionProviderAccessError,
            "extraction_model_access_error",
        ),
    ],
)
def test_classify_extraction_provider_error_identifies_fatal_cases(
    error: Exception,
    provider: str,
    model: str,
    expected_type: type[BaseException],
    expected_code: str,
) -> None:
    classified = classify_extraction_provider_error(
        error,
        provider=provider,
        model=model,
    )

    assert isinstance(classified, expected_type)
    assert classified is not None
    assert classified.error_code == expected_code
    assert "hint" in classified.error_metadata
    assert isinstance(classified.error_metadata.get("action_items"), list)


def test_classify_extraction_provider_error_keeps_parse_failures_recoverable() -> None:
    classified = classify_extraction_provider_error(
        ValueError("Failed to parse JSON from response: {"),
        provider="openai",
        model="gpt-5-mini",
    )

    assert classified is None


def test_extract_chapter_scenes_fails_fast_for_fatal_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    chapter = Chapter(
        number=1,
        title="Fatal Test",
        paragraphs=["A" * 800, "B" * 800],
        source_name="chapter1.xhtml",
    )
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(
            extraction_model_vendor="openai",
            gemini_model="gpt-5-mini",
            extraction_backup_model_vendor="google",
            extraction_backup_model="gemini-2.5-flash-lite",
            enable_refinement=False,
            max_chunk_chars=1000,
        ),
    )

    call_count = 0

    async def fake_openai_json_output(**_: object) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Incorrect API key provided: invalid key")

    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(
        ExtractionProviderAccessError,
        match="rejected the configured API key",
    ):
        extractor._extract_chapter_scenes(chapter)

    assert call_count == 1


def test_extract_chapter_scenes_continues_after_recoverable_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    chapter = Chapter(
        number=1,
        title="Recoverable Test",
        paragraphs=["A" * 800, "B" * 800],
        source_name="chapter1.xhtml",
    )
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(
            extraction_model_vendor="openai",
            gemini_model="gpt-5-mini",
            extraction_backup_model_vendor="google",
            extraction_backup_model="gemini-2.5-flash-lite",
            enable_refinement=False,
            max_chunk_chars=1000,
        ),
    )

    call_count = 0

    async def fake_openai_json_output(**_: object) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Failed to parse JSON from response: {")
        return {
            "chapter_title": "Recoverable Test",
            "chapter_number": 1,
            "scenes": [
                {
                    "scene_id": 1,
                    "location_marker": "1",
                    "raw_excerpt": "B" * 50,
                }
            ],
        }

    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    scenes = extractor._extract_chapter_scenes(chapter)

    assert call_count == 2
    assert len(scenes) == 1
    assert scenes[0].raw_excerpt == "B" * 50


def test_scene_refiner_raises_fatal_provider_errors_even_in_best_effort_mode(
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

    async def fake_openai_structured_output(**_: object) -> object:
        raise RuntimeError(
            "You exceeded your current quota, please check your plan and billing details."
        )

    monkeypatch.setattr(openai_api, "structured_output", fake_openai_structured_output)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    refiner = SceneRefiner(
        default_vendor="openai",
        model="gpt-5-mini",
        backup_vendor="google",
        backup_model="gemini-2.5-flash-lite",
        temperature=0.1,
    )

    with pytest.raises(ExtractionQuotaError, match="available credits"):
        refiner.refine(chapter, [scene])
