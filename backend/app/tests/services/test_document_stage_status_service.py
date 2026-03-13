from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session

from app.repositories import DocumentRepository, SceneRankingRepository
from app.services.pipeline import DocumentStageStatusService


def test_sync_document_sets_pending_when_no_scenes(db: Session) -> None:
    document_repo = DocumentRepository(db)
    slug = f"test-book-stage-empty-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    service = DocumentStageStatusService(db)
    service.sync_document(document=document)
    db.commit()
    db.refresh(document)

    assert document.extraction_status == "pending"
    assert document.ranking_status == "pending"
    assert document.extraction_completed_at is None
    assert document.ranking_completed_at is None

    db.delete(document)
    db.commit()


def test_sync_document_marks_extraction_completed_and_ranking_stale(
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    slug = f"test-book-stage-stale-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    scene_one = scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )
    scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=2,
        chunk_index=1,
    )

    ranking_repo.create(
        data={
            "scene_extraction_id": scene_one.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "scores": {"visual_style_potential": 8.0},
            "overall_priority": 8.0,
            "weight_config": {"visual_style_potential": 1.0},
            "weight_config_hash": "stage-status-hash",
            "raw_response": {},
        },
        commit=True,
    )

    service = DocumentStageStatusService(db)
    service.sync_document(document=document)
    db.commit()
    db.refresh(document)

    assert document.extraction_status == "completed"
    assert document.ranking_status == "stale"
    assert document.extraction_completed_at is not None
    assert document.ranking_completed_at is None

    db.delete(document)
    db.commit()


def test_sync_document_marks_ranking_completed_when_coverage_is_full(
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    slug = f"test-book-stage-complete-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    scene_one = scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )
    scene_two = scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=2,
        chunk_index=1,
    )

    for scene in (scene_one, scene_two):
        ranking_repo.create(
            data={
                "scene_extraction_id": scene.id,
                "model_vendor": "test-vendor",
                "model_name": "test-model",
                "prompt_version": "test-v1",
                "scores": {"visual_style_potential": 8.0},
                "overall_priority": 8.0,
                "weight_config": {"visual_style_potential": 1.0},
                "weight_config_hash": f"stage-status-hash-{scene.id}",
                "raw_response": {},
            },
            commit=True,
        )

    service = DocumentStageStatusService(db)
    service.sync_document(document=document)
    db.commit()
    db.refresh(document)

    assert document.extraction_status == "completed"
    assert document.ranking_status == "completed"
    assert document.ranking_completed_at is not None

    db.delete(document)
    db.commit()


def test_sync_document_treats_discarded_scenes_as_not_rank_required(
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    slug = f"test-book-stage-discarded-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    rankable_scene = scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
        refinement_decision="keep",
    )
    scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=2,
        chunk_index=1,
        refinement_decision="discard",
    )

    ranking_repo.create(
        data={
            "scene_extraction_id": rankable_scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "scores": {"visual_style_potential": 8.0},
            "overall_priority": 8.0,
            "weight_config": {"visual_style_potential": 1.0},
            "weight_config_hash": f"stage-status-hash-{rankable_scene.id}",
            "raw_response": {},
        },
        commit=True,
    )

    service = DocumentStageStatusService(db)
    service.sync_document(document=document)
    db.commit()
    db.refresh(document)

    assert document.extraction_status == "completed"
    assert document.ranking_status == "completed"
    assert document.ranking_completed_at is not None

    db.delete(document)
    db.commit()


def test_mark_stage_running_and_failed_updates_document_fields(db: Session) -> None:
    document_repo = DocumentRepository(db)
    slug = f"test-book-stage-running-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    service = DocumentStageStatusService(db)
    service.mark_stage_running(document=document, stage="extraction")
    service.mark_stage_failed(
        document=document,
        stage="ranking",
        error_message="Ranking exploded",
    )
    db.commit()
    db.refresh(document)

    assert document.extraction_status == "running"
    assert document.extraction_error is None
    assert document.ranking_status == "failed"
    assert document.ranking_error == "Ranking exploded"

    db.delete(document)
    db.commit()


def test_sync_all_documents_updates_multiple_documents(
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    extraction_slug = f"test-book-sync-all-extraction-{uuid4()}"
    extraction_only_document = document_repo.create(
        data={
            "slug": extraction_slug,
            "source_path": f"documents/{extraction_slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "pending",
            "ranking_status": "pending",
            "source_metadata": {},
        },
        commit=True,
    )
    scene_factory(
        book_slug=extraction_slug,
        source_book_path=extraction_only_document.source_path,
        document_id=extraction_only_document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )

    ranking_slug = f"test-book-sync-all-ranking-{uuid4()}"
    ranked_document = document_repo.create(
        data={
            "slug": ranking_slug,
            "source_path": f"documents/{ranking_slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "pending",
            "ranking_status": "pending",
            "source_metadata": {},
        },
        commit=True,
    )
    ranked_scene = scene_factory(
        book_slug=ranking_slug,
        source_book_path=ranked_document.source_path,
        document_id=ranked_document.id,
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
            "weight_config_hash": f"sync-all-hash-{ranked_scene.id}",
            "raw_response": {},
        },
        commit=True,
    )

    total_documents = len(document_repo.list(limit=None))

    service = DocumentStageStatusService(db)
    synced = service.sync_all_documents()
    db.refresh(extraction_only_document)
    db.refresh(ranked_document)

    assert synced == total_documents
    assert extraction_only_document.extraction_status == "completed"
    assert extraction_only_document.ranking_status == "pending"
    assert ranked_document.extraction_status == "completed"
    assert ranked_document.ranking_status == "completed"

    db.delete(extraction_only_document)
    db.delete(ranked_document)
    db.commit()


def test_sync_all_documents_preserves_existing_completed_timestamps(
    db: Session,
    scene_factory,
) -> None:
    document_repo = DocumentRepository(db)
    ranking_repo = SceneRankingRepository(db)

    existing_completed_at = datetime.now(timezone.utc)
    slug = f"test-book-sync-all-preserve-{uuid4()}"
    document = document_repo.create(
        data={
            "slug": slug,
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "ingested",
            "extraction_status": "completed",
            "extraction_completed_at": existing_completed_at,
            "ranking_status": "completed",
            "ranking_completed_at": existing_completed_at,
            "source_metadata": {},
        },
        commit=True,
    )
    scene = scene_factory(
        book_slug=slug,
        source_book_path=document.source_path,
        document_id=document.id,
        chapter_number=1,
        scene_number=1,
        chunk_index=0,
    )
    ranking_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "scores": {"visual_style_potential": 8.0},
            "overall_priority": 8.0,
            "weight_config": {"visual_style_potential": 1.0},
            "weight_config_hash": f"sync-all-preserve-hash-{scene.id}",
            "raw_response": {},
        },
        commit=True,
    )

    total_documents = len(document_repo.list(limit=None))

    service = DocumentStageStatusService(db)
    synced = service.sync_all_documents()
    db.refresh(document)

    assert synced == total_documents
    assert document.extraction_status == "completed"
    assert document.ranking_status == "completed"
    assert document.extraction_completed_at == existing_completed_at
    assert document.ranking_completed_at == existing_completed_at

    db.delete(document)
    db.commit()
