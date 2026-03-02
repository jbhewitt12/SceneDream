import asyncio

import pytest
from sqlmodel import Session

from app.repositories import SceneRankingRepository
from app.services.langchain import gemini_api
from app.services.scene_ranking import SceneRankingPreview, SceneRankingService
from models.scene_ranking import SceneRanking


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


def test_rank_scene_creates_ranking(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()

    async def fake_json_output(**_: object) -> dict[str, object]:
        return _mock_response(6.5)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = SceneRankingService(db)
    result = asyncio.run(service.rank_scene(scene))

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


def test_rank_scene_dry_run_returns_preview(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory(book_slug="dry-run-book")

    async def fake_json_output(**_: object) -> dict[str, object]:
        return _mock_response(7.2)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = SceneRankingService(db)
    preview = asyncio.run(service.rank_scene(scene, dry_run=True))

    assert isinstance(preview, SceneRankingPreview)
    assert preview.overall_priority == 7.2

    repository = SceneRankingRepository(db)
    assert repository.list_for_scene(scene.id) == []
