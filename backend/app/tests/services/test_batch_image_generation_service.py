"""Unit tests for BatchImageGenerationService."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories.image_generation_batch import ImageGenerationBatchRepository
from app.services.image_generation.batch_image_generation_service import (
    _QUALITY_MAPPING,
    BatchImageGenerationService,
    _default_project_root_from_path,
)
from app.services.image_generation.image_generation_service import (
    GenerationTask,
    ImageGenerationConfig,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction


@pytest.fixture()
def anyio_backend() -> str:
    """Batch polling uses asyncio semantics; run async tests on asyncio backend."""
    return "asyncio"


# -- Tests for _build_jsonl --


def test_build_jsonl_produces_valid_format(db: Session) -> None:
    """Test that _build_jsonl produces valid .jsonl with correct structure."""
    service = BatchImageGenerationService(db, api_key="sk-test-key")
    config = ImageGenerationConfig(model="gpt-image-1.5", quality="standard")

    # Create a mock task
    mock_prompt = MagicMock(spec=ImagePrompt)
    mock_prompt.id = uuid4()
    mock_prompt.prompt_text = "A test prompt for image generation"

    task = GenerationTask(
        prompt=mock_prompt,
        variant_index=0,
        size="1024x1024",
        quality="standard",
        style="vivid",
        aspect_ratio="1:1",
        storage_path="img/generated/test-book/chapter-1",
        file_name="scene-1-v0.png",
    )

    jsonl = service._build_jsonl([task], config)
    lines = jsonl.strip().split("\n")

    assert len(lines) == 1
    row = json.loads(lines[0])

    assert row["custom_id"] == f"{mock_prompt.id}_v0"
    assert row["method"] == "POST"
    assert row["url"] == "/v1/images/generations"
    assert row["body"]["model"] == "gpt-image-1.5"
    assert row["body"]["prompt"] == "A test prompt for image generation"
    assert row["body"]["size"] == "1024x1024"
    assert row["body"]["output_format"] == "png"


def test_default_project_root_detects_local_layout() -> None:
    source_file = Path(
        "/Users/test/SceneDream/backend/app/services/image_generation/batch_image_generation_service.py"
    )
    assert _default_project_root_from_path(source_file) == Path(
        "/Users/test/SceneDream"
    )


def test_default_project_root_detects_container_layout() -> None:
    source_file = Path(
        "/app/app/services/image_generation/batch_image_generation_service.py"
    )
    assert _default_project_root_from_path(source_file) == Path("/app")


def test_build_jsonl_quality_mapping_standard(db: Session) -> None:
    """Test that 'standard' quality maps to 'auto' in batch request."""
    service = BatchImageGenerationService(db, api_key="sk-test-key")
    config = ImageGenerationConfig(quality="standard")

    mock_prompt = MagicMock(spec=ImagePrompt)
    mock_prompt.id = uuid4()
    mock_prompt.prompt_text = "test"

    task = GenerationTask(
        prompt=mock_prompt,
        variant_index=0,
        size="1024x1024",
        quality="standard",
        style="vivid",
        aspect_ratio=None,
        storage_path="img/generated/test/chapter-1",
        file_name="scene-1-v0.png",
    )

    jsonl = service._build_jsonl([task], config)
    row = json.loads(jsonl.strip())
    assert row["body"]["quality"] == "auto"


def test_build_jsonl_quality_mapping_hd(db: Session) -> None:
    """Test that 'hd' quality maps to 'high' in batch request."""
    service = BatchImageGenerationService(db, api_key="sk-test-key")
    config = ImageGenerationConfig(quality="hd")

    mock_prompt = MagicMock(spec=ImagePrompt)
    mock_prompt.id = uuid4()
    mock_prompt.prompt_text = "test"

    task = GenerationTask(
        prompt=mock_prompt,
        variant_index=0,
        size="1024x1024",
        quality="hd",
        style="vivid",
        aspect_ratio=None,
        storage_path="img/generated/test/chapter-1",
        file_name="scene-1-v0.png",
    )

    jsonl = service._build_jsonl([task], config)
    row = json.loads(jsonl.strip())
    assert row["body"]["quality"] == "high"


def test_build_jsonl_multiple_tasks(db: Session) -> None:
    """Test that _build_jsonl handles multiple tasks."""
    service = BatchImageGenerationService(db, api_key="sk-test-key")
    config = ImageGenerationConfig(quality="standard")

    tasks = []
    for i in range(3):
        mock_prompt = MagicMock(spec=ImagePrompt)
        mock_prompt.id = uuid4()
        mock_prompt.prompt_text = f"prompt {i}"
        tasks.append(
            GenerationTask(
                prompt=mock_prompt,
                variant_index=i,
                size="1024x1024",
                quality="standard",
                style="vivid",
                aspect_ratio=None,
                storage_path="img/generated/test/chapter-1",
                file_name=f"scene-1-v{i}.png",
            )
        )

    jsonl = service._build_jsonl(tasks, config)
    lines = jsonl.strip().split("\n")
    assert len(lines) == 3

    for i, line in enumerate(lines):
        row = json.loads(line)
        assert row["body"]["prompt"] == f"prompt {i}"


def test_quality_mapping_values() -> None:
    """Test the quality mapping constants."""
    assert _QUALITY_MAPPING["standard"] == "auto"
    assert _QUALITY_MAPPING["hd"] == "high"
    assert _QUALITY_MAPPING.get("high") is None  # already native


# -- Tests for process_completed_batch --


def test_process_completed_batch_saves_images(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    """Test that process_completed_batch creates DB records and saves files."""
    import base64

    scene = scene_factory(book_slug="test-book-batch")
    prompt = prompt_factory(scene, variant_index=0)

    custom_id = f"{prompt.id}_v0"

    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_test_123",
            "openai_input_file_id": "file-input-123",
            "openai_output_file_id": "file-output-123",
            "status": "completed",
            "task_mapping": [
                {
                    "custom_id": custom_id,
                    "image_prompt_id": str(prompt.id),
                    "scene_extraction_id": str(scene.id),
                    "variant_index": 0,
                    "book_slug": scene.book_slug,
                    "chapter_number": scene.chapter_number,
                    "scene_number": scene.scene_number,
                    "storage_path": "img/generated/test-book-batch/chapter-1",
                    "file_name": "scene-1-v0.png",
                    "aspect_ratio": "1:1",
                },
            ],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        },
        commit=True,
    )

    fake_image = base64.b64encode(b"fake-png-data").decode()
    output_line = json.dumps(
        {
            "custom_id": custom_id,
            "response": {
                "status_code": 200,
                "body": {"data": [{"b64_json": fake_image}]},
            },
        }
    )

    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = output_line
    mock_client.files.content.return_value = mock_content

    service = BatchImageGenerationService(db, api_key="sk-test-key")
    service._client = mock_client

    results = service.process_completed_batch(batch)

    assert len(results) == 1
    assert results[0].generated_image_id is not None
    assert results[0].error is None

    # Verify batch was updated to processed
    db.refresh(batch)
    assert batch.status == "processed"
    assert batch.completed_requests == 1
    assert batch.failed_requests == 0


def test_process_completed_batch_handles_errors(db: Session) -> None:
    """Test that process_completed_batch handles failed requests."""
    custom_id = f"{uuid4()}_v0"

    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_err_123",
            "openai_input_file_id": "file-input-err",
            "openai_output_file_id": "file-output-err",
            "status": "completed",
            "task_mapping": [
                {
                    "custom_id": custom_id,
                    "image_prompt_id": str(uuid4()),
                    "scene_extraction_id": str(uuid4()),
                    "variant_index": 0,
                    "book_slug": "test-book",
                    "chapter_number": 1,
                    "scene_number": 1,
                    "storage_path": "img/generated/test-book/chapter-1",
                    "file_name": "scene-1-v0.png",
                    "aspect_ratio": "1:1",
                },
            ],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        },
        commit=True,
    )

    # Build error output
    output_line = json.dumps(
        {
            "custom_id": custom_id,
            "response": {
                "status_code": 400,
                "body": {"error": {"message": "Content policy violation"}},
            },
        }
    )

    mock_client = MagicMock()
    mock_content = MagicMock()
    mock_content.text = output_line
    mock_client.files.content.return_value = mock_content

    service = BatchImageGenerationService(db, api_key="sk-test-key")
    service._client = mock_client

    results = service.process_completed_batch(batch)

    assert len(results) == 1
    assert results[0].error == "Content policy violation"
    assert results[0].generated_image_id is None

    # Cleanup
    db.delete(batch)
    db.commit()


def test_process_completed_batch_no_output_file(db: Session) -> None:
    """Test that process_completed_batch handles missing output file."""
    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_no_output",
            "openai_input_file_id": "file-input-no",
            "openai_output_file_id": None,
            "status": "completed",
            "task_mapping": [],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 0,
        },
        commit=True,
    )

    service = BatchImageGenerationService(db, api_key="sk-test-key")
    results = service.process_completed_batch(batch)

    assert results == []

    # Cleanup
    db.delete(batch)
    db.commit()


# -- Tests for poll timeout --


@pytest.mark.anyio("asyncio")
async def test_poll_batch_timeout(db: Session) -> None:
    """Test that _poll_batch returns after timeout without processing."""
    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_poll_timeout",
            "openai_input_file_id": "file-input-poll",
            "status": "submitted",
            "task_mapping": [],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        },
        commit=True,
    )

    # Mock OpenAI client that always returns in_progress
    mock_batch_response = MagicMock()
    mock_batch_response.status = "in_progress"
    mock_batch_response.request_counts = MagicMock()
    mock_batch_response.request_counts.completed = 0
    mock_batch_response.request_counts.failed = 0
    mock_batch_response.request_counts.total = 1

    service = BatchImageGenerationService(
        db,
        api_key="sk-test-key",
        poll_timeout=1,  # 1 second timeout
        poll_interval=1,  # 1 second interval
    )
    service._client = MagicMock()
    service._client.batches.retrieve.return_value = mock_batch_response

    result = await service._poll_batch(batch)

    # Should still be in_progress after timeout
    assert result.status == "in_progress"

    # Cleanup
    db.delete(batch)
    db.commit()


@pytest.mark.anyio("asyncio")
async def test_poll_batch_completed(db: Session) -> None:
    """Test that _poll_batch returns immediately when batch completes."""
    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_poll_done",
            "openai_input_file_id": "file-input-done",
            "status": "submitted",
            "task_mapping": [],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        },
        commit=True,
    )

    mock_batch_response = MagicMock()
    mock_batch_response.status = "completed"
    mock_batch_response.output_file_id = "file-output-done"
    mock_batch_response.error_file_id = None
    mock_batch_response.request_counts = MagicMock()
    mock_batch_response.request_counts.completed = 1
    mock_batch_response.request_counts.failed = 0

    service = BatchImageGenerationService(
        db,
        api_key="sk-test-key",
        poll_timeout=60,
        poll_interval=1,
    )
    service._client = MagicMock()
    service._client.batches.retrieve.return_value = mock_batch_response

    result = await service._poll_batch(batch)

    assert result.status == "completed"
    assert result.openai_output_file_id == "file-output-done"

    # Cleanup
    db.delete(batch)
    db.commit()


@pytest.mark.anyio("asyncio")
async def test_poll_batch_failed(db: Session) -> None:
    """Test that _poll_batch handles failed batches."""
    batch_repo = ImageGenerationBatchRepository(db)
    batch = batch_repo.create(
        data={
            "openai_batch_id": "batch_poll_fail",
            "openai_input_file_id": "file-input-fail",
            "status": "submitted",
            "task_mapping": [],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        },
        commit=True,
    )

    mock_batch_response = MagicMock()
    mock_batch_response.status = "failed"
    mock_batch_response.request_counts = MagicMock()
    mock_batch_response.request_counts.completed = 0
    mock_batch_response.request_counts.failed = 1
    mock_batch_response.errors = MagicMock()
    mock_err = MagicMock()
    mock_err.code = "invalid_request"
    mock_err.message = "Bad request"
    mock_batch_response.errors.data = [mock_err]

    service = BatchImageGenerationService(
        db,
        api_key="sk-test-key",
        poll_timeout=60,
        poll_interval=1,
    )
    service._client = MagicMock()
    service._client.batches.retrieve.return_value = mock_batch_response

    result = await service._poll_batch(batch)

    assert result.status == "failed"
    assert result.error is not None
    assert "Bad request" in result.error

    # Cleanup
    db.delete(batch)
    db.commit()
