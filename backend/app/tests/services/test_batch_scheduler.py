"""Unit tests for BatchImageScheduler and check_pending_batches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories.image_generation_batch import ImageGenerationBatchRepository
from app.services.image_generation.batch_scheduler import (
    BatchImageScheduler,
    check_pending_batches,
)


@pytest.fixture()
def batch_factory(db: Session):
    """Factory for creating test batch records."""
    created = []

    def _create(**overrides):
        repo = ImageGenerationBatchRepository(db)
        data = {
            "openai_batch_id": f"batch_{uuid4().hex[:8]}",
            "openai_input_file_id": f"file-{uuid4().hex[:8]}",
            "status": "submitted",
            "task_mapping": [],
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "quality": "standard",
            "style": "vivid",
            "size": "1024x1024",
            "total_requests": 1,
        }
        data.update(overrides)
        batch = repo.create(data=data, commit=True)
        created.append(batch)
        return batch

    yield _create

    for batch in created:
        db.refresh(batch)
        db.delete(batch)
    db.commit()


def test_check_pending_batches_processes_completed(db: Session, batch_factory):
    """Test that check_pending_batches processes completed batches."""
    batch = batch_factory(status="in_progress")

    mock_openai_batch = MagicMock()
    mock_openai_batch.status = "completed"
    mock_openai_batch.output_file_id = "file-output-123"
    mock_openai_batch.error_file_id = None
    mock_openai_batch.request_counts = MagicMock()
    mock_openai_batch.request_counts.completed = 1
    mock_openai_batch.request_counts.failed = 0

    mock_client = MagicMock(spec=["batches", "api_key"])
    mock_client.batches.retrieve.return_value = mock_openai_batch
    mock_client.api_key = "sk-test-key"

    mock_service = MagicMock()
    mock_service.process_completed_batch.return_value = []

    with patch(
        "app.services.image_generation.batch_image_generation_service.BatchImageGenerationService",
        return_value=mock_service,
    ):
        check_pending_batches(db, mock_client)

    mock_client.batches.retrieve.assert_any_call(batch.openai_batch_id)
    # process_completed_batch may be called for stale batches left by other tests
    mock_service.process_completed_batch.assert_called()

    db.refresh(batch)
    assert batch.status in ("completed", "processed")


def test_check_pending_batches_ignores_still_in_progress(
    db: Session, batch_factory
):
    """Test that still-in-progress batches are left alone."""
    _batch = batch_factory(status="in_progress")

    mock_openai_batch = MagicMock()
    mock_openai_batch.status = "in_progress"
    mock_openai_batch.request_counts = MagicMock()
    mock_openai_batch.request_counts.completed = 0
    mock_openai_batch.request_counts.failed = 0

    mock_client = MagicMock(spec=["batches", "api_key"])
    mock_client.batches.retrieve.return_value = mock_openai_batch

    with patch(
        "app.services.image_generation.batch_image_generation_service.BatchImageGenerationService"
    ) as MockBatchService:
        check_pending_batches(db, mock_client)

    MockBatchService.return_value.process_completed_batch.assert_not_called()


def test_check_pending_batches_handles_failed(db: Session, batch_factory):
    """Test that failed batches are updated with error info."""
    batch = batch_factory(status="in_progress")

    mock_openai_batch = MagicMock()
    mock_openai_batch.status = "failed"
    mock_openai_batch.request_counts = MagicMock()
    mock_openai_batch.request_counts.completed = 0
    mock_openai_batch.request_counts.failed = 1
    mock_err = MagicMock()
    mock_err.code = "server_error"
    mock_err.message = "Internal server error"
    mock_openai_batch.errors = MagicMock()
    mock_openai_batch.errors.data = [mock_err]

    mock_client = MagicMock(spec=["batches", "api_key"])
    mock_client.batches.retrieve.return_value = mock_openai_batch

    check_pending_batches(db, mock_client)

    db.refresh(batch)
    assert batch.status == "failed"
    assert batch.error is not None
    assert "Internal server error" in batch.error


def test_check_pending_batches_no_pending(db: Session):
    """Test that the function does nothing when no batches are pending."""
    mock_client = MagicMock(spec=["batches"])

    check_pending_batches(db, mock_client)

    mock_client.batches.retrieve.assert_not_called()


@pytest.mark.anyio("asyncio")
async def test_scheduler_start_stop():
    """Test that the scheduler starts and stops cleanly."""
    scheduler = BatchImageScheduler()

    assert not scheduler.is_running

    scheduler.start()
    assert scheduler.is_running

    scheduler.stop()
    assert not scheduler.is_running


@pytest.mark.anyio("asyncio")
async def test_scheduler_double_start():
    """Test that starting an already-started scheduler is safe."""
    scheduler = BatchImageScheduler()

    scheduler.start()
    scheduler.start()  # Should not raise
    assert scheduler.is_running

    scheduler.stop()


def test_scheduler_double_stop():
    """Test that stopping an already-stopped scheduler is safe."""
    scheduler = BatchImageScheduler()

    scheduler.stop()  # Should not raise
    assert not scheduler.is_running
