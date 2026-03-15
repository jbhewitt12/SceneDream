from __future__ import annotations

import argparse
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories import ImagePromptRepository, SceneRankingRepository
from app.services.image_gen_cli import (
    _collect_matching_prompt_ids_for_image_generation,
    _count_prompt_ready_scenes_without_images,
    _run_prompts,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationService,
)
from app.services.image_prompt_generation.models import ImagePromptGenerationConfig


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def test_count_prompt_ready_scenes_without_images_uses_unique_ranked_scenes() -> None:
    scene_with_image = uuid4()
    scene_missing_prompts = uuid4()
    scene_prompt_ready = uuid4()

    rankings = [
        SimpleNamespace(scene_extraction_id=scene_with_image),
        SimpleNamespace(scene_extraction_id=scene_with_image),
        SimpleNamespace(scene_extraction_id=scene_missing_prompts),
        SimpleNamespace(scene_extraction_id=scene_prompt_ready),
    ]

    ranking_repo = SimpleNamespace(
        list_top_rankings_for_book=lambda **_kwargs: rankings,
    )
    prompt_repo = SimpleNamespace(
        has_any_for_scene=lambda scene_id: scene_id == scene_prompt_ready,
    )
    image_repo = SimpleNamespace(
        list_for_scene=lambda scene_id, limit=1: [object()]
        if scene_id == scene_with_image
        else [],
    )

    ready_scenes, scenes_missing_prompts = _count_prompt_ready_scenes_without_images(
        ranking_repo=ranking_repo,
        prompt_repo=prompt_repo,
        image_repo=image_repo,
        book_slug="test-book",
        target_scenes=1,
    )

    assert ready_scenes == 1
    assert scenes_missing_prompts == 1


def test_count_prompt_ready_scenes_without_images_uses_prompt_matcher_when_provided() -> None:
    scene_with_mismatched_prompts = uuid4()
    scene_with_matching_prompts = uuid4()

    rankings = [
        SimpleNamespace(scene_extraction_id=scene_with_mismatched_prompts),
        SimpleNamespace(scene_extraction_id=scene_with_matching_prompts),
    ]

    ranking_repo = SimpleNamespace(
        list_top_rankings_for_book=lambda **_kwargs: rankings,
    )
    prompt_repo = SimpleNamespace(
        has_any_for_scene=lambda _scene_id: True,
    )
    image_repo = SimpleNamespace(
        list_for_scene=lambda _scene_id, limit=1: [],
    )

    ready_scenes, scenes_missing_prompts = _count_prompt_ready_scenes_without_images(
        ranking_repo=ranking_repo,
        prompt_repo=prompt_repo,
        image_repo=image_repo,
        book_slug="test-book",
        target_scenes=2,
        scene_has_ready_prompts=lambda scene_id: scene_id
        == scene_with_matching_prompts,
    )

    assert ready_scenes == 1
    assert scenes_missing_prompts == 1


