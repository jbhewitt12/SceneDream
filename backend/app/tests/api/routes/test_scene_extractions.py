"""Tests for scene extraction API routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.scene_extractions as scene_extractions_routes
from app.services.pipeline import (
    PipelineExecutionResult,
    PipelineOrchestrator,
    PipelineStats,
)


def test_list_scene_extractions_applies_filters_and_pagination(
    client: TestClient,
    scene_factory,
) -> None:
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    matching_scene = scene_factory(
        book_slug=f"test-book-scenes-{uuid4()}",
        chapter_number=3,
        scene_number=1,
        chapter_title="Sky Harbor",
        location_marker="Docking Bay 7",
        raw="Neon skyline glows above the harbor.",
        refined="Neon skyline glows above the harbor while ships descend.",
        refinement_decision="keep",
        extracted_at=base_time,
    )
    scene_factory(
        book_slug=matching_scene.book_slug,
        chapter_number=3,
        scene_number=2,
        raw="A maintenance drone drifts past the bay doors.",
        refined=None,
        refinement_decision="discard",
        extracted_at=base_time + timedelta(minutes=1),
    )
    scene_factory(
        book_slug=f"test-book-other-{uuid4()}",
        chapter_number=9,
        scene_number=1,
        raw="Unrelated scene that should not match filters.",
        refined="Unrelated scene refined.",
        refinement_decision="keep",
        extracted_at=base_time + timedelta(minutes=2),
    )

    response = client.get(
        "/api/v1/scene-extractions/",
        params={
            "page": 1,
            "page_size": 10,
            "book_slug": matching_scene.book_slug,
            "chapter_number": 3,
            "decision": "keep",
            "has_refined": True,
            "search": "skyline",
            "start_date": (base_time - timedelta(minutes=1)).isoformat(),
            "end_date": (base_time + timedelta(minutes=1)).isoformat(),
            "order": "asc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 10
    assert [item["id"] for item in payload["data"]] == [str(matching_scene.id)]


def test_scene_extraction_filters_returns_expected_options(
    client: TestClient,
    scene_factory,
) -> None:
    first_time = datetime(2025, 2, 1, tzinfo=timezone.utc)
    second_time = datetime(2025, 2, 2, tzinfo=timezone.utc)

    first = scene_factory(
        book_slug=f"test-book-filters-a-{uuid4()}",
        chapter_number=2,
        scene_number=1,
        refinement_decision="keep",
        refined="A calm orbiting station.",
        extracted_at=first_time,
    )
    second = scene_factory(
        book_slug=f"test-book-filters-b-{uuid4()}",
        chapter_number=4,
        scene_number=1,
        refinement_decision="discard",
        refined=None,
        extracted_at=second_time,
    )

    response = client.get("/api/v1/scene-extractions/filters")

    assert response.status_code == 200
    payload = response.json()
    assert first.book_slug in payload["books"]
    assert second.book_slug in payload["books"]
    assert payload["chapters_by_book"][first.book_slug] == [2]
    assert payload["chapters_by_book"][second.book_slug] == [4]
    assert "keep" in payload["refinement_decisions"]
    assert "discard" in payload["refinement_decisions"]
    assert set(payload["has_refined_options"]) == {True, False}
    assert payload["date_range"]["earliest"] is not None
    assert payload["date_range"]["latest"] is not None


def test_get_scene_extraction_by_id_and_not_found(
    client: TestClient,
    scene_factory,
) -> None:
    scene = scene_factory(chapter_title="Route Read Test")

    response = client.get(f"/api/v1/scene-extractions/{scene.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(scene.id)
    assert payload["chapter_title"] == "Route Read Test"

    missing_response = client.get(f"/api/v1/scene-extractions/{uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Scene extraction not found"


# ---------------------------------------------------------------------------
# Tests: POST /{scene_id}/generate
# ---------------------------------------------------------------------------


def _mock_orchestrator_for_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AsyncMock, list[tuple[object, str]]]:
    """Set up mocks for the scene generate endpoint."""
    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )
    scheduled_calls: list[tuple[object, str]] = []

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:
        scheduled_calls.append((coro, task_name))
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        scene_extractions_routes,
        "spawn_background_task",
        _capture_spawn,
    )
    return execute_mock, scheduled_calls


def test_generate_for_scene_creates_pending_run(
    client: TestClient,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory()

    execute_mock, scheduled_calls = _mock_orchestrator_for_generate(monkeypatch)

    response = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={"num_images": 3},
    )

    assert response.status_code == 202
    payload = response.json()
    assert "pipeline_run_id" in payload
    assert payload["status"] == "pending"
    assert "3" in payload["message"]

    execute_mock.assert_called_once()
    assert len(scheduled_calls) == 1
    _, task_name = scheduled_calls[0]
    assert task_name.startswith("scene-generate-")


def test_generate_for_scene_returns_404_for_missing_scene(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_orchestrator_for_generate(monkeypatch)

    response = client.post(
        f"/api/v1/scene-extractions/{uuid4()}/generate",
        json={"num_images": 2},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Scene extraction not found"


def test_generate_for_scene_validates_num_images(
    client: TestClient,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory()
    _mock_orchestrator_for_generate(monkeypatch)

    response = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={"num_images": 0},
    )
    assert response.status_code == 422

    response_high = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={"num_images": 21},
    )
    assert response_high.status_code == 422


def test_generate_for_scene_passes_art_style_options(
    client: TestClient,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory()

    execute_mock, _ = _mock_orchestrator_for_generate(monkeypatch)

    response = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={
            "num_images": 2,
            "prompt_art_style_mode": "single_style",
            "prompt_art_style_text": "Watercolor",
            "quality": "hd",
            "style": "vivid",
            "aspect_ratio": "16:9",
        },
    )

    assert response.status_code == 202
    # Verify the orchestrator was called with the right config
    call_args = execute_mock.call_args
    prepared = call_args[0][0]
    assert prepared.config.prompt_options.scene_variant_count == 2
    assert prepared.config.prompt_options.require_exact_scene_variants is True
    assert prepared.config.image_options.quality == "hd"
    assert prepared.config.image_options.style == "vivid"
    assert prepared.config.image_options.aspect_ratio == "16:9"


def test_generate_for_scene_derives_document_context(
    client: TestClient,
    scene_factory,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scene-targeted runs should derive document context from the scene."""
    from app.repositories import DocumentRepository

    doc_repo = DocumentRepository(db)
    slug = f"test-doc-ctx-{uuid4()}"
    doc = doc_repo.create(
        data={
            "slug": slug,
            "display_name": "Test Doc",
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    scene = scene_factory(book_slug=slug)

    execute_mock, _ = _mock_orchestrator_for_generate(monkeypatch)

    response = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={"num_images": 1},
    )

    assert response.status_code == 202
    call_args = execute_mock.call_args
    prepared = call_args[0][0]
    assert prepared.context.book_slug == slug
    assert prepared.context.document_id == doc.id

    db.delete(doc)
    db.commit()


def test_generate_for_scene_task_creation_failure(
    client: TestClient,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory()

    def _failing_spawn(coro: object, *, task_name: str) -> None:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        scene_extractions_routes,
        "spawn_background_task",
        _failing_spawn,
    )

    response = client.post(
        f"/api/v1/scene-extractions/{scene.id}/generate",
        json={"num_images": 2},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to start scene generation"
