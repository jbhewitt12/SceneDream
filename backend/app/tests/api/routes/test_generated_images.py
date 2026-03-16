"""Tests for generated image API routes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.api.routes.generated_images as generated_images_routes
from app.repositories import (
    AppSettingsRepository,
    GeneratedImageRepository,
    ImagePromptRepository,
    SceneExtractionRepository,
)
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction


def _set_social_posting_enabled(db: Session, enabled: bool) -> bool:
    repository = AppSettingsRepository(db)
    settings = repository.get_or_create_global(commit=True, refresh=True)
    previous = settings.social_posting_enabled
    repository.update(
        settings,
        data={"social_posting_enabled": enabled},
        commit=True,
        refresh=True,
    )
    return previous


@pytest.fixture()
def remix_test_data(db: Session) -> Generator[dict[str, object], None, None]:
    """Create persisted scene, prompt, and generated image for remix tests."""

    scene_repo = SceneExtractionRepository(db)
    prompt_repo = ImagePromptRepository(db)
    image_repo = GeneratedImageRepository(db)

    scene = scene_repo.create(
        data={
            "book_slug": f"test-book-remix-{uuid4()}",
            "source_book_path": "documents/test.epub",
            "chapter_number": 1,
            "chapter_title": "Test Chapter",
            "chapter_source_name": "chapter1.xhtml",
            "scene_number": 1,
            "location_marker": "chapter-1-scene-1",
            "raw": "A mysterious forest under moonlight.",
            "refined": "A mysterious forest glows softly under moonlight.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 2,
            "raw_word_count": 10,
            "raw_char_count": 70,
            "scene_paragraph_start": 1,
            "scene_paragraph_end": 2,
            "scene_word_start": 1,
            "scene_word_end": 40,
            "extraction_model": "test-model",
            "refinement_model": "test-model",
        },
        commit=True,
    )

    prompt = prompt_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "variant_index": 0,
            "title": "Forest Moonlight",
            "prompt_text": "A serene moonlit forest clearing with soft ethereal light.",
            "negative_prompt": None,
            "style_tags": ["dreamy"],
            "attributes": {"lighting": "moonlit", "composition": "wide"},
            "notes": None,
            "context_window": {"chapter_number": 1},
            "raw_response": {},
            "temperature": 0.5,
            "max_output_tokens": 2048,
            "llm_request_id": None,
            "execution_time_ms": 500,
        },
        commit=True,
    )

    image = image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "book_slug": scene.book_slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai",
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "high",
            "style": "vivid",
            "response_format": "b64_json",
            "storage_path": "img/generated/test",
            "file_name": "test.png",
            "aspect_ratio": "1:1",
        },
        commit=True,
    )

    yield {"scene": scene, "prompt": prompt, "image": image}

    # Cleanup order respects FK constraints
    db.delete(image)
    db.delete(prompt)
    db.delete(scene)
    db.commit()


def test_remix_endpoint_schedules_async_task(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure remix endpoint schedules async task without awaiting it."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    prompt: ImagePrompt = remix_test_data["prompt"]  # type: ignore[assignment]

    execute_mock = AsyncMock(name="_execute_remix_generation")
    scheduled_calls: list[tuple[object, str]] = []

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:
        scheduled_calls.append((coro, task_name))
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        generated_images_routes,
        "_execute_remix_generation",
        execute_mock,
    )
    monkeypatch.setattr(
        generated_images_routes,
        "_spawn_background_task",
        _capture_spawn,
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/remix",
        json={"variants_count": 2},
    )

    assert response.status_code == 202
    execute_mock.assert_called_once_with(
        source_image_id=image.id,
        source_prompt_id=prompt.id,
        variants_count=2,
        dry_run=False,
    )
    assert len(scheduled_calls) == 1
    scheduled_coro, task_name = scheduled_calls[0]
    assert asyncio.iscoroutine(scheduled_coro)
    assert execute_mock.await_count == 0
    assert task_name.startswith("remix-generated-image-")


def test_remix_endpoint_task_creation_failure(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service should surface errors if task scheduling fails."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]

    execute_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(
        generated_images_routes,
        "_execute_remix_generation",
        execute_mock,
    )

    def _failing_spawn(coro: object, *, task_name: str) -> None:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        generated_images_routes,
        "_spawn_background_task",
        _failing_spawn,
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/remix",
        json={"variants_count": 1},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to start remix generation"


def test_custom_remix_endpoint_schedules_async_task(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure custom remix endpoint schedules async task and returns promptly."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    prompt: ImagePrompt = remix_test_data["prompt"]  # type: ignore[assignment]

    execute_mock = AsyncMock(name="_execute_custom_remix_generation")
    custom_prompt = prompt
    scheduled_calls: list[tuple[object, str]] = []

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:
        scheduled_calls.append((coro, task_name))
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        generated_images_routes,
        "_execute_custom_remix_generation",
        execute_mock,
    )
    monkeypatch.setattr(
        generated_images_routes,
        "_spawn_background_task",
        _capture_spawn,
    )
    monkeypatch.setattr(
        "app.api.routes.generated_images.ImagePromptGenerationService.create_custom_remix_variant",
        AsyncMock(return_value=custom_prompt),
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/custom-remix",
        json={"custom_prompt_text": "A vibrant aurora over the forest."},
    )

    assert response.status_code == 202
    execute_mock.assert_called_once_with(
        source_image_id=image.id,
        source_prompt_id=prompt.id,
        custom_prompt_id=custom_prompt.id,
        custom_prompt_text="A vibrant aurora over the forest.",
    )
    assert len(scheduled_calls) == 1
    scheduled_coro, task_name = scheduled_calls[0]
    assert asyncio.iscoroutine(scheduled_coro)
    assert execute_mock.await_count == 0
    assert task_name.startswith("custom-remix-generated-image-")


def test_spawn_background_task_logs_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled errors in background tasks should be logged via callback."""

    caplog.set_level(logging.ERROR, logger=generated_images_routes.logger.name)

    async def _failing_task() -> None:
        raise RuntimeError("boom")

    async def _run() -> None:
        task = generated_images_routes._spawn_background_task(
            _failing_task(), task_name="test-task"
        )
        await asyncio.sleep(0)
        assert task.done()

    asyncio.run(_run())

    assert any(
        "Unhandled exception in background task test-task" in message
        for message in caplog.messages
    )


