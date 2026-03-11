from __future__ import annotations

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
