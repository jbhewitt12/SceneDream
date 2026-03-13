from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.repositories import (
    DocumentRepository,
    PipelineRunRepository,
    SceneRankingRepository,
)

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
            "extraction_status": "completed",
            "ranking_status": "failed",
            "ranking_error": "Ranking failed for route test",
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
            (
                entry
                for entry in payload["data"]
                if entry["document_id"] == str(document.id)
            ),
            None,
        )

        assert target is not None
        assert target["source_path"] == relative_path
        assert target["file_exists"] is True
        assert target["stages"]["extraction"]["status"] == "completed"
        assert target["stages"]["ranking"]["status"] == "failed"
        assert target["stages"]["ranking"]["error"] == "Ranking failed for route test"
        assert target["last_run"] is not None
        assert target["last_run"]["id"] == str(run.id)
        assert target["last_run"]["error_message"] == "Route-level failure"
        assert target["last_run"]["usage_summary"] == {}
    finally:
        if source_file.exists():
            source_file.unlink()


def test_sync_document_stages_updates_statuses(
    client: TestClient,
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    extraction_slug = f"test-book-dashboard-sync-extraction-{uuid4()}"
    extraction_document = document_repo.create(
        data={
            "slug": extraction_slug,
            "display_name": "Sync Extraction Document",
            "source_path": f"documents/{extraction_slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "pending",
            "ranking_status": "pending",
            "source_metadata": {"route_test": True},
        },
        commit=True,
    )
    scene_factory(
        book_slug=extraction_slug,
        source_book_path=extraction_document.source_path,
        document_id=extraction_document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )

    ranking_slug = f"test-book-dashboard-sync-ranking-{uuid4()}"
    ranking_document = document_repo.create(
        data={
            "slug": ranking_slug,
            "display_name": "Sync Ranking Document",
            "source_path": f"documents/{ranking_slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "pending",
            "ranking_status": "pending",
            "source_metadata": {"route_test": True},
        },
        commit=True,
    )
    ranked_scene = scene_factory(
        book_slug=ranking_slug,
        source_book_path=ranking_document.source_path,
        document_id=ranking_document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )
    ranking_repo.create(
        data={
            "scene_extraction_id": ranked_scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "scores": {"visual_style_potential": 8.0},
            "overall_priority": 8.0,
            "weight_config": {"visual_style_potential": 1.0},
            "weight_config_hash": f"route-sync-hash-{ranked_scene.id}",
            "raw_response": {},
        },
        commit=True,
    )

    total_documents = len(document_repo.list(limit=None))

    response = client.post("/api/v1/documents/sync-stages")

    assert response.status_code == 200
    assert response.json() == {"synced": total_documents}

    db.refresh(extraction_document)
    db.refresh(ranking_document)
    assert extraction_document.extraction_status == "completed"
    assert extraction_document.ranking_status == "pending"
    assert ranking_document.extraction_status == "completed"
    assert ranking_document.ranking_status == "completed"
