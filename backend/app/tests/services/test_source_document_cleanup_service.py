from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from app.services.source_document_cleanup_service import SourceDocumentCleanupService
from models.document import Document
from models.generated_asset import GeneratedAsset
from models.generated_image import GeneratedImage
from models.image_generation_batch import ImageGenerationBatch
from models.image_prompt import ImagePrompt
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking
from models.social_media_post import SocialMediaPost


def _write_file(project_root: Path, storage_path: str, file_name: str) -> Path:
    file_path = project_root / storage_path / file_name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"fixture")
    return file_path


def _build_scene(
    *,
    source_book_path: str,
    book_slug: str,
    chapter_number: int,
    scene_number: int,
    document_id: object | None = None,
) -> SceneExtraction:
    return SceneExtraction(
        document_id=document_id,
        source_book_path=source_book_path,
        book_slug=book_slug,
        chapter_number=chapter_number,
        chapter_title=f"Chapter {chapter_number}",
        scene_number=scene_number,
        location_marker=f"chapter-{chapter_number}-scene-{scene_number}",
        raw=f"Scene {scene_number} from chapter {chapter_number}.",
        refined=f"Refined scene {scene_number}.",
        extraction_model="test-model",
        refinement_model="test-model",
    )


def _build_ranking(
    *,
    scene_id: object,
    pipeline_run_id: object | None,
    weight_hash: str,
) -> SceneRanking:
    return SceneRanking(
        scene_extraction_id=scene_id,
        pipeline_run_id=pipeline_run_id,
        model_vendor="test-vendor",
        model_name="test-ranking-model",
        prompt_version="ranking-v1",
        scores={"visual": 1.0},
        overall_priority=1.0,
        weight_config={"visual": 1.0},
        weight_config_hash=weight_hash,
        raw_response={},
    )


def _build_prompt(
    *,
    scene_id: object,
    pipeline_run_id: object | None,
    variant_index: int,
) -> ImagePrompt:
    return ImagePrompt(
        scene_extraction_id=scene_id,
        pipeline_run_id=pipeline_run_id,
        model_vendor="test-vendor",
        model_name="test-prompt-model",
        prompt_version="prompt-v1",
        variant_index=variant_index,
        prompt_text="A test prompt.",
        attributes={},
        context_window={},
        raw_response={},
    )


