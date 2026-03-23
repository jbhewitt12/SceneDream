"""Tests for image prompt API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.image_prompts as image_prompts_routes
from app.services.prompt_metadata.prompt_metadata_service import (
    PromptMetadataGenerationServiceError,
)


def _assert_app_error(
    payload: dict[str, object],
    *,
    code: str,
    message: str,
) -> dict[str, object]:
    detail = payload["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == code
    assert detail["message"] == message
    return detail


def test_list_prompts_for_scene_with_filters(
    client: TestClient,
    scene_factory,
    prompt_factory,
) -> None:
    scene = scene_factory(book_slug=f"test-book-scene-prompts-{uuid4()}")
    matching = prompt_factory(
        scene,
        model_name="meta-model",
        prompt_version="meta-v1",
    )
    prompt_factory(
        scene,
        model_name="other-model",
        prompt_version="meta-v2",
    )

    response = client.get(
        f"/api/v1/image-prompts/scene/{scene.id}",
        params={
            "model_name": "meta-model",
            "prompt_version": "meta-v1",
            "include_scene": True,
            "limit": 5,
            "newest_first": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["scene_extraction_id"] == str(scene.id)
    assert payload["meta"]["model_name"] == "meta-model"
    assert payload["meta"]["prompt_version"] == "meta-v1"
    assert len(payload["data"]) == 1
    assert payload["data"][0]["id"] == str(matching.id)
    assert payload["data"][0]["scene"]["id"] == str(scene.id)


def test_list_prompts_global_filters(
    client: TestClient,
    scene_factory,
    prompt_factory,
) -> None:
    slug = f"test-book-global-prompts-{uuid4()}"
    scene_one = scene_factory(book_slug=slug, chapter_number=1)
    scene_two = scene_factory(book_slug=slug, chapter_number=2)
    scene_other = scene_factory(book_slug=f"test-book-other-prompts-{uuid4()}")

    prompt_factory(
        scene_one,
        model_name="global-model",
        prompt_version="global-v1",
        style_tags=["vaporwave"],
    )
    expected = prompt_factory(
        scene_two,
        model_name="global-model",
        prompt_version="global-v1",
        style_tags=["vaporwave", "cinematic"],
    )
    prompt_factory(
        scene_other,
        model_name="global-model",
        prompt_version="global-v1",
        style_tags=["vaporwave"],
    )

    response = client.get(
        "/api/v1/image-prompts/list",
        params={
            "book_slug": slug,
            "chapter_number": 2,
            "model_name": "global-model",
            "prompt_version": "global-v1",
            "style_tag": "vaporwave",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["book_slug"] == slug
    assert payload["meta"]["chapter_number"] == 2
    assert payload["meta"]["model_name"] == "global-model"
    assert payload["meta"]["prompt_version"] == "global-v1"
    assert payload["meta"]["style_tag"] == "vaporwave"
    assert payload["meta"]["offset"] == 0
    assert len(payload["data"]) == 1
    assert payload["data"][0]["id"] == str(expected.id)


def test_list_prompts_for_book(
    client: TestClient,
    scene_factory,
    prompt_factory,
) -> None:
    slug = f"test-book-book-route-{uuid4()}"
    scene_one = scene_factory(book_slug=slug, chapter_number=1)
    scene_two = scene_factory(book_slug=slug, chapter_number=2)

    prompt_factory(scene_one, model_name="book-model", prompt_version="book-v1")
    matching = prompt_factory(
        scene_two,
        model_name="book-model",
        prompt_version="book-v1",
        style_tags=["noir"],
    )

    response = client.get(
        f"/api/v1/image-prompts/book/{slug}",
        params={
            "chapter_number": 2,
            "model_name": "book-model",
            "prompt_version": "book-v1",
            "style_tag": "noir",
            "limit": 10,
            "offset": 0,
            "include_scene": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["book_slug"] == slug
    assert payload["meta"]["chapter_number"] == 2
    assert payload["meta"]["model_name"] == "book-model"
    assert payload["meta"]["prompt_version"] == "book-v1"
    assert payload["meta"]["style_tag"] == "noir"
    assert len(payload["data"]) == 1
    assert payload["data"][0]["id"] == str(matching.id)
    assert payload["data"][0]["scene"]["id"] == str(scene_two.id)


def test_get_image_prompt_by_id_and_not_found(
    client: TestClient,
    scene_factory,
    prompt_factory,
) -> None:
    scene = scene_factory(book_slug=f"test-book-get-prompt-{uuid4()}")
    prompt = prompt_factory(scene)

    response = client.get(
        f"/api/v1/image-prompts/{prompt.id}",
        params={"include_scene": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(prompt.id)
    assert payload["scene_extraction_id"] == str(scene.id)
    assert payload["scene"]["id"] == str(scene.id)

    missing_response = client.get(f"/api/v1/image-prompts/{uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Image prompt not found"


def test_generate_metadata_variants_success(
    client: TestClient,
    scene_factory,
    prompt_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory(book_slug=f"test-book-generate-meta-{uuid4()}")
    prompt = prompt_factory(scene)

    generate_mock = AsyncMock(
        return_value=[
            {
                "title": "Steel Horizon",
                "flavour_text": "Stormlight hums beneath the city's sleeping machinery.",
            },
            {
                "title": "Glass Orbit",
                "flavour_text": "Even silence bends when engines dream beyond the atmosphere.",
            },
        ]
    )
    monkeypatch.setattr(
        image_prompts_routes.PromptMetadataGenerationService,
        "generate_metadata_variants",
        generate_mock,
    )

    response = client.post(
        f"/api/v1/image-prompts/{prompt.id}/metadata/generate",
        json={"variants_count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt_id"] == str(prompt.id)
    assert payload["count"] == 2
    assert payload["variants"][0]["title"] == "Steel Horizon"
    assert payload["variants"][1]["title"] == "Glass Orbit"

    generate_mock.assert_awaited_once()
    assert generate_mock.await_args.kwargs["variants_count"] == 2


def test_generate_metadata_variants_not_found(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/image-prompts/{uuid4()}/metadata/generate",
        json={"variants_count": 2},
    )

    assert response.status_code == 404
    _assert_app_error(
        response.json(),
        code="image_prompt_not_found",
        message="Image prompt not found",
    )


def test_generate_metadata_variants_server_error(
    client: TestClient,
    scene_factory,
    prompt_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory(book_slug=f"test-book-meta-error-{uuid4()}")
    prompt = prompt_factory(scene)

    async def _raise_error(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        raise PromptMetadataGenerationServiceError("metadata provider failed")

    monkeypatch.setattr(
        image_prompts_routes.PromptMetadataGenerationService,
        "generate_metadata_variants",
        _raise_error,
    )

    response = client.post(
        f"/api/v1/image-prompts/{prompt.id}/metadata/generate",
        json={"variants_count": 3},
    )

    assert response.status_code == 500
    detail = _assert_app_error(
        response.json(),
        code="metadata_generation_failed",
        message="metadata provider failed",
    )
    assert "metadata provider failed" in detail["cause_messages"]


def test_update_prompt_metadata_success(
    client: TestClient,
    scene_factory,
    prompt_factory,
) -> None:
    scene = scene_factory(book_slug=f"test-book-update-meta-{uuid4()}")
    prompt = prompt_factory(scene, title="Old Title", flavour_text=None)

    response = client.patch(
        f"/api/v1/image-prompts/{prompt.id}/metadata",
        json={
            "title": "Updated Title",
            "flavour_text": "The city exhales static as dawn ignites the towers.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(prompt.id)
    assert payload["title"] == "Updated Title"
    assert (
        payload["flavour_text"] == "The city exhales static as dawn ignites the towers."
    )


def test_update_prompt_metadata_not_found(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/image-prompts/{uuid4()}/metadata",
        json={"title": "Updated"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Image prompt not found"


def test_update_prompt_metadata_requires_payload_field(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/image-prompts/{uuid4()}/metadata",
        json={},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "At least one metadata field must be provided"
