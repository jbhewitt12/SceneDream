from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.image_gen_cli import _count_prompt_ready_scenes_without_images


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