def test_cleanup_source_document_removes_only_target_story_artifacts(
    db: Session,
    tmp_path: Path,
) -> None:
    target_source_path = f"example_docs/target-story-{uuid4()}.md"
    other_source_path = f"example_docs/other-story-{uuid4()}.md"
    shared_book_slug = f"test-book-shared-slug-{uuid4()}"

    target_document = Document(
        slug=f"test-book-target-doc-{uuid4()}",
        display_name="The Cask of Amontillado",
        source_path=target_source_path,
        source_type="md",
    )
    other_document = Document(
        slug=f"test-book-other-doc-{uuid4()}",
        display_name="Another Story",
        source_path=other_source_path,
        source_type="md",
    )
    db.add(target_document)
    db.add(other_document)
    db.flush()

    target_scene_one = _build_scene(
        source_book_path=target_source_path,
        book_slug=shared_book_slug,
        chapter_number=1,
        scene_number=1,
        document_id=target_document.id,
    )
    target_scene_two = _build_scene(
        source_book_path=target_source_path,
        book_slug=shared_book_slug,
        chapter_number=1,
        scene_number=2,
    )
    other_scene_same_slug = _build_scene(
        source_book_path=other_source_path,
        book_slug=shared_book_slug,
        chapter_number=2,
        scene_number=1,
        document_id=other_document.id,
    )
    db.add(target_scene_one)
    db.add(target_scene_two)
    db.add(other_scene_same_slug)
    db.flush()

    target_document_run = PipelineRun(
        document_id=target_document.id,
        book_slug=shared_book_slug,
        status="completed",
        current_stage="completed",
        config_overrides={"resolved_book_path": target_source_path},
    )
    target_path_only_run = PipelineRun(
        book_slug=shared_book_slug,
        status="failed",
        current_stage="generating_images",
        config_overrides={"resolved_book_path": target_source_path},
    )
    target_scene_targeted_run = PipelineRun(
        book_slug=shared_book_slug,
        status="failed",
        current_stage="generating_images",
        config_overrides={"scene_ids": [str(target_scene_two.id)]},
    )
    unrelated_scene_targeted_run = PipelineRun(
        book_slug=shared_book_slug,
        status="pending",
        current_stage="pending",
        config_overrides={"scene_ids": [str(other_scene_same_slug.id)]},
    )
    other_document_run = PipelineRun(
        document_id=other_document.id,
        book_slug=shared_book_slug,
        status="completed",
        current_stage="completed",
        config_overrides={"resolved_book_path": other_source_path},
    )
    db.add(target_document_run)
    db.add(target_path_only_run)
    db.add(target_scene_targeted_run)
    db.add(unrelated_scene_targeted_run)
    db.add(other_document_run)
    db.flush()

    target_ranking_one = _build_ranking(
        scene_id=target_scene_one.id,
        pipeline_run_id=target_document_run.id,
        weight_hash=f"hash-{uuid4()}",
    )
    target_ranking_two = _build_ranking(
        scene_id=target_scene_two.id,
        pipeline_run_id=target_scene_targeted_run.id,
        weight_hash=f"hash-{uuid4()}",
    )
    other_ranking = _build_ranking(
        scene_id=other_scene_same_slug.id,
        pipeline_run_id=other_document_run.id,
        weight_hash=f"hash-{uuid4()}",
    )
    db.add(target_ranking_one)
    db.add(target_ranking_two)
    db.add(other_ranking)
    db.flush()

    target_prompt_one = _build_prompt(
        scene_id=target_scene_one.id,
        pipeline_run_id=target_document_run.id,
        variant_index=0,
    )
    target_prompt_two = _build_prompt(
        scene_id=target_scene_two.id,
        pipeline_run_id=target_scene_targeted_run.id,
        variant_index=0,
    )
    other_prompt = _build_prompt(
        scene_id=other_scene_same_slug.id,
        pipeline_run_id=other_document_run.id,
        variant_index=0,
    )
    db.add(target_prompt_one)
    db.add(target_prompt_two)
    db.add(other_prompt)
    db.flush()

    target_asset = GeneratedAsset(
        document_id=target_document.id,
        pipeline_run_id=target_document_run.id,
        scene_extraction_id=target_scene_one.id,
        image_prompt_id=target_prompt_one.id,
        asset_type="image",
        status="created",
        storage_path="img/generated/target-assets/chapter-1",
        file_name="target-asset.png",
        asset_metadata={},
    )
    target_document_only_asset = GeneratedAsset(
        document_id=target_document.id,
        pipeline_run_id=target_document_run.id,
        asset_type="prompt",
        status="created",
        asset_metadata={},
    )
    other_asset = GeneratedAsset(
        document_id=other_document.id,
        pipeline_run_id=other_document_run.id,
        scene_extraction_id=other_scene_same_slug.id,
        image_prompt_id=other_prompt.id,
        asset_type="image",
        status="created",
        storage_path="img/generated/other-assets/chapter-2",
        file_name="other-asset.png",
        asset_metadata={},
    )
    db.add(target_asset)
    db.add(target_document_only_asset)
    db.add(other_asset)
    db.flush()

    target_image_one = GeneratedImage(
        scene_extraction_id=target_scene_one.id,
        image_prompt_id=target_prompt_one.id,
        pipeline_run_id=target_document_run.id,
        generated_asset_id=target_asset.id,
        book_slug=shared_book_slug,
        chapter_number=1,
        variant_index=0,
        provider="openai_gpt_image",
        model="gpt-image-1",
        size="1024x1024",
        quality="standard",
        style="vivid",
        response_format="b64_json",
        storage_path="img/generated/shared-book/chapter-1",
        file_name="target-image-1.png",
    )
    target_image_two = GeneratedImage(
        scene_extraction_id=target_scene_two.id,
        image_prompt_id=target_prompt_two.id,
        pipeline_run_id=target_scene_targeted_run.id,
        book_slug=shared_book_slug,
        chapter_number=1,
        variant_index=0,
        provider="openai_gpt_image",
        model="gpt-image-1",
        size="1024x1024",
        quality="standard",
        style="vivid",
        response_format="b64_json",
        storage_path="img/generated/shared-book/chapter-1",
        file_name="target-image-2.png",
    )
    other_image = GeneratedImage(
        scene_extraction_id=other_scene_same_slug.id,
        image_prompt_id=other_prompt.id,
        pipeline_run_id=other_document_run.id,
        generated_asset_id=other_asset.id,
        book_slug=shared_book_slug,
        chapter_number=2,
        variant_index=0,
        provider="openai_gpt_image",
        model="gpt-image-1",
        size="1024x1024",
        quality="standard",
        style="vivid",
        response_format="b64_json",
        storage_path="img/generated/shared-book/chapter-2",
        file_name="other-image.png",
    )
    db.add(target_image_one)
    db.add(target_image_two)
    db.add(other_image)
    db.flush()

    target_remix_run = PipelineRun(
        book_slug=shared_book_slug,
        status="pending",
        current_stage="pending",
        config_overrides={
            "source_image_id": str(target_image_one.id),
            "source_prompt_id": str(target_prompt_one.id),
        },
    )
    unrelated_remix_run = PipelineRun(
        book_slug=shared_book_slug,
        status="pending",
        current_stage="pending",
        config_overrides={
            "source_image_id": str(other_image.id),
            "source_prompt_id": str(other_prompt.id),
        },
    )
    db.add(target_remix_run)
    db.add(unrelated_remix_run)
    db.flush()

    target_post = SocialMediaPost(
        generated_image_id=target_image_one.id,
        service_name="x",
        status="queued",
    )
    other_post = SocialMediaPost(
        generated_image_id=other_image.id,
        service_name="x",
        status="queued",
    )
    db.add(target_post)
    db.add(other_post)

    target_batch = ImageGenerationBatch(
        openai_batch_id=f"batch-{uuid4()}",
        openai_input_file_id=f"input-{uuid4()}",
        status="submitted",
        task_mapping=[
            {
                "custom_id": "target",
                "image_prompt_id": str(target_prompt_one.id),
                "scene_extraction_id": str(target_scene_one.id),
                "variant_index": 0,
                "book_slug": shared_book_slug,
                "chapter_number": 1,
                "scene_number": 1,
                "storage_path": "img/generated/batch-target/chapter-1",
                "file_name": "batch-target.png",
                "aspect_ratio": "1:1",
            }
        ],
        provider="openai_gpt_image",
        model="gpt-image-1",
        quality="standard",
        style="vivid",
        size="1024x1024",
        total_requests=1,
        book_slug=shared_book_slug,
    )
    other_batch = ImageGenerationBatch(
        openai_batch_id=f"batch-{uuid4()}",
        openai_input_file_id=f"input-{uuid4()}",
        status="submitted",
        task_mapping=[
            {
                "custom_id": "other",
                "image_prompt_id": str(other_prompt.id),
                "scene_extraction_id": str(other_scene_same_slug.id),
                "variant_index": 0,
                "book_slug": shared_book_slug,
                "chapter_number": 2,
                "scene_number": 1,
                "storage_path": "img/generated/batch-other/chapter-2",
                "file_name": "batch-other.png",
                "aspect_ratio": "1:1",
            }
        ],
        provider="openai_gpt_image",
        model="gpt-image-1",
        quality="standard",
        style="vivid",
        size="1024x1024",
        total_requests=1,
        book_slug=shared_book_slug,
    )
    db.add(target_batch)
    db.add(other_batch)
    db.commit()

    target_image_one_path = _write_file(
        tmp_path,
        target_image_one.storage_path,
        target_image_one.file_name,
    )
    target_image_two_path = _write_file(
        tmp_path,
        target_image_two.storage_path,
        target_image_two.file_name,
    )
    target_asset_path = _write_file(
        tmp_path,
        target_asset.storage_path or "",
        target_asset.file_name or "",
    )
    target_batch_path = _write_file(
        tmp_path,
        "img/generated/batch-target/chapter-1",
        "batch-target.png",
    )
    other_image_path = _write_file(
        tmp_path,
        other_image.storage_path,
        other_image.file_name,
    )
    other_asset_path = _write_file(
        tmp_path,
        other_asset.storage_path or "",
        other_asset.file_name or "",
    )
    other_batch_path = _write_file(
        tmp_path,
        "img/generated/batch-other/chapter-2",
        "batch-other.png",
    )

    service = SourceDocumentCleanupService(db, project_root=tmp_path)
    report = service.cleanup_source_document(target_source_path)

    assert report.book_slugs == (shared_book_slug,)
    assert report.document_count == 1
    assert report.scene_count == 2
    assert report.scene_ranking_count == 2
    assert report.image_prompt_count == 2
    assert report.generated_image_count == 2
    assert report.social_post_count == 1
    assert report.generated_asset_count == 2
    assert report.pipeline_run_count == 4
    assert report.image_generation_batch_count == 1
    assert report.targeted_file_count == 4
    assert report.existing_file_count == 4
    assert report.files_deleted == 4

    assert db.get(Document, target_document.id) is None
    assert db.get(SceneExtraction, target_scene_one.id) is None
    assert db.get(SceneExtraction, target_scene_two.id) is None
    assert db.get(SceneRanking, target_ranking_one.id) is None
    assert db.get(SceneRanking, target_ranking_two.id) is None
    assert db.get(ImagePrompt, target_prompt_one.id) is None
    assert db.get(ImagePrompt, target_prompt_two.id) is None
    assert db.get(GeneratedImage, target_image_one.id) is None
    assert db.get(GeneratedImage, target_image_two.id) is None
    assert db.get(SocialMediaPost, target_post.id) is None
    assert db.get(GeneratedAsset, target_asset.id) is None
    assert db.get(GeneratedAsset, target_document_only_asset.id) is None
    assert db.get(PipelineRun, target_document_run.id) is None
    assert db.get(PipelineRun, target_path_only_run.id) is None
    assert db.get(PipelineRun, target_scene_targeted_run.id) is None
    assert db.get(PipelineRun, target_remix_run.id) is None
    assert db.get(ImageGenerationBatch, target_batch.id) is None

    assert db.get(Document, other_document.id) is not None
    assert db.get(SceneExtraction, other_scene_same_slug.id) is not None
    assert db.get(SceneRanking, other_ranking.id) is not None
    assert db.get(ImagePrompt, other_prompt.id) is not None
    assert db.get(GeneratedImage, other_image.id) is not None
    assert db.get(SocialMediaPost, other_post.id) is not None
    assert db.get(GeneratedAsset, other_asset.id) is not None
    assert db.get(PipelineRun, unrelated_scene_targeted_run.id) is not None
    assert db.get(PipelineRun, other_document_run.id) is not None
    assert db.get(PipelineRun, unrelated_remix_run.id) is not None
    assert db.get(ImageGenerationBatch, other_batch.id) is not None

    assert not target_image_one_path.exists()
    assert not target_image_two_path.exists()
    assert not target_asset_path.exists()
    assert not target_batch_path.exists()
    assert other_image_path.exists()
    assert other_asset_path.exists()
    assert other_batch_path.exists()


