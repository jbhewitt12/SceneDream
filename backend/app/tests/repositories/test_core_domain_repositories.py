from uuid import uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.repositories import (
    DocumentRepository,
    GeneratedAssetRepository,
    GeneratedImageRepository,
    PipelineRunRepository,
)


def test_document_repository_upsert_and_filters(db: Session) -> None:
    repository = DocumentRepository(db)
    slug = f"test-book-{uuid4()}"
    document = repository.create(
        data={
            "slug": slug,
            "display_name": "Test Document",
            "source_path": f"documents/{slug}.epub",
            "source_type": "epub",
            "ingestion_state": "pending",
            "source_metadata": {"seeded": True},
        },
        commit=True,
    )

    updated = repository.upsert_by_slug(
        slug=slug,
        values={
            "display_name": "Updated Name",
            "ingestion_state": "ingested",
        },
        commit=True,
    )
    assert updated.id == document.id
    assert updated.display_name == "Updated Name"
    assert updated.ingestion_state == "ingested"

    filtered = repository.list(source_type="epub", ingestion_state="ingested")
    assert any(row.id == document.id for row in filtered)

    db.delete(updated)
    db.commit()


def test_pipeline_run_repository_status_transitions(db: Session) -> None:
    document_repo = DocumentRepository(db)
    run_repo = PipelineRunRepository(db)
    slug = f"test-book-{uuid4()}"
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

    run = run_repo.create(
        data={
            "document_id": document.id,
            "book_slug": slug,
            "status": "pending",
            "config_overrides": {"scenes_count": 5},
        },
        commit=True,
    )
    assert run.started_at is None

    running = run_repo.update_status(
        run.id,
        status="running",
        current_stage="extracting",
        commit=True,
    )
    assert running is not None
    assert running.current_stage == "extracting"
    assert running.started_at is not None
    assert running.completed_at is None

    completed = run_repo.update_status(
        run.id,
        status="completed",
        current_stage="completed",
        completed=True,
        commit=True,
    )
    assert completed is not None
    assert completed.completed_at is not None

    runs_for_document = run_repo.list_for_document(document_id=document.id)
    assert [row.id for row in runs_for_document] == [run.id]

    db.delete(run)
    db.delete(document)
    db.commit()


def test_document_backfill_sql_links_existing_scenes(
    db: Session, scene_factory
) -> None:
    repository = DocumentRepository(db)
    slug = f"test-book-{uuid4()}"
    scene = scene_factory(book_slug=slug)
    document = repository.create(
        data={
            "slug": slug,
            "source_path": scene.source_book_path,
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {"backfilled": True},
        },
        commit=True,
    )
    assert scene.document_id is None

    db.execute(
        text(
            """
            UPDATE scene_extractions AS se
            SET document_id = d.id
            FROM documents AS d
            WHERE se.book_slug = d.slug
            """
        )
    )
    db.commit()
    db.refresh(scene)

    assert scene.document_id == document.id

    db.delete(document)
    db.commit()


