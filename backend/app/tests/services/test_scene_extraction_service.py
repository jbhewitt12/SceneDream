from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session

from app.services.langchain.model_routing import ResolvedLLMModel
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    RawScene,
    SceneExtractionConfig,
    SceneExtractor,
)
from app.services.scene_extraction.scene_refinement import RefinedScene


def test_existing_processed_chunks_uses_repository(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=False),
    )
    chapter = Chapter(
        number=7,
        title="Chapter Seven",
        paragraphs=["Paragraph"],
        source_name="chapter7.xhtml",
    )

    captured: dict[str, object] = {}

    def fake_chunk_indexes_for_chapter(
        *, book_slug: str, chapter_number: int
    ) -> set[int]:
        captured["book_slug"] = book_slug
        captured["chapter_number"] = chapter_number
        return {0, 2}

    monkeypatch.setattr(
        extractor._scene_repo,
        "chunk_indexes_for_chapter",
        fake_chunk_indexes_for_chapter,
    )

    result = extractor._existing_processed_chunks("test-book", chapter)

    assert result == {0, 2}
    assert captured == {"book_slug": "test-book", "chapter_number": 7}


def test_persist_chapter_scenes_uses_upsert_repository(
    db: Session,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = scene_factory(
        book_slug="test-book-persist",
        chapter_number=2,
        scene_number=1,
        chapter_title="Original Chapter",
        chapter_source_name="old-source.xhtml",
        props={
            "keep_key": "keep-value",
            "provisional_id": 999,
            "chunk_paragraph_span": "1-2",
            "location_marker_normalized": "legacy",
            "refinement_summary": "legacy",
        },
    )

    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=False),
    )

    def fake_resolve_extraction_model() -> ResolvedLLMModel:
        return ResolvedLLMModel(
            vendor="google",
            model="gemini-test-model",
            used_backup=False,
        )

    upsert_calls: list[dict[str, object]] = []

    def fake_upsert_by_identity(**kwargs: object) -> object:
        upsert_calls.append(kwargs)
        return existing

    monkeypatch.setattr(
        extractor,
        "_resolve_extraction_model",
        fake_resolve_extraction_model,
    )
    monkeypatch.setattr(
        extractor._scene_repo,
        "upsert_by_identity",
        fake_upsert_by_identity,
    )

    chapter = Chapter(
        number=2,
        title="Refactored Chapter",
        paragraphs=["A", "B", "C"],
        source_name="chapter2.xhtml",
    )
    raw_scenes = [
        RawScene(
            chapter_number=2,
            chapter_title="Refactored Chapter",
            provisional_id=10,
            location_marker="3-4",
            raw_excerpt="A bright city glows at dusk.",
            chunk_index=0,
            chunk_span=(3, 4),
            scene_id=1,
        ),
        RawScene(
            chapter_number=2,
            chapter_title="Refactored Chapter",
            provisional_id=11,
            location_marker="5",
            raw_excerpt="A shuttle descends through storm clouds.",
            chunk_index=1,
            chunk_span=(5, 5),
            scene_id=2,
        ),
        RawScene(
            chapter_number=2,
            chapter_title="Refactored Chapter",
            provisional_id=12,
            location_marker="6",
            raw_excerpt="Missing identity should be skipped.",
            chunk_index=2,
            chunk_span=(6, 6),
            scene_id=None,
        ),
    ]

    extractor._persist_chapter_scenes(
        book_slug="test-book-persist",
        book_path="documents/test.epub",
        chapter=chapter,
        raw_scenes=raw_scenes,
        refinements={},
    )

    assert len(upsert_calls) == 2

    first_call = upsert_calls[0]
    assert first_call["book_slug"] == "test-book-persist"
    assert first_call["chapter_number"] == 2
    assert first_call["scene_number"] == 1
    assert first_call["commit"] is False
    assert first_call["refresh"] is False

    first_values = first_call["values"]
    assert isinstance(first_values, dict)
    assert first_values["chapter_source_name"] == "chapter2.xhtml"
    assert first_values["location_marker_normalized"] == "3-4"
    assert first_values["extraction_model"] == "gemini-test-model"
    assert "refinement_decision" not in first_values
    assert first_values["props"] == {
        "keep_key": "keep-value",
        "extraction_model_vendor": "google",
        "extraction_used_backup_model": False,
    }

    second_call = upsert_calls[1]
    assert second_call["scene_number"] == 2
    assert second_call["commit"] is False
    assert second_call["refresh"] is False

    second_values = second_call["values"]
    assert isinstance(second_values, dict)
    assert second_values["book_slug"] == "test-book-persist"
    assert second_values["chapter_number"] == 2
    assert second_values["scene_number"] == 2
    assert second_values["refinement_decision"] is None
    assert second_values["props"] == {
        "extraction_model_vendor": "google",
        "extraction_used_backup_model": False,
    }


