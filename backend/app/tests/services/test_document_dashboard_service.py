from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from app.repositories import (
    DocumentRepository,
    GeneratedImageRepository,
    PipelineRunRepository,
    SceneRankingRepository,
)
from app.services.document_dashboard_service import (
    DocumentDashboardService,
    _default_project_root_from_path,
)


def test_document_dashboard_service_reports_stage_counts_for_document(
    db: Session,
    scene_factory,
    prompt_factory,
    tmp_path: Path,
) -> None:
    source_path = "documents/Test Author/Test Novel.epub"
    source_file = tmp_path / source_path
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("Chapter 1\n\nA test paragraph.", encoding="utf-8")

    slug = f"test-book-dashboard-{uuid4()}"
    document_repo = DocumentRepository(db)
    document = document_repo.create(
        data={
            "slug": slug,
            "display_name": "Dashboard Test Novel",
            "source_path": source_path,
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "completed",
            "extraction_completed_at": datetime.now(timezone.utc),
            "ranking_status": "completed",
            "ranking_completed_at": datetime.now(timezone.utc),
            "source_metadata": {},
        },
        commit=True,
    )

    scene = scene_factory(
        book_slug=slug,
        source_book_path=source_path,
        document_id=document.id,
    )
    prompt = prompt_factory(scene)

    ranking_repo = SceneRankingRepository(db)
    ranking_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "scores": {"visual_style_potential": 8.0},
            "overall_priority": 8.0,
            "weight_config": {"visual_style_potential": 1.0},
            "weight_config_hash": "dashboard-hash",
            "raw_response": {},
        },
        commit=True,
    )

    run_repo = PipelineRunRepository(db)
    run = run_repo.create(
        data={
            "document_id": document.id,
            "book_slug": slug,
            "status": "completed",
            "current_stage": "completed",
            "config_overrides": {"test": True},
        },
        commit=True,
    )

    image_repo = GeneratedImageRepository(db)
    image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "pipeline_run_id": run.id,
            "book_slug": slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai",
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "response_format": "b64_json",
            "storage_path": "img/generated/test/dashboard-test.png",
            "file_name": "dashboard-test.png",
        },
        commit=True,
    )

    service = DocumentDashboardService(db, project_root=tmp_path)
    entries = service.list_entries()
    match = next((entry for entry in entries if entry.document_id == document.id), None)

    assert match is not None
    assert match.slug == slug
    assert match.file_exists is True
    assert match.counts.extracted == 1
    assert match.counts.ranked == 1
    assert match.counts.prompts_generated == 1
    assert match.counts.images_generated == 1
    assert match.stages.extraction.status == "completed"
    assert match.stages.extraction.error is None
    assert match.stages.ranking.status == "completed"
    assert match.stages.ranking.error is None
    assert match.stages.prompts_generated.status == "completed"
    assert match.stages.images_generated.status == "completed"
    assert match.last_run is not None
    assert match.last_run.status == "completed"
    assert match.last_run.usage_summary == {}


def test_document_dashboard_service_uses_legacy_slug_fallback(
    db: Session,
    scene_factory,
    tmp_path: Path,
) -> None:
    source_path = "documents/Test Shelf/Legacy Book.txt"
    source_file = tmp_path / source_path
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("Plain text chapter content.", encoding="utf-8")

    legacy_slug = "legacy-book"
    scene_factory(
        book_slug=legacy_slug,
        source_book_path=source_path,
        document_id=None,
    )

    run_repo = PipelineRunRepository(db)
    run = run_repo.create(
        data={
            "document_id": None,
            "book_slug": legacy_slug,
            "status": "failed",
            "current_stage": "failed",
            "error_message": "Legacy pipeline error",
            "config_overrides": {"legacy": True},
        },
        commit=True,
    )

    service = DocumentDashboardService(db, project_root=tmp_path)
    entries = service.list_entries()
    match = next((entry for entry in entries if entry.source_path == source_path), None)

    assert match is not None
    assert match.document_id is None
    assert match.slug == legacy_slug
    assert match.counts.extracted == 1
    assert match.counts.ranked == 0
    assert match.counts.prompts_generated == 0
    assert match.counts.images_generated == 0
    assert match.stages.extraction.status == "completed"
    assert match.stages.ranking.status == "pending"
    assert match.last_run is not None
    assert match.last_run.id == run.id
    assert match.last_run.error_message == "Legacy pipeline error"
    assert match.last_run.usage_summary == {}


def test_default_project_root_detects_local_layout() -> None:
    source_file = Path(
        "/Users/test/SceneDream/backend/app/services/document_dashboard_service.py"
    )
    assert _default_project_root_from_path(source_file) == Path(
        "/Users/test/SceneDream"
    )


def test_default_project_root_detects_container_layout() -> None:
    source_file = Path("/app/app/services/document_dashboard_service.py")
    assert _default_project_root_from_path(source_file) == Path("/app")
