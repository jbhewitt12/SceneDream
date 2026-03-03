from collections.abc import Callable, Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.core.db import engine
from app.main import app
from app.repositories import (
    GeneratedImageRepository,
    ImagePromptRepository,
    SceneExtractionRepository,
    SceneRankingRepository,
)
from models.document import Document
from models.generated_asset import GeneratedAsset
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

        # Clean up test data: delete all test-book entries
        # This acts as a safety net if individual test fixtures fail to clean up

        # Find all test book slugs (both "test-book" and "test-book-{uuid}" patterns)
        statement = select(SceneExtraction.book_slug).distinct()
        all_book_slugs = session.exec(statement).all()
        test_book_slugs = [
            slug
            for slug in all_book_slugs
            if slug.startswith("test-book") or slug.startswith("gallery-book")
        ]

        # Delete in correct order to respect FK constraints
        for book_slug in test_book_slugs:
            # Get all scenes for this test book
            scenes_stmt = select(SceneExtraction).where(
                SceneExtraction.book_slug == book_slug
            )
            test_scenes = session.exec(scenes_stmt).all()

            for scene in test_scenes:
                # Delete generated images first
                images_stmt = delete(GeneratedImage).where(
                    GeneratedImage.scene_extraction_id == scene.id
                )
                session.execute(images_stmt)

                # Delete canonical generated assets linked to scene
                assets_stmt = delete(GeneratedAsset).where(
                    GeneratedAsset.scene_extraction_id == scene.id
                )
                session.execute(assets_stmt)

                # Delete image prompts
                prompts_stmt = delete(ImagePrompt).where(
                    ImagePrompt.scene_extraction_id == scene.id
                )
                session.execute(prompts_stmt)

                # Delete scene rankings
                rankings_stmt = delete(SceneRanking).where(
                    SceneRanking.scene_extraction_id == scene.id
                )
                session.execute(rankings_stmt)

                # Delete the scene itself
                session.delete(scene)

        # Cleanup pipeline/document test data
        test_documents = session.exec(
            select(Document).where(
                Document.slug.startswith("test-book")
                | Document.slug.startswith("gallery-book")
            )
        ).all()
        for document in test_documents:
            session.execute(
                delete(GeneratedAsset).where(GeneratedAsset.document_id == document.id)
            )
            session.execute(
                delete(PipelineRun).where(PipelineRun.document_id == document.id)
            )
            session.delete(document)

        session.execute(
            delete(PipelineRun).where(
                PipelineRun.book_slug.startswith("test-book")
                | PipelineRun.book_slug.startswith("gallery-book")
            )
        )
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def scene_factory(db: Session) -> Callable[..., SceneExtraction]:
    """Shared factory for creating test SceneExtraction records.

    Accepts keyword overrides for any field. Automatically cleans up
    created scenes and all related records (images, prompts, rankings)
    after the test.
    """
    created: list[SceneExtraction] = []

    def _create(**overrides: object) -> SceneExtraction:
        repository = SceneExtractionRepository(db)
        counter = len(created) + 1
        data: dict[str, object] = {
            "book_slug": f"test-book-{uuid4()}",
            "source_book_path": "documents/test.epub",
            "chapter_number": 1,
            "chapter_title": "Test Chapter",
            "chapter_source_name": "chapter1.xhtml",
            "scene_number": counter,
            "location_marker": f"chapter-1-scene-{counter}",
            "raw": "A futuristic cityscape at sunset with neon lights.",
            "refined": "A sprawling futuristic cityscape at sunset, neon lights reflecting.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 3,
            "raw_word_count": 10,
            "raw_char_count": 50,
            "scene_paragraph_start": 1,
            "scene_paragraph_end": 3,
            "scene_word_start": 1,
            "scene_word_end": 30,
            "extraction_model": "test-model",
            "refinement_model": "test-model",
        }
        data.update(overrides)
        scene = repository.create(data=data, commit=True)
        created.append(scene)
        return scene

    yield _create

    # Cleanup in FK-safe order: images -> prompts -> rankings -> scenes
    image_repo = GeneratedImageRepository(db)
    prompt_repo = ImagePromptRepository(db)
    ranking_repo = SceneRankingRepository(db)
    for scene in created:
        for image in image_repo.list_for_scene(scene.id, include_file_deleted=True):
            db.delete(image)
        asset_stmt = delete(GeneratedAsset).where(
            GeneratedAsset.scene_extraction_id == scene.id
        )
        db.execute(asset_stmt)
        prompt_repo.delete_for_scene(scene.id, commit=False)
        for ranking in ranking_repo.list_for_scene(scene.id):
            db.delete(ranking)
        db.delete(scene)
    db.commit()


@pytest.fixture()
def prompt_factory(db: Session) -> Callable[..., ImagePrompt]:
    """Shared factory for creating test ImagePrompt records.

    Requires a SceneExtraction as the first argument. Accepts keyword
    overrides for any field. Cleanup is handled by scene_factory teardown.
    """
    created: list[ImagePrompt] = []

    def _create(scene: SceneExtraction, **overrides: object) -> ImagePrompt:
        repository = ImagePromptRepository(db)
        counter = len(created)
        data: dict[str, object] = {
            "scene_extraction_id": scene.id,
            "model_vendor": "test-vendor",
            "model_name": "test-model",
            "prompt_version": "test-v1",
            "variant_index": counter,
            "title": f"Test Prompt {counter}",
            "prompt_text": "A dramatic sci-fi scene with vibrant neon colors and dynamic composition.",
            "negative_prompt": None,
            "style_tags": ["cinematic", "vivid"],
            "attributes": {
                "camera": "dslr",
                "lens": "35mm",
                "composition": "rule-of-thirds",
                "lighting": "neon glow",
                "palette": "cyan and magenta",
                "aspect_ratio": "16:9",
                "references": ["Blade Runner"],
            },
            "notes": None,
            "context_window": {
                "chapter_number": scene.chapter_number,
                "paragraph_span": [1, 3],
            },
            "raw_response": {},
            "temperature": 0.7,
            "max_output_tokens": 2048,
            "llm_request_id": None,
            "execution_time_ms": 1000,
        }
        data.update(overrides)
        prompt = repository.create(data=data, commit=True)
        created.append(prompt)
        return prompt

    yield _create