def test_extract_book_processes_chapters_and_persists_results(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=True),
    )
    chapters = [
        Chapter(
            number=1,
            title="Opening",
            paragraphs=["p1", "p2"],
            source_name="chapter1.xhtml",
        ),
        Chapter(
            number=2,
            title="Finale",
            paragraphs=["p3"],
            source_name="chapter2.xhtml",
        ),
    ]

    monkeypatch.setattr(
        extractor,
        "_resolve_book_path",
        lambda _book_path: Path("documents/test.epub"),
    )
    monkeypatch.setattr(
        extractor,
        "_resolve_book_slug",
        lambda _book_path: "test-book-service",
    )
    monkeypatch.setattr(extractor, "_load_chapters", lambda _book_path: chapters)

    extract_calls: list[dict[str, object]] = []
    refine_calls: list[int] = []
    persist_calls: list[dict[str, object]] = []

    def fake_extract_chapter_scenes(
        chapter: Chapter,
        *,
        chunk_limit: int | None = None,
        book_slug: str | None = None,
        chunk_start_index: int | None = None,
    ) -> list[RawScene]:
        extract_calls.append(
            {
                "chapter_number": chapter.number,
                "chunk_limit": chunk_limit,
                "book_slug": book_slug,
                "chunk_start_index": chunk_start_index,
            }
        )
        if chapter.number == 1:
            return [
                RawScene(
                    chapter_number=1,
                    chapter_title=chapter.title,
                    provisional_id=1,
                    location_marker="1-2",
                    raw_excerpt="Opening scene one.",
                    chunk_index=0,
                    chunk_span=(1, 2),
                    scene_id=1,
                ),
                RawScene(
                    chapter_number=1,
                    chapter_title=chapter.title,
                    provisional_id=2,
                    location_marker="3",
                    raw_excerpt="Opening scene two.",
                    chunk_index=1,
                    chunk_span=(3, 3),
                    scene_id=2,
                ),
            ]
        return [
            RawScene(
                chapter_number=2,
                chapter_title=chapter.title,
                provisional_id=1,
                location_marker="1",
                raw_excerpt="Finale scene.",
                chunk_index=0,
                chunk_span=(1, 1),
                scene_id=1,
            )
        ]

    def fake_refine_chapter_scenes(
        chapter: Chapter,
        scenes: list[RawScene],
    ) -> dict[int, RefinedScene]:
        refine_calls.append(chapter.number)
        return {
            scene.scene_id: RefinedScene(
                scene_id=scene.scene_id or 0,
                decision="keep",
                rationale="Looks cinematic.",
            )
            for scene in scenes
            if scene.scene_id is not None
        }

    def fake_persist_chapter_scenes(
        *,
        book_slug: str,
        book_path: str | Path,
        chapter: Chapter,
        raw_scenes: list[RawScene],
        refinements: dict[int, RefinedScene],
    ) -> None:
        persist_calls.append(
            {
                "book_slug": book_slug,
                "book_path": str(book_path),
                "chapter_number": chapter.number,
                "raw_count": len(raw_scenes),
                "refinement_count": len(refinements),
            }
        )

    monkeypatch.setattr(
        extractor, "_extract_chapter_scenes", fake_extract_chapter_scenes
    )
    monkeypatch.setattr(extractor, "_refine_chapter_scenes", fake_refine_chapter_scenes)
    monkeypatch.setattr(
        extractor, "_persist_chapter_scenes", fake_persist_chapter_scenes
    )

    stats = extractor.extract_book("ignored.epub")

    assert stats == {"book_slug": "test-book-service", "chapters": 2, "scenes": 3}
    assert extract_calls == [
        {
            "chapter_number": 1,
            "chunk_limit": None,
            "book_slug": "test-book-service",
            "chunk_start_index": None,
        },
        {
            "chapter_number": 2,
            "chunk_limit": None,
            "book_slug": "test-book-service",
            "chunk_start_index": None,
        },
    ]
    assert refine_calls == [1, 2]
    assert persist_calls == [
        {
            "book_slug": "test-book-service",
            "book_path": "documents/test.epub",
            "chapter_number": 1,
            "raw_count": 2,
            "refinement_count": 2,
        },
        {
            "book_slug": "test-book-service",
            "book_path": "documents/test.epub",
            "chapter_number": 2,
            "raw_count": 1,
            "refinement_count": 1,
        },
    ]