def test_content_path_backfill_sql_normalizes_legacy_books_paths(
    db: Session, scene_factory
) -> None:
    repository = DocumentRepository(db)
    slug = f"test-book-{uuid4()}"
    legacy_path = "/tmp/library/books/Author Name/Novel.epub"
    scene = scene_factory(book_slug=slug, source_book_path=legacy_path, props={})
    document = repository.create(
        data={
            "slug": slug,
            "source_path": legacy_path,
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {},
        },
        commit=True,
    )

    db.execute(
        text(
            """
            WITH normalized AS (
                SELECT
                    id,
                    source_path AS old_path,
                    CASE
                        WHEN source_path IS NULL OR source_path = '' THEN source_path
                        WHEN regexp_replace(source_path, '^\\./+', '') LIKE 'documents/%' THEN regexp_replace(source_path, '^\\./+', '')
                        WHEN regexp_replace(source_path, '^\\./+', '') LIKE 'books/%' THEN 'documents/' || substring(regexp_replace(source_path, '^\\./+', '') FROM 7)
                        WHEN regexp_replace(source_path, '^\\./+', '') ~ '.*/documents/.*' THEN regexp_replace(regexp_replace(source_path, '^\\./+', ''), '^.*/documents/', 'documents/')
                        WHEN regexp_replace(source_path, '^\\./+', '') ~ '.*/books/.*' THEN 'documents/' || substring(regexp_replace(regexp_replace(source_path, '^\\./+', ''), '^.*/books/', 'books/') FROM 7)
                        ELSE regexp_replace(source_path, '^\\./+', '')
                    END AS new_path
                FROM documents
            )
            UPDATE documents AS d
            SET
                source_path = n.new_path,
                source_metadata = CASE
                    WHEN n.old_path <> n.new_path THEN jsonb_set(
                        COALESCE(d.source_metadata, '{}'::jsonb),
                        '{legacy_source_path}',
                        to_jsonb(n.old_path),
                        true
                    )
                    ELSE d.source_metadata
                END
            FROM normalized AS n
            WHERE d.id = n.id
              AND n.new_path IS NOT NULL
              AND n.old_path <> n.new_path
            """
        )
    )
    db.execute(
        text(
            """
            WITH normalized AS (
                SELECT
                    id,
                    source_book_path AS old_path,
                    CASE
                        WHEN source_book_path IS NULL OR source_book_path = '' THEN source_book_path
                        WHEN regexp_replace(source_book_path, '^\\./+', '') LIKE 'documents/%' THEN regexp_replace(source_book_path, '^\\./+', '')
                        WHEN regexp_replace(source_book_path, '^\\./+', '') LIKE 'books/%' THEN 'documents/' || substring(regexp_replace(source_book_path, '^\\./+', '') FROM 7)
                        WHEN regexp_replace(source_book_path, '^\\./+', '') ~ '.*/documents/.*' THEN regexp_replace(regexp_replace(source_book_path, '^\\./+', ''), '^.*/documents/', 'documents/')
                        WHEN regexp_replace(source_book_path, '^\\./+', '') ~ '.*/books/.*' THEN 'documents/' || substring(regexp_replace(regexp_replace(source_book_path, '^\\./+', ''), '^.*/books/', 'books/') FROM 7)
                        ELSE regexp_replace(source_book_path, '^\\./+', '')
                    END AS new_path
                FROM scene_extractions
            )
            UPDATE scene_extractions AS se
            SET
                source_book_path = n.new_path,
                props = CASE
                    WHEN n.old_path <> n.new_path THEN jsonb_set(
                        COALESCE(se.props, '{}'::jsonb),
                        '{legacy_source_book_path}',
                        to_jsonb(n.old_path),
                        true
                    )
                    ELSE se.props
                END
            FROM normalized AS n
            WHERE se.id = n.id
              AND n.new_path IS NOT NULL
              AND n.old_path <> n.new_path
            """
        )
    )
    db.commit()
    db.refresh(scene)
    db.refresh(document)

    assert document.source_path == "documents/Author Name/Novel.epub"
    assert document.source_metadata["legacy_source_path"] == legacy_path
    assert scene.source_book_path == "documents/Author Name/Novel.epub"
    assert scene.props["legacy_source_book_path"] == legacy_path

    db.delete(document)
    db.commit()


