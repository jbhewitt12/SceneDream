"""Tests for pipeline run API routes."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.api.routes.pipeline_runs as pipeline_runs_routes
from app.repositories import (
    AppSettingsRepository,
    DocumentRepository,
    PipelineRunRepository,
)
from app.services.pipeline import (
    PipelineExecutionResult,
    PipelineOrchestrator,
    PipelineRunStartService,
    PipelineStats,
    PreparedPipelineExecution,
)
from app.services.pipeline.orchestrator_config import (
    DocumentTarget,
    PipelineExecutionConfig,
    PipelineExecutionContext,
    PipelineStagePlan,
)
from models.document import Document


@pytest.fixture()
def pipeline_document(db: Session) -> Generator[Document, None, None]:
    repository = DocumentRepository(db)
    slug = f"test-book-pipeline-{uuid4()}"
    document = repository.create(
        data={
            "slug": slug,
            "display_name": "Pipeline Test Document",
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {"test": True},
        },
        commit=True,
    )
    yield document
    db.delete(document)
    db.commit()


def test_start_pipeline_run_schedules_background_task(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

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
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )
    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )

    slug = f"test-book-{uuid4()}"
    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "book_slug": slug,
            "book_path": f"documents/{slug}.epub",
            "images_for_scenes": 2,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["book_slug"] == slug
    assert payload["status"] == "pending"
    assert payload["current_stage"] == "pending"

    execute_mock.assert_called_once()
    assert len(scheduled_calls) == 1
    scheduled_coro, task_name = scheduled_calls[0]
    assert asyncio.iscoroutine(scheduled_coro)
    assert task_name.startswith("pipeline-run-")


def test_start_pipeline_run_task_creation_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    def _failing_spawn(coro: object, *, task_name: str) -> None:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _failing_spawn,
    )

    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "book_slug": f"test-book-{uuid4()}",
            "book_path": "documents/test.epub",
            "images_for_scenes": 1,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to start pipeline run"


def test_start_pipeline_run_uses_document_defaults(
    client: TestClient,
    pipeline_document: Document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    document = pipeline_document
    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )

    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "document_id": str(document.id),
            "images_for_scenes": 1,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["document_id"] == str(document.id)
    assert payload["book_slug"] == document.slug


def test_start_pipeline_run_allows_resume_when_source_path_missing(
    client: TestClient,
    pipeline_document: Document,
    scene_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_factory(
        book_slug=pipeline_document.slug,
        source_book_path=pipeline_document.source_path,
        document_id=pipeline_document.id,
    )

    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )

    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "document_id": str(pipeline_document.id),
            "images_for_scenes": 1,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["config_overrides"]["skip_extraction"] is True


def test_start_pipeline_run_preserves_image_generation_skip_flags(
    client: TestClient,
    pipeline_document: Document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )

    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "document_id": str(pipeline_document.id),
            "images_for_scenes": 1,
            "skip_extraction": True,
            "skip_ranking": True,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["config_overrides"]["skip_extraction"] is True
    assert payload["config_overrides"]["skip_ranking"] is True


def test_start_pipeline_run_rejects_missing_source_when_no_resume_data(
    client: TestClient,
    pipeline_document: Document,
) -> None:
    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "document_id": str(pipeline_document.id),
            "images_for_scenes": 1,
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "book_path does not exist and no extracted scenes are available to resume"
    )


def test_start_pipeline_run_applies_single_style_override(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )

    settings_repo = AppSettingsRepository(db)
    settings = settings_repo.get_or_create_global(commit=True, refresh=True)
    original_mode = settings.default_prompt_art_style_mode
    original_text = settings.default_prompt_art_style_text

    try:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": "random_mix",
                "default_prompt_art_style_text": None,
            },
            commit=True,
            refresh=True,
        )
        slug = f"test-book-{uuid4()}"
        response = client.post(
            "/api/v1/pipeline-runs",
            json={
                "book_slug": slug,
                "book_path": f"documents/{slug}.epub",
                "images_for_scenes": 2,
                "prompt_art_style_mode": "single_style",
                "prompt_art_style_text": "Pipeline Style Override",
            },
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["config_overrides"]["resolved_prompt_art_style_mode"] == (
            "single_style"
        )
        assert payload["config_overrides"]["resolved_prompt_art_style_text"] == (
            "Pipeline Style Override"
        )
    finally:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": original_mode,
                "default_prompt_art_style_text": original_text,
            },
            commit=True,
            refresh=True,
        )


def test_start_pipeline_run_uses_settings_prompt_art_style_defaults(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    execute_mock = AsyncMock(
        name="orchestrator_execute",
        return_value=PipelineExecutionResult(
            run_id=uuid4(), status="completed", stats=PipelineStats()
        ),
    )

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        PipelineOrchestrator,
        "execute",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "spawn_background_task",
        _capture_spawn,
    )

    settings_repo = AppSettingsRepository(db)
    settings = settings_repo.get_or_create_global(commit=True, refresh=True)
    original_mode = settings.default_prompt_art_style_mode
    original_text = settings.default_prompt_art_style_text

    try:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": "single_style",
                "default_prompt_art_style_text": "Settings Default Style",
            },
            commit=True,
            refresh=True,
        )

        slug = f"test-book-{uuid4()}"
        response = client.post(
            "/api/v1/pipeline-runs",
            json={
                "book_slug": slug,
                "book_path": f"documents/{slug}.epub",
                "images_for_scenes": 1,
            },
        )

        assert response.status_code == 202
        payload = response.json()
        assert payload["config_overrides"]["resolved_prompt_art_style_mode"] == (
            "single_style"
        )
        assert payload["config_overrides"]["resolved_prompt_art_style_text"] == (
            "Settings Default Style"
        )
    finally:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": original_mode,
                "default_prompt_art_style_text": original_text,
            },
            commit=True,
            refresh=True,
        )


def test_start_pipeline_run_rejects_blank_single_style_text(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    slug = f"test-book-{uuid4()}"
    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "book_slug": slug,
            "book_path": f"documents/{slug}.epub",
            "images_for_scenes": 1,
            "prompt_art_style_mode": "single_style",
            "prompt_art_style_text": "   ",
        },
    )

    assert response.status_code == 422
    assert "prompt_art_style_text is required" in response.json()["detail"][0]["msg"]


def test_start_pipeline_run_rejects_invalid_settings_single_style_defaults(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_runs_routes.PipelineRunStartService,
        "_source_path_exists",
        lambda _self, _source_path: True,
    )

    settings_repo = AppSettingsRepository(db)
    settings = settings_repo.get_or_create_global(commit=True, refresh=True)
    original_mode = settings.default_prompt_art_style_mode
    original_text = settings.default_prompt_art_style_text

    try:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": "single_style",
                "default_prompt_art_style_text": None,
            },
            commit=True,
            refresh=True,
        )
        slug = f"test-book-{uuid4()}"
        response = client.post(
            "/api/v1/pipeline-runs",
            json={
                "book_slug": slug,
                "book_path": f"documents/{slug}.epub",
                "images_for_scenes": 1,
            },
        )
        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "prompt_art_style_text is required when prompt_art_style_mode is single_style"
        )
    finally:
        settings_repo.update(
            settings,
            data={
                "default_prompt_art_style_mode": original_mode,
                "default_prompt_art_style_text": original_text,
            },
            commit=True,
            refresh=True,
        )


def test_start_pipeline_run_requires_slug_or_document(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/pipeline-runs",
        json={"images_for_scenes": 1},
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "book_slug is required when document_id is not provided"
    )


def test_get_pipeline_run_returns_record(
    client: TestClient,
    db: Session,
) -> None:
    slug = f"test-book-{uuid4()}"
    run_repo = PipelineRunRepository(db)
    run = run_repo.create(
        data={
            "book_slug": slug,
            "status": "pending",
            "current_stage": "pending",
            "config_overrides": {"source": "test"},
        },
        commit=True,
    )

    response = client.get(f"/api/v1/pipeline-runs/{run.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(run.id)
    assert payload["book_slug"] == slug
    assert payload["usage_summary"] == {}

    db.delete(run)
    db.commit()


def test_get_pipeline_run_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/pipeline-runs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline run not found"


def test_build_execution_config_maps_request_fields() -> None:
    """Verify _build_execution_config translates all request fields correctly."""
    from app.schemas.pipeline_run import PipelineRunStartRequest

    request = PipelineRunStartRequest(
        document_id=uuid4(),
        book_slug="test-slug",
        book_path="documents/test.epub",
        prompt_art_style_mode="single_style",
        prompt_art_style_text="Watercolor",
        prompts_per_scene=3,
        ignore_ranking_recommendations=True,
        prompts_for_scenes=5,
        images_for_scenes=5,
        skip_extraction=True,
        skip_ranking=False,
        skip_prompts=False,
        quality="hd",
        style="vivid",
        aspect_ratio="16:9",
        dry_run=True,
    )

    config = pipeline_runs_routes._build_execution_config(request)

    assert isinstance(config.target, DocumentTarget)
    assert config.target.document_id == request.document_id
    assert config.target.book_slug == "test-slug"
    assert config.target.book_path == "documents/test.epub"

    assert config.stages.run_extraction is False
    assert config.stages.run_ranking is True
    assert config.stages.run_prompt_generation is True
    assert config.stages.run_image_generation is True

    assert config.prompt_options.prompts_per_scene == 3
    assert config.prompt_options.ignore_ranking_recommendations is True
    assert config.prompt_options.prompts_for_scenes == 5
    assert config.prompt_options.images_for_scenes == 5
    assert config.prompt_options.prompt_art_style_mode == "single_style"
    assert config.prompt_options.prompt_art_style_text == "Watercolor"

    assert config.image_options.quality == "hd"
    assert config.image_options.style == "vivid"
    assert config.image_options.aspect_ratio == "16:9"

    assert config.dry_run is True


def test_build_execution_config_skip_prompts_disables_images() -> None:
    """Verify skip_prompts implies no image generation."""
    from app.schemas.pipeline_run import PipelineRunStartRequest

    request = PipelineRunStartRequest(
        book_slug="test-slug",
        book_path="documents/test.epub",
        skip_prompts=True,
    )

    config = pipeline_runs_routes._build_execution_config(request)

    assert config.stages.run_prompt_generation is False
    assert config.stages.run_image_generation is False


def test_start_pipeline_run_no_batch_fields_in_request(
    client: TestClient,
) -> None:
    """Verify mode/poll_timeout/poll_interval are no longer accepted."""
    response = client.post(
        "/api/v1/pipeline-runs",
        json={
            "book_slug": "test",
            "book_path": "documents/test.epub",
            "mode": "batch",
            "poll_timeout": 100,
            "poll_interval": 5,
        },
    )

    # Pydantic v2 ignores extra fields by default; the fields should not
    # appear in the parsed model. Verify the request succeeds or fails
    # for a reason other than "mode" being present.
    # If mode were still in the schema, it would be accepted.
    # The important thing is the schema no longer exposes them.
    from app.schemas.pipeline_run import PipelineRunStartRequest

    assert not hasattr(
        PipelineRunStartRequest.model_fields, "mode"
    )
    assert "mode" not in PipelineRunStartRequest.model_fields
    assert "poll_timeout" not in PipelineRunStartRequest.model_fields
    assert "poll_interval" not in PipelineRunStartRequest.model_fields