def test_extract_preview_limits_chapters_and_chunks(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=False),
    )
    chapters = [
        Chapter(
            number=1,
            title="Preview One",
            paragraphs=["p1", "p2", "p3"],
            source_name="chapter1.xhtml",
        ),
        Chapter(
            number=2,
            title="Preview Two",
            paragraphs=["p4", "p5"],
            source_name="chapter2.xhtml",
        ),
        Chapter(
            number=3,
            title="Preview Three",
            paragraphs=["p6"],
            source_name="chapter3.xhtml",
        ),
    ]

    monkeypatch.setattr(
        extractor,
        "_resolve_book_path",
        lambda _book_path: Path("documents/preview.epub"),
    )
    monkeypatch.setattr(
        extractor,
        "_resolve_book_slug",
        lambda _book_path: "test-book-preview",
    )
    monkeypatch.setattr(extractor, "_load_chapters", lambda _book_path: chapters)
    monkeypatch.setattr(extractor, "_chunk_chapter", lambda _chapter: [object()] * 4)

    extract_calls: list[dict[str, object]] = []
    persist_calls: list[dict[str, object]] = []

    def fake_extract_chapter_scenes(
        chapter: Chapter,
        *,
        chunk_limit: int | None = None,
        book_slug: str | None = None,
        chunk_start_index: int | None = None,
    ) -> list[RawScene]:
        extract_calls.append(
            {
                "chapter_number": chapter.number,
                "chunk_limit": chunk_limit,
                "book_slug": book_slug,
                "chunk_start_index": chunk_start_index,
            }
        )
        return [
            RawScene(
                chapter_number=chapter.number,
                chapter_title=chapter.title,
                provisional_id=1,
                location_marker="1",
                raw_excerpt=f"Preview scene {chapter.number}.",
                chunk_index=0,
                chunk_span=(1, 1),
                scene_id=1,
            )
        ]

    def fake_persist_chapter_scenes(
        *,
        book_slug: str,
        book_path: str | Path,
        chapter: Chapter,
        raw_scenes: list[RawScene],
        refinements: dict[int, RefinedScene],
    ) -> None:
        persist_calls.append(
            {
                "book_slug": book_slug,
                "book_path": str(book_path),
                "chapter_number": chapter.number,
                "raw_count": len(raw_scenes),
                "refinement_count": len(refinements),
            }
        )

    monkeypatch.setattr(
        extractor, "_extract_chapter_scenes", fake_extract_chapter_scenes
    )
    monkeypatch.setattr(
        extractor, "_persist_chapter_scenes", fake_persist_chapter_scenes
    )

    stats = extractor.extract_preview(
        "ignored.epub",
        max_chapters=2,
        max_chunks_per_chapter=1,
    )

    assert stats["book_slug"] == "test-book-preview"
    assert stats["chapters"] == 2
    assert stats["scenes"] == 2
    assert stats["chapters_processed"] == [
        {
            "chapter_number": 1,
            "chapter_title": "Preview One",
            "chunks_considered": 1,
            "raw_scenes": 1,
        },
        {
            "chapter_number": 2,
            "chapter_title": "Preview Two",
            "chunks_considered": 1,
            "raw_scenes": 1,
        },
    ]
    assert extract_calls == [
        {
            "chapter_number": 1,
            "chunk_limit": 1,
            "book_slug": "test-book-preview",
            "chunk_start_index": None,
        },
        {
            "chapter_number": 2,
            "chunk_limit": 1,
            "book_slug": "test-book-preview",
            "chunk_start_index": None,
        },
    ]
    assert persist_calls == [
        {
            "book_slug": "test-book-preview",
            "book_path": "ignored.epub",
            "chapter_number": 1,
            "raw_count": 1,
            "refinement_count": 0,
        },
        {
            "book_slug": "test-book-preview",
            "book_path": "ignored.epub",
            "chapter_number": 2,
            "raw_count": 1,
            "refinement_count": 0,
        },
    ]


def test_chunk_chapter_uses_reduced_default_chunk_size_and_overlap(db: Session) -> None:
    extractor = SceneExtractor(
        session=db,
        config=SceneExtractionConfig(enable_refinement=False),
    )
    chapter = Chapter(
        number=1,
        title="Dense Chapter",
        paragraphs=["a" * 1500, "b" * 1500, "c" * 1500, "d" * 1500, "e" * 1500],
        source_name="chapter1.xhtml",
    )

    chunks = extractor._chunk_chapter(chapter)

    assert [(chunk.start_paragraph, chunk.end_paragraph) for chunk in chunks] == [
        (1, 4),
        (4, 5),
    ]