def test_cleanup_source_document_dry_run_leaves_rows_and_files_in_place(
    db: Session,
    tmp_path: Path,
) -> None:
    target_source_path = f"example_docs/dry-run-story-{uuid4()}.md"
    book_slug = f"test-book-dry-run-{uuid4()}"

    scene = _build_scene(
        source_book_path=target_source_path,
        book_slug=book_slug,
        chapter_number=1,
        scene_number=1,
    )
    db.add(scene)
    db.flush()

    prompt = _build_prompt(
        scene_id=scene.id,
        pipeline_run_id=None,
        variant_index=0,
    )
    db.add(prompt)
    db.flush()

    image = GeneratedImage(
        scene_extraction_id=scene.id,
        image_prompt_id=prompt.id,
        book_slug=book_slug,
        chapter_number=1,
        variant_index=0,
        provider="openai_gpt_image",
        model="gpt-image-1",
        size="1024x1024",
        quality="standard",
        style="vivid",
        response_format="b64_json",
        storage_path="img/generated/dry-run/chapter-1",
        file_name="dry-run-image.png",
    )
    db.add(image)
    db.commit()

    image_path = _write_file(tmp_path, image.storage_path, image.file_name)

    service = SourceDocumentCleanupService(db, project_root=tmp_path)
    report = service.cleanup_source_document(target_source_path, dry_run=True)

    assert report.scene_count == 1
    assert report.image_prompt_count == 1
    assert report.generated_image_count == 1
    assert report.targeted_file_count == 1
    assert report.files_deleted == 0
    assert image_path.exists()
    assert db.get(SceneExtraction, scene.id) is not None
    assert db.get(ImagePrompt, prompt.id) is not None
    assert db.get(GeneratedImage, image.id) is not None
