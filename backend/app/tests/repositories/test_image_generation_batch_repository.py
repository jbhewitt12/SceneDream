"""Tests for ImageGenerationBatchRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session

from app.repositories import ImageGenerationBatchRepository


def _batch_payload(**overrides: object) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    data: dict[str, object] = {
        "openai_batch_id": f"batch-{uuid4()}",
        "openai_input_file_id": f"file-{uuid4()}",
        "openai_output_file_id": None,
        "openai_error_file_id": None,
        "status": "submitted",
        "task_mapping": [{"custom_id": "scene-1", "scene_extraction_id": str(uuid4())}],
        "provider": "openai",
        "model": "gpt-image-1",
        "quality": "high",
        "style": "vivid",
        "size": "1024x1024",
        "total_requests": 1,
        "completed_requests": 0,
        "failed_requests": 0,
        "book_slug": f"test-book-batch-{uuid4()}",
        "error": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    data.update(overrides)
    return data


def test_create_get_and_get_by_openai_batch_id(db: Session) -> None:
    repository = ImageGenerationBatchRepository(db)
    batch = repository.create(data=_batch_payload(), commit=True)

    fetched = repository.get(batch.id)
    assert fetched is not None
    assert fetched.id == batch.id

    by_openai_id = repository.get_by_openai_batch_id(batch.openai_batch_id)
    assert by_openai_id is not None
    assert by_openai_id.id == batch.id

    db.delete(batch)
    db.commit()


def test_list_pending_filters_expected_statuses(db: Session) -> None:
    repository = ImageGenerationBatchRepository(db)
    base_time = datetime(2025, 7, 1, tzinfo=timezone.utc)

    submitted = repository.create(
        data=_batch_payload(status="submitted", created_at=base_time),
        commit=True,
    )
    validating = repository.create(
        data=_batch_payload(
            status="validating",
            created_at=base_time + timedelta(minutes=1),
        ),
        commit=True,
    )
    in_progress = repository.create(
        data=_batch_payload(
            status="in_progress",
            created_at=base_time + timedelta(minutes=2),
        ),
        commit=True,
    )
    completed = repository.create(
        data=_batch_payload(
            status="completed",
            created_at=base_time + timedelta(minutes=3),
        ),
        commit=True,
    )

    pending = repository.list_pending()
    assert [batch.id for batch in pending] == [
        submitted.id,
        validating.id,
        in_progress.id,
    ]
    assert completed.id not in {batch.id for batch in pending}

    for batch in [submitted, validating, in_progress, completed]:
        db.delete(batch)
    db.commit()


def test_update_status_updates_fields_and_handles_missing(db: Session) -> None:
    repository = ImageGenerationBatchRepository(db)
    batch = repository.create(data=_batch_payload(status="submitted"), commit=True)

    previous_updated_at = batch.updated_at
    updated = repository.update_status(
        batch.id,
        "completed",
        completed_requests=1,
        failed_requests=0,
        openai_output_file_id="file-output-1",
        error=None,
    )

    assert updated is not None
    assert updated.status == "completed"
    assert updated.completed_requests == 1
    assert updated.openai_output_file_id == "file-output-1"
    assert updated.updated_at >= previous_updated_at

    missing = repository.update_status(uuid4(), "failed", error="missing")
    assert missing is None

    db.delete(batch)
    db.commit()