def test_collect_matching_prompt_ids_for_image_generation_skips_higher_ranked_stale_prompt_sets() -> None:
    stale_scene = uuid4()
    matching_scene = uuid4()
    stale_prompt = SimpleNamespace(
        id=uuid4(),
        raw_response={
            "service": {
                "prompt_art_style_mode": "random_mix",
                "prompt_art_style_text": None,
                "target_provider": "gpt-image",
            }
        },
        target_provider="gpt-image",
    )
    matching_prompts = [
        SimpleNamespace(
            id=uuid4(),
            raw_response={
                "service": {
                    "prompt_art_style_mode": "single_style",
                    "prompt_art_style_text": "neon noir",
                    "target_provider": "gpt-image",
                }
            },
            target_provider="gpt-image",
        ),
        SimpleNamespace(
            id=uuid4(),
            raw_response={
                "service": {
                    "prompt_art_style_mode": "single_style",
                    "prompt_art_style_text": "neon noir",
                    "target_provider": "gpt-image",
                }
            },
            target_provider="gpt-image",
        ),
    ]

    rankings = [
        SimpleNamespace(scene_extraction_id=stale_scene),
        SimpleNamespace(scene_extraction_id=matching_scene),
    ]

    ranking_repo = SimpleNamespace(
        list_top_rankings_for_book=lambda **_kwargs: rankings,
    )
    prompt_repo = SimpleNamespace(
        get_latest_generated_set_for_scene=lambda scene_id: (
            [stale_prompt] if scene_id == stale_scene else matching_prompts
        ),
    )
    image_repo = SimpleNamespace(
        list_for_scene=lambda _scene_id, limit=1: [],
    )
    prompt_service = SimpleNamespace(
        _config=ImagePromptGenerationConfig(
            variants_count=2,
            use_ranking_recommendation=False,
            prompt_art_style_mode="single_style",
            prompt_art_style_text="neon noir",
        ),
        _ranking_repo=SimpleNamespace(get_latest_for_scene=lambda _scene_id: None),
        _existing_prompt_set_matches_config=lambda prompts, config: all(
            prompt.raw_response["service"].get("prompt_art_style_mode")
            == config.prompt_art_style_mode
            and prompt.raw_response["service"].get("prompt_art_style_text")
            == config.prompt_art_style_text
            for prompt in prompts
        ),
    )

    prompt_ids = _collect_matching_prompt_ids_for_image_generation(
        ranking_repo=ranking_repo,
        prompt_repo=prompt_repo,
        image_repo=image_repo,
        prompt_service=prompt_service,
        book_slug="test-book",
        target_scenes=1,
    )

    assert prompt_ids == [prompt.id for prompt in matching_prompts]


@pytest.mark.anyio
async def test_run_prompts_rolls_back_after_scene_generation_error(
    db: Session,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed scene should not poison later prompt-selection queries."""

    book_slug = f"test-book-{uuid4()}"
    failing_scene = scene_factory(book_slug=book_slug, chapter_number=1, scene_number=1)
    succeeding_scene = scene_factory(
        book_slug=book_slug,
        chapter_number=1,
        scene_number=2,
    )

    ranking_repo = SceneRankingRepository(db)
    ranking_repo.create(
        data={
            "scene_extraction_id": failing_scene.id,
            "model_vendor": "openai",
            "model_name": "test-ranking-model",
            "prompt_version": "test-ranking-v1",
            "scores": {"cinematic": 0.9},
            "overall_priority": 9.9,
            "weight_config": {"cinematic": 1.0},
            "weight_config_hash": "test-weight-hash-1",
            "raw_response": {},
        },
        commit=True,
    )
    ranking_repo.create(
        data={
            "scene_extraction_id": succeeding_scene.id,
            "model_vendor": "openai",
            "model_name": "test-ranking-model",
            "prompt_version": "test-ranking-v1",
            "scores": {"cinematic": 0.8},
            "overall_priority": 8.9,
            "weight_config": {"cinematic": 1.0},
            "weight_config_hash": "test-weight-hash-2",
            "raw_response": {},
        },
        commit=True,
    )

    async def fake_generate_for_scene(
        self: ImagePromptGenerationService,
        scene,
        **_kwargs,
    ):
        if scene.id == failing_scene.id:
            prompt_repo = ImagePromptRepository(self._session)
            duplicate_record = {
                "scene_extraction_id": scene.id,
                "model_vendor": "openai",
                "model_name": "test-prompt-model",
                "prompt_version": "test-prompt-v1",
                "target_provider": "gpt-image",
                "variant_index": 0,
                "title": "Duplicate prompt",
                "prompt_text": "duplicate prompt text",
                "attributes": {},
                "context_window": {},
                "raw_response": {},
            }
            prompt_repo.create(data=duplicate_record, commit=False, refresh=False)
            prompt_repo.create(data=duplicate_record, commit=False, refresh=False)
        return [SimpleNamespace(id=uuid4())]

    monkeypatch.setattr(
        ImagePromptGenerationService,
        "generate_for_scene",
        fake_generate_for_scene,
    )

    stats = await _run_prompts(
        argparse.Namespace(
            dry_run=False,
            prompts_per_scene=1,
            ignore_ranking_recommendations=True,
            book_slug=book_slug,
            top_scenes=2,
            overwrite=False,
            prompt_art_style_mode=None,
            prompt_art_style_text=None,
        )
    )

    assert stats.prompts_generated == 1
    assert len(stats.errors) == 1
    assert str(failing_scene.id) in stats.errors[0]
