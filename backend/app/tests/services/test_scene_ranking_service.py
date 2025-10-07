from collections.abc import Callable

import pytest
from sqlmodel import Session

from app.repositories import SceneExtractionRepository, SceneRankingRepository
from app.services.langchain import gemini_api
from app.services.scene_ranking import SceneRankingPreview, SceneRankingService
from models.scene_ranking import SceneRanking


@pytest.fixture()
def scene_factory(db: Session) -> Callable[..., object]:
    created: list[object] = []

    def _create(**overrides: object) -> object:
        repository = SceneExtractionRepository(db)
        counter = len(created) + 1
        data: dict[str, object] = {
            "book_slug": "test-book",
            "source_book_path": "books/test.epub",
            "chapter_number": counter,
            "chapter_title": f"Chapter {counter}",
            "chapter_source_name": "Test",
            "scene_number": 1,
            "location_marker": f"chapter-{counter}-scene-1",
            "raw": "A hero walks into a mysterious forest.",
            "refined": "The hero enters a luminous forest filled with whispers.",
            "chunk_index": 0,
            "chunk_paragraph_start": 0,
            "chunk_paragraph_end": 0,
            "raw_word_count": 9,
            "raw_char_count": 52,
            "refined_word_count": 11,
            "refined_char_count": 68,
            "scene_paragraph_start": 1,
            "scene_paragraph_end": 2,
            "scene_word_start": 0,
            "scene_word_end": 25,
            "extraction_model": "unit-test",
            "refinement_model": "unit-test",
        }
        data.update(overrides)
        scene = repository.create(data=data, commit=True)
        created.append(scene)
        return scene

    yield _create

    for scene in created:
        db.delete(scene)
    db.commit()


def _mock_response(score: float = 6.0) -> dict[str, object]:
    scores = {
        "originality": score,
        "visual_style_potential": score,
        "image_prompt_fit": score,
        "video_prompt_fit": score,
        "emotional_intensity": score,
        "worldbuilding_depth": score,
        "character_focus": score,
        "action_dynamism": score,
        "clarity_for_prompting": score,
    }
    return {
        "scores": scores,
        "overall_priority": score,
        "justification": "Balanced test scores across all criteria.",
        "warnings": ["mild peril"],
        "character_tags": ["Hero"],
        "diagnostics": {"request_id": "test-request"},
    }


def test_rank_scene_creates_ranking(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory()

    monkeypatch.setattr(gemini_api, "json_output", lambda **_: _mock_response(6.5))

    service = SceneRankingService(db)
    result = service.rank_scene(scene)

    assert isinstance(result, SceneRanking)
    assert pytest.approx(result.overall_priority, 0.001) == 6.5
    assert result.warnings == ["mild peril"]
    assert result.character_tags == ["Hero"]
    assert result.llm_request_id == "test-request"

    repository = SceneRankingRepository(db)
    stored = repository.get(result.id)
    assert stored is not None

    db.delete(result)
    db.commit()


def test_rank_scene_dry_run_returns_preview(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory(book_slug="dry-run-book")

    monkeypatch.setattr(gemini_api, "json_output", lambda **_: _mock_response(7.2))

    service = SceneRankingService(db)
    preview = service.rank_scene(scene, dry_run=True)

    assert isinstance(preview, SceneRankingPreview)
    assert preview.overall_priority == 7.2

    repository = SceneRankingRepository(db)
    assert repository.list_for_scene(scene.id) == []