# ---------------------------------------------------------------------------
# File-deletion / 410 Gone tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def file_deleted_image(db: Session) -> Generator[dict[str, object], None, None]:
    """Create a generated image marked as file-deleted."""
    scene_repo = SceneExtractionRepository(db)
    prompt_repo = ImagePromptRepository(db)
    image_repo = GeneratedImageRepository(db)

    scene = scene_repo.create(
        data={
            "book_slug": f"test-book-deleted-{uuid4()}",
            "source_book_path": "documents/test.epub",
            "chapter_number": 1,
            "chapter_title": "Test Chapter",
            "chapter_source_name": "chapter1.xhtml",
            "scene_number": 1,
            "location_marker": "chapter-1-scene-1",
            "raw": "A quiet street at dawn.",
            "refined": "A quiet cobblestone street at dawn.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 2,
            "raw_word_count": 8,
            "raw_char_count": 40,
            "scene_paragraph_start": 1,
            "scene_paragraph_end": 2,
            "scene_word_start": 1,
            "scene_word_end": 20,
            "extraction_model": "test-model",
            "refinement_model": "test-model",
        },
        commit=True,
    )
    prompt = prompt_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "variant_index": 0,
            "title": "Dawn Street",
            "prompt_text": "A quiet cobblestone street at dawn.",
            "negative_prompt": None,
            "style_tags": ["serene"],
            "attributes": {},
            "notes": None,
            "context_window": {"chapter_number": 1},
            "raw_response": {},
            "temperature": 0.5,
            "max_output_tokens": 2048,
            "llm_request_id": None,
            "execution_time_ms": 400,
        },
        commit=True,
    )
    image = image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "book_slug": scene.book_slug,
            "chapter_number": 1,
            "variant_index": 0,
            "provider": "openai",
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "response_format": "b64_json",
            "storage_path": "img/generated/test",
            "file_name": "test-deleted.png",
        },
        commit=True,
    )
    image_repo.mark_file_deleted(image.id, commit=True)

    yield {"scene": scene, "prompt": prompt, "image": image}

    db.delete(image)
    db.delete(prompt)
    db.delete(scene)
    db.commit()