def test_generated_asset_repository_links_existing_records(
    db: Session, scene_factory, prompt_factory
) -> None:
    scene = scene_factory(book_slug=f"test-book-{uuid4()}")
    prompt = prompt_factory(scene)
    document_repo = DocumentRepository(db)
    run_repo = PipelineRunRepository(db)
    asset_repo = GeneratedAssetRepository(db)
    image_repo = GeneratedImageRepository(db)

    document = document_repo.create(
        data={
            "slug": scene.book_slug,
            "source_path": scene.source_book_path,
            "source_type": "epub",
            "ingestion_state": "ingested",
            "source_metadata": {"from_fixture": True},
        },
        commit=True,
    )
    run = run_repo.create(
        data={
            "document_id": document.id,
            "book_slug": scene.book_slug,
            "status": "running",
            "current_stage": "generating_prompts",
            "config_overrides": {"style": "cinematic"},
        },
        commit=True,
    )

    scene.document_id = document.id
    prompt.pipeline_run_id = run.id
    db.add(scene)
    db.add(prompt)
    db.commit()
    db.refresh(scene)
    db.refresh(prompt)

    prompt_asset = asset_repo.create(
        data={
            "document_id": document.id,
            "pipeline_run_id": run.id,
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "asset_type": "prompt",
            "status": "created",
            "provider": "google",
            "model": prompt.model_name,
            "asset_metadata": {"variant_index": prompt.variant_index},
        },
        commit=True,
    )
    image_asset = asset_repo.bulk_create(
        [
            {
                "document_id": document.id,
                "pipeline_run_id": run.id,
                "scene_extraction_id": scene.id,
                "image_prompt_id": prompt.id,
                "asset_type": "image",
                "status": "created",
                "provider": "openai",
                "model": "dall-e-3",
                "storage_path": f"img/generated/{scene.book_slug}/chapter-{scene.chapter_number}",
                "file_name": "asset-0.png",
                "mime_type": "image/png",
                "asset_metadata": {"size": "1024x1024"},
            }
        ],
        commit=True,
    )[0]

    image = image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "pipeline_run_id": run.id,
            "generated_asset_id": image_asset.id,
            "book_slug": scene.book_slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai",
            "model": "dall-e-3",
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "response_format": "b64_json",
            "storage_path": f"img/generated/{scene.book_slug}/chapter-{scene.chapter_number}",
            "file_name": "image-0.png",
        },
        commit=True,
    )

    for_document = asset_repo.list_for_document(document.id)
    assert {asset.id for asset in for_document} == {prompt_asset.id, image_asset.id}

    image_assets = asset_repo.list_for_pipeline_run(run.id, asset_type="image")
    assert [asset.id for asset in image_assets] == [image_asset.id]

    persisted_image = image_repo.get(image.id)
    assert persisted_image is not None
    assert persisted_image.pipeline_run_id == run.id
    assert persisted_image.generated_asset_id == image_asset.id

    db.delete(image)
    db.delete(prompt_asset)
    db.delete(image_asset)
    db.delete(run)
    db.delete(document)
    db.commit()


def test_pipeline_run_repository_stage_progress(db: Session) -> None:
    document_repo = DocumentRepository(db)
    run_repo = PipelineRunRepository(db)
    slug = f"test-book-progress-{uuid4()}"
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

    run = run_repo.create(
        data={
            "document_id": document.id,
            "book_slug": slug,
            "status": "pending",
            "config_overrides": {},
        },
        commit=True,
    )
    assert run.stage_progress is None

    progress = {
        "extracting": {
            "status": "running",
            "items": 3,
            "total": 10,
            "unit": "chapters",
        },
        "ranking": {"status": "pending"},
        "generating_prompts": {"status": "pending"},
        "generating_images": {"status": "pending"},
    }
    updated = run_repo.update_status(
        run.id,
        status="extracting",
        current_stage="extracting",
        stage_progress=progress,
        commit=True,
    )
    assert updated is not None
    assert updated.stage_progress is not None
    assert updated.stage_progress["extracting"]["status"] == "running"
    assert updated.stage_progress["extracting"]["items"] == 3
    assert updated.stage_progress["ranking"]["status"] == "pending"

    # Updating again merges properly
    completed_progress = {
        "extracting": {"status": "completed", "items": 42, "unit": "scenes"},
        "ranking": {"status": "pending"},
        "generating_prompts": {"status": "pending"},
        "generating_images": {"status": "pending"},
    }
    final = run_repo.update_status(
        run.id,
        status="completed",
        current_stage="completed",
        stage_progress=completed_progress,
        completed=True,
        commit=True,
    )
    assert final is not None
    assert final.stage_progress is not None
    assert final.stage_progress["extracting"]["status"] == "completed"
    assert final.stage_progress["extracting"]["items"] == 42

    db.delete(run)
    db.delete(document)
    db.commit()
