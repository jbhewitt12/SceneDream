from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.repositories import DocumentRepository, PipelineRunRepository

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def test_get_documents_dashboard_returns_pipeline_status(
    client: TestClient,
    db: Session,
    scene_factory,
) -> None:
    unique_slug = f"test-book-dashboard-route-{uuid4()}"
    relative_path = f"documents/dashboard-tests/{unique_slug}.txt"
    source_file = PROJECT_ROOT / relative_path
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("Route dashboard test content.", encoding="utf-8")

    document_repo = DocumentRepository(db)
    document = document_repo.create(
        data={
            "slug": unique_slug,
            "display_name": "Dashboard Route Document",
            "source_path": relative_path,
            "source_type": "txt",
            "ingestion_state": "ingested",
            "source_metadata": {"route_test": True},
        },
        commit=True,
    )

    scene_factory(
        book_slug=unique_slug,
        source_book_path=relative_path,
        document_id=document.id,
    )

    run_repo = PipelineRunRepository(db)
    run = run_repo.create(
        data={
            "document_id": document.id,
            "book_slug": unique_slug,
            "status": "failed",
            "current_stage": "failed",
            "error_message": "Route-level failure",
            "config_overrides": {"route_test": True},
        },
        commit=True,
    )

    try:
        response = client.get("/api/v1/documents/dashboard")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] >= 1

        target = next(
            (entry for entry in payload["data"] if entry["document_id"] == str(document.id)),
            None,
        )

        assert target is not None
        assert target["source_path"] == relative_path
        assert target["file_exists"] is True
        assert target["stages"]["extracted"] is True
        assert target["last_run"] is not None
        assert target["last_run"]["id"] == str(run.id)
        assert target["last_run"]["error_message"] == "Route-level failure"
        assert target["last_run"]["usage_summary"] == {}
    finally:
        if source_file.exists():
            source_file.unlink()