def test_content_endpoint_returns_410_for_deleted_image(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    response = client.get(f"/api/v1/generated-images/{image.id}/content")
    assert response.status_code == 410
    assert response.json()["detail"] == "Image file has been deleted"


def test_crop_endpoint_returns_410_for_deleted_image(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    # Send a minimal file upload
    response = client.put(
        f"/api/v1/generated-images/{image.id}/crop",
        files={"file": ("crop.png", b"fake-png-data", "image/png")},
    )
    assert response.status_code == 410
    assert response.json()["detail"] == "Image file has been deleted"


def test_list_response_excludes_file_deleted_images(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    response = client.get(
        "/api/v1/generated-images",
        params={"book": image.book_slug, "limit": 10},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    matching = [d for d in data if d["id"] == str(image.id)]
    assert matching == []


def test_scene_list_response_excludes_file_deleted_images(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    scene: SceneExtraction = file_deleted_image["scene"]  # type: ignore[assignment]
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    response = client.get(f"/api/v1/generated-images/scene/{scene.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    matching = [d for d in data if d["id"] == str(image.id)]
    assert matching == []


def test_prompt_list_response_excludes_file_deleted_images(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    prompt: ImagePrompt = file_deleted_image["prompt"]  # type: ignore[assignment]
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    response = client.get(f"/api/v1/generated-images/prompt/{prompt.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    matching = [d for d in data if d["id"] == str(image.id)]
    assert matching == []


def test_detail_response_includes_file_deleted_field(
    client: TestClient,
    file_deleted_image: dict[str, object],
) -> None:
    image: GeneratedImage = file_deleted_image["image"]  # type: ignore[assignment]
    response = client.get(f"/api/v1/generated-images/{image.id}")
    assert response.status_code == 200
    img_data = response.json()["image"]
    assert img_data["file_deleted"] is True
    assert img_data["file_deleted_at"] is not None


def test_queue_for_posting_returns_409_when_social_posting_disabled(
    client: TestClient,
    db: Session,
    remix_test_data: dict[str, object],
) -> None:
    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    previous = _set_social_posting_enabled(db, False)
    image.user_approved = True
    db.add(image)
    db.commit()
    db.refresh(image)

    try:
        response = client.post(f"/api/v1/generated-images/{image.id}/queue-for-posting")
        assert response.status_code == 409
        assert (
            response.json()["detail"] == "Social media posting is disabled in Settings"
        )
    finally:
        _set_social_posting_enabled(db, previous)


def test_posting_status_returns_409_when_social_posting_disabled(
    client: TestClient,
    db: Session,
    remix_test_data: dict[str, object],
) -> None:
    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    previous = _set_social_posting_enabled(db, False)

    try:
        response = client.get(f"/api/v1/generated-images/{image.id}/posting-status")
        assert response.status_code == 409
        assert (
            response.json()["detail"] == "Social media posting is disabled in Settings"
        )
    finally:
        _set_social_posting_enabled(db, previous)


def test_retry_failed_posts_returns_409_when_social_posting_disabled(
    client: TestClient,
    db: Session,
) -> None:
    previous = _set_social_posting_enabled(db, False)

    try:
        response = client.post("/api/v1/generated-images/retry-failed-posts")
        assert response.status_code == 409
        assert (
            response.json()["detail"] == "Social media posting is disabled in Settings"
        )
    finally:
        _set_social_posting_enabled(db, previous)
