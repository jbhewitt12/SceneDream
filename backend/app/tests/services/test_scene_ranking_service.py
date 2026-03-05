import asyncio

import pytest
from sqlmodel import Session

from app.repositories import SceneRankingRepository
from app.services.langchain import gemini_api, openai_api
from app.services.scene_ranking import SceneRankingPreview, SceneRankingService
from models.scene_ranking import SceneRanking


@pytest.fixture(autouse=True)
def _default_llm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "")


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


def test_rank_scene_falls_back_to_openai_when_gemini_key_missing(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory(book_slug="fallback-book")

    async def fail_gemini(**_: object) -> dict[str, object]:
        raise AssertionError("Gemini should not be called when key is missing")

    async def fake_openai_json_output(**_: object) -> dict[str, object]:
        return _mock_response(7.1)

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)
    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    service = SceneRankingService(db)
    preview = asyncio.run(service.rank_scene(scene, dry_run=True))

    assert isinstance(preview, SceneRankingPreview)
    assert preview.model_name == "gpt-5-mini"
