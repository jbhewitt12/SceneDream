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
from app.repositories import DocumentRepository, PipelineRunRepository
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

    db.delete(run)
    db.commit()


def test_get_pipeline_run_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/pipeline-runs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline run not found"
