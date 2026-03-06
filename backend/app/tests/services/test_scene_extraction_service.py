from __future__ import annotations

import pytest
from sqlmodel import Session

from app.services.langchain.model_routing import ResolvedLLMModel
from app.services.scene_extraction.scene_extraction import (
    Chapter,
    RawScene,
    SceneExtractionConfig,
    SceneExtractor,
)


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
