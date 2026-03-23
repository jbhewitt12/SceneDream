"""Tests for generated image API routes."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.repositories import (
    AppSettingsRepository,
    GeneratedImageRepository,
    ImagePromptRepository,
    PipelineRunRepository,
    SceneExtractionRepository,
)
from app.services.image_prompt_generation.image_prompt_generation_service import (
    ImagePromptGenerationServiceError,
)
from app.services.pipeline.orchestrator_config import (
    PreparedPipelineExecution,
)
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction


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


def _mock_prepare_execution(
    monkeypatch: pytest.MonkeyPatch,
    run_id: object | None = None,
    *,
    custom_remix: bool = False,
) -> MagicMock:
    """Mock prepare_execution to return a PreparedPipelineExecution."""
    from app.services.pipeline.orchestrator_config import (
        CustomRemixTarget,
        PipelineExecutionConfig,
        PipelineExecutionContext,
        PipelineStagePlan,
        RemixTarget,
    )

    rid = run_id or uuid4()
    if custom_remix:
        target: RemixTarget | CustomRemixTarget = CustomRemixTarget(
            source_image_id=uuid4(),
            source_prompt_id=uuid4(),
            custom_prompt_text="test prompt",
        )
    else:
        target = RemixTarget(
            source_image_id=uuid4(),
            source_prompt_id=uuid4(),
        )

    prepared = PreparedPipelineExecution(
        run_id=rid,  # type: ignore[arg-type]
        config=PipelineExecutionConfig(
            target=target,
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        ),
        config_overrides={},
        context=PipelineExecutionContext(book_slug="test-book"),
    )
    mock_prepare = MagicMock(return_value=prepared)
    monkeypatch.setattr(
        "app.api.routes.generated_images.PipelineRunStartService.prepare_execution",
        mock_prepare,
    )
    return mock_prepare


def _mock_orchestrator_and_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, list[tuple[object, str]]]:
    """Mock PipelineOrchestrator.execute and spawn_background_task."""
    execute_mock = AsyncMock(name="PipelineOrchestrator.execute")
    monkeypatch.setattr(
        "app.api.routes.generated_images.PipelineOrchestrator.execute",
        execute_mock,
    )

    scheduled_calls: list[tuple[object, str]] = []

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:
        scheduled_calls.append((coro, task_name))
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        "app.api.routes.generated_images.spawn_background_task",
        _capture_spawn,
    )
    return execute_mock, scheduled_calls


def test_remix_endpoint_creates_pending_run_and_schedules_task(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remix endpoint creates a pending PipelineRun via prepare_execution
    and spawns orchestrator execution in the background."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    run_id = uuid4()

    _mock_prepare_execution(monkeypatch, run_id=run_id)
    execute_mock, scheduled_calls = _mock_orchestrator_and_spawn(monkeypatch)

    response = client.post(
        f"/api/v1/generated-images/{image.id}/remix",
        json={"variants_count": 2},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["pipeline_run_id"] == str(run_id)
    assert data["status"] == "accepted"
    assert len(scheduled_calls) == 1
    assert scheduled_calls[0][1].startswith("remix-generated-image-")


def test_remix_endpoint_returns_pipeline_run_id(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response must include pipeline_run_id."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    run_id = uuid4()

    _mock_prepare_execution(monkeypatch, run_id=run_id)
    _mock_orchestrator_and_spawn(monkeypatch)

    response = client.post(
        f"/api/v1/generated-images/{image.id}/remix",
        json={},
    )

    assert response.status_code == 202
    data = response.json()
    assert "pipeline_run_id" in data
    assert data["pipeline_run_id"] == str(run_id)


def test_remix_endpoint_task_creation_failure(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service should surface errors if task scheduling fails."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]

    _mock_prepare_execution(monkeypatch)

    execute_mock = AsyncMock(name="PipelineOrchestrator.execute")
    monkeypatch.setattr(
        "app.api.routes.generated_images.PipelineOrchestrator.execute",
        execute_mock,
    )

    def _failing_spawn(coro: object, *, task_name: str) -> None:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        "app.api.routes.generated_images.spawn_background_task",
        _failing_spawn,
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/remix",
        json={"variants_count": 1},
    )

    assert response.status_code == 500
    detail = _assert_app_error(
        response.json(),
        code="remix_generation_start_failed",
        message="scheduler unavailable",
    )
    assert "scheduler unavailable" in detail["cause_messages"]


def test_custom_remix_endpoint_creates_pending_run_and_schedules_task(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom remix creates a pending run, creates custom prompt in request scope,
    and spawns orchestrator execution."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    prompt: ImagePrompt = remix_test_data["prompt"]  # type: ignore[assignment]
    run_id = uuid4()

    _mock_prepare_execution(monkeypatch, run_id=run_id, custom_remix=True)
    execute_mock, scheduled_calls = _mock_orchestrator_and_spawn(monkeypatch)

    # Mock create_custom_remix_variant to return the existing prompt as the custom prompt
    monkeypatch.setattr(
        "app.api.routes.generated_images.ImagePromptGenerationService.create_custom_remix_variant",
        AsyncMock(return_value=prompt),
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/custom-remix",
        json={"custom_prompt_text": "A vibrant aurora over the forest."},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["pipeline_run_id"] == str(run_id)
    assert data["custom_prompt_id"] == str(prompt.id)
    assert data["status"] == "accepted"
    assert len(scheduled_calls) == 1
    assert scheduled_calls[0][1].startswith("custom-remix-generated-image-")


def test_custom_remix_endpoint_returns_pipeline_run_id(
    client: TestClient,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom remix response must include pipeline_run_id."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]
    prompt: ImagePrompt = remix_test_data["prompt"]  # type: ignore[assignment]
    run_id = uuid4()

    _mock_prepare_execution(monkeypatch, run_id=run_id, custom_remix=True)
    _mock_orchestrator_and_spawn(monkeypatch)

    monkeypatch.setattr(
        "app.api.routes.generated_images.ImagePromptGenerationService.create_custom_remix_variant",
        AsyncMock(return_value=prompt),
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/custom-remix",
        json={"custom_prompt_text": "Test prompt text."},
    )

    assert response.status_code == 202
    data = response.json()
    assert "pipeline_run_id" in data
    assert data["pipeline_run_id"] == str(run_id)


def test_custom_remix_prompt_creation_failure_fails_pending_run(
    client: TestClient,
    db: Session,
    remix_test_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If custom prompt creation fails, the pending run should be marked as failed."""

    image: GeneratedImage = remix_test_data["image"]  # type: ignore[assignment]

    # Create a real pending pipeline run so we can verify it gets failed
    run_repo = PipelineRunRepository(db)
    run = run_repo.create(
        data={
            "book_slug": image.book_slug,
            "status": "pending",
            "current_stage": "pending",
            "config_overrides": {},
        },
        commit=True,
        refresh=True,
    )
    run_id = run.id

    from app.services.pipeline.orchestrator_config import (
        CustomRemixTarget,
        PipelineExecutionConfig,
        PipelineExecutionContext,
        PipelineStagePlan,
    )

    prepared = PreparedPipelineExecution(
        run_id=run_id,
        config=PipelineExecutionConfig(
            target=CustomRemixTarget(
                source_image_id=image.id,
                source_prompt_id=image.image_prompt_id,
                custom_prompt_text="Will fail",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        ),
        config_overrides={},
        context=PipelineExecutionContext(book_slug=image.book_slug),
    )
    monkeypatch.setattr(
        "app.api.routes.generated_images.PipelineRunStartService.prepare_execution",
        MagicMock(return_value=prepared),
    )
    _mock_orchestrator_and_spawn(monkeypatch)

    # Make prompt creation fail
    monkeypatch.setattr(
        "app.api.routes.generated_images.ImagePromptGenerationService.create_custom_remix_variant",
        AsyncMock(side_effect=ImagePromptGenerationServiceError("prompt gen failed")),
    )

    response = client.post(
        f"/api/v1/generated-images/{image.id}/custom-remix",
        json={"custom_prompt_text": "Will fail"},
    )

    assert response.status_code == 400
    detail = _assert_app_error(
        response.json(),
        code="custom_remix_prompt_creation_failed",
        message="prompt gen failed",
    )
    assert "prompt gen failed" in detail["cause_messages"]

    # Verify the pipeline run was marked as failed
    db.expire_all()
    failed_run = run_repo.get(run_id)
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert "prompt gen failed" in (failed_run.error_message or "")

    # Cleanup
    db.delete(failed_run)
    db.commit()


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
    _assert_app_error(
        response.json(),
        code="generated_image_deleted",
        message="Image file has been deleted",
    )


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
