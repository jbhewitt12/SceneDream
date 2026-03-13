"""Tests for pipeline run API routes."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
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

    execute_mock = AsyncMock(name="_execute_pipeline_run")
    scheduled_calls: list[tuple[object, str]] = []

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:
        scheduled_calls.append((coro, task_name))
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
        _capture_spawn,
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
    call_kwargs = execute_mock.call_args.kwargs
    assert str(call_kwargs["run_id"]) == payload["id"]
    assert isinstance(call_kwargs["args"], argparse.Namespace)
    assert call_kwargs["args"].book_slug == slug

    assert len(scheduled_calls) == 1
    scheduled_coro, task_name = scheduled_calls[0]
    assert asyncio.iscoroutine(scheduled_coro)
    assert execute_mock.await_count == 0
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

    execute_mock = AsyncMock(name="_execute_pipeline_run")
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )

    def _failing_spawn(coro: object, *, task_name: str) -> None:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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
    execute_mock = AsyncMock(name="_execute_pipeline_run")

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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

    execute_mock = AsyncMock(name="_execute_pipeline_run")

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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

    execute_mock.assert_called_once()
    args = execute_mock.call_args.kwargs["args"]
    assert args.skip_extraction is True
    assert args.book_path is None


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

    execute_mock = AsyncMock(name="_execute_pipeline_run")

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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

    execute_mock.assert_called_once()
    args = execute_mock.call_args.kwargs["args"]
    assert args.skip_extraction is True
    assert args.skip_ranking is True


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

    execute_mock = AsyncMock(name="_execute_pipeline_run")

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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

        execute_mock.assert_called_once()
        args = execute_mock.call_args.kwargs["args"]
        assert args.prompt_art_style_mode == "single_style"
        assert args.prompt_art_style_text == "Pipeline Style Override"
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

    execute_mock = AsyncMock(name="_execute_pipeline_run")

    def _capture_spawn(coro: object, *, task_name: str) -> MagicMock:  # noqa: ARG001
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_execute_pipeline_run",
        execute_mock,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_spawn_background_task",
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


def test_execute_pipeline_run_records_usage_summary_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, object]] = []

    async def _fake_run_full_pipeline(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        stats = MagicMock()
        stats.errors = []
        stats.to_dict.return_value = {
            "scenes_extracted": 3,
            "scenes_refined": 2,
            "scenes_ranked": 3,
            "prompts_generated": 6,
            "images_generated": 2,
            "errors": [],
        }
        return stats

    def _capture_update(**kwargs: object) -> None:
        updates.append(kwargs)

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_run_full_pipeline",
        _fake_run_full_pipeline,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_update_status",
        _capture_update,
    )

    asyncio.run(
        pipeline_runs_routes._execute_pipeline_run(
            run_id=uuid4(),
            args=argparse.Namespace(
                book_slug="usage-summary-success",
                book_path="documents/usage-summary-success.epub",
                images_for_scenes=2,
                prompts_for_scenes=None,
                prompts_per_scene=None,
                prompt_art_style_mode="single_style",
                prompt_art_style_text="Watercolor",
                skip_extraction=False,
                skip_ranking=False,
                skip_prompts=False,
                quality="standard",
                style="vivid",
                aspect_ratio="1:1",
                mode="sync",
            ),
            config_overrides={"resolved_images_for_scenes": 2},
        )
    )

    assert updates[-1]["status_value"] == "completed"
    usage_summary = updates[-1]["usage_summary"]
    assert isinstance(usage_summary, dict)
    assert usage_summary["status"] == "completed"
    assert usage_summary["outputs"]["prompts_generated"] == 6
    assert usage_summary["outputs"]["images_generated"] == 2
    assert usage_summary["errors"]["code"] is None
    assert usage_summary["effective"]["config_overrides"] == {
        "resolved_images_for_scenes": 2
    }
    assert usage_summary["effective"]["prompt_generation"] == {
        "model_vendor": "google",
        "model_name": "gemini-3-pro-preview",
        "backup_model_vendor": "openai",
        "backup_model_name": "gpt-5-mini",
        "prompt_version": "image-prompts-v4",
        "target_provider": "gpt-image",
        "prompt_art_style_mode": "single_style",
        "prompt_art_style_text": "Watercolor",
    }
    assert "diagnostics" in usage_summary
    assert usage_summary["diagnostics"]["stage_durations_ms"] == {}
    assert len(usage_summary["diagnostics"]["stage_events"]) >= 2


def test_execute_pipeline_run_records_stage_durations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, object]] = []
    stage_running_calls: list[dict[str, object]] = []
    sync_calls: list[dict[str, object]] = []

    async def _fake_run_full_pipeline(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        stage_callback = _kwargs.get("stage_callback")
        assert callable(stage_callback)
        await stage_callback("extracting")
        await stage_callback("ranking")
        stats = MagicMock()
        stats.errors = []
        stats.to_dict.return_value = {
            "scenes_extracted": 1,
            "scenes_refined": 0,
            "scenes_ranked": 1,
            "prompts_generated": 0,
            "images_generated": 0,
            "errors": [],
        }
        return stats

    def _capture_update(**kwargs: object) -> None:
        updates.append(kwargs)

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_run_full_pipeline",
        _fake_run_full_pipeline,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_update_status",
        _capture_update,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_set_document_stage_running",
        lambda **kwargs: stage_running_calls.append(kwargs),
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_sync_document_stage_statuses",
        lambda **kwargs: sync_calls.append(kwargs),
    )

    asyncio.run(
        pipeline_runs_routes._execute_pipeline_run(
            run_id=uuid4(),
            args=argparse.Namespace(
                book_slug="diagnostics-success",
                book_path="documents/diagnostics-success.epub",
                images_for_scenes=1,
                prompts_for_scenes=None,
                prompts_per_scene=None,
                prompt_art_style_mode="random_mix",
                prompt_art_style_text=None,
                skip_extraction=False,
                skip_ranking=False,
                skip_prompts=False,
                quality="standard",
                style="vivid",
                aspect_ratio="1:1",
                mode="sync",
            ),
            config_overrides={"resolved_images_for_scenes": 1},
        )
    )

    usage_summary = updates[-1]["usage_summary"]
    assert isinstance(usage_summary, dict)
    diagnostics = usage_summary["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["observed_stage"] == "ranking"
    assert "extracting" in diagnostics["stage_durations_ms"]
    assert "ranking" in diagnostics["stage_durations_ms"]
    assert diagnostics["stage_durations_ms"]["extracting"] >= 0
    assert diagnostics["stage_durations_ms"]["ranking"] >= 0
    event_types = [event["type"] for event in diagnostics["stage_events"]]
    assert "stage_started" in event_types
    assert "stage_completed" in event_types
    assert "run_completed" in event_types
    assert [call["pipeline_stage"] for call in stage_running_calls] == [
        "extracting",
        "ranking",
    ]
    assert len(sync_calls) == 1
    assert sync_calls[0]["preserve_failed_pipeline_stage"] is None


def test_execute_pipeline_run_records_usage_summary_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, object]] = []
    failed_calls: list[dict[str, object]] = []
    sync_calls: list[dict[str, object]] = []

    async def _fake_run_full_pipeline(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    def _capture_update(**kwargs: object) -> None:
        updates.append(kwargs)

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_run_full_pipeline",
        _fake_run_full_pipeline,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_update_status",
        _capture_update,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_set_document_stage_failed",
        lambda **kwargs: failed_calls.append(kwargs),
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_sync_document_stage_statuses",
        lambda **kwargs: sync_calls.append(kwargs),
    )

    asyncio.run(
        pipeline_runs_routes._execute_pipeline_run(
            run_id=uuid4(),
            args=argparse.Namespace(
                book_slug="usage-summary-failure",
                book_path="documents/usage-summary-failure.epub",
                images_for_scenes=1,
                prompts_for_scenes=None,
                prompts_per_scene=None,
                prompt_art_style_mode="random_mix",
                prompt_art_style_text=None,
                skip_extraction=False,
                skip_ranking=False,
                skip_prompts=False,
                quality="standard",
                style="vivid",
                aspect_ratio="1:1",
                mode="sync",
            ),
            config_overrides={"resolved_images_for_scenes": 1},
        )
    )

    assert updates[-1]["status_value"] == "failed"
    usage_summary = updates[-1]["usage_summary"]
    assert isinstance(usage_summary, dict)
    assert usage_summary["status"] == "failed"
    assert usage_summary["errors"]["count"] >= 1
    assert usage_summary["errors"]["code"] == "pipeline_exception"
    assert usage_summary["outputs"]["images_generated"] == 0
    diagnostics = usage_summary["diagnostics"]
    assert diagnostics["error"]["code"] == "pipeline_exception"
    assert diagnostics["error"]["stage"] == "pending"
    assert diagnostics["error"]["message"] == "boom"
    assert len(failed_calls) == 1
    assert failed_calls[0]["pipeline_stage"] is None
    assert failed_calls[0]["error_message"] == "boom"
    assert len(sync_calls) == 1
    assert sync_calls[0]["preserve_failed_pipeline_stage"] is None


def test_execute_pipeline_run_classifies_missing_source_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, object]] = []

    async def _fake_run_full_pipeline(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("--book-path is required for scene extraction")

    def _capture_update(**kwargs: object) -> None:
        updates.append(kwargs)

    monkeypatch.setattr(
        pipeline_runs_routes,
        "_run_full_pipeline",
        _fake_run_full_pipeline,
    )
    monkeypatch.setattr(
        pipeline_runs_routes,
        "_update_status",
        _capture_update,
    )

    asyncio.run(
        pipeline_runs_routes._execute_pipeline_run(
            run_id=uuid4(),
            args=argparse.Namespace(
                book_slug="diagnostics-missing-source",
                book_path=None,
                images_for_scenes=1,
                prompts_for_scenes=None,
                prompts_per_scene=None,
                prompt_art_style_mode="random_mix",
                prompt_art_style_text=None,
                skip_extraction=False,
                skip_ranking=False,
                skip_prompts=False,
                quality="standard",
                style=None,
                aspect_ratio=None,
                mode="sync",
            ),
            config_overrides={"resolved_images_for_scenes": 1},
        )
    )

    usage_summary = updates[-1]["usage_summary"]
    assert isinstance(usage_summary, dict)
    assert usage_summary["errors"]["code"] == "missing_source"
    diagnostics = usage_summary["diagnostics"]
    assert diagnostics["error"]["code"] == "missing_source"
