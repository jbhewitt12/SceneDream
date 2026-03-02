"""Unit tests for ImageGenerationService."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories import GeneratedImageRepository
from app.services.image_generation import dalle_image_api
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
    derive_style_from_tags,
    map_aspect_ratio_to_size,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

pytestmark = pytest.mark.anyio("asyncio")


def test_map_aspect_ratio_to_size():
    """Test aspect ratio to size mapping."""
    # GPT Image provider (default)
    assert map_aspect_ratio_to_size("1:1") == "1024x1024"
    assert map_aspect_ratio_to_size("9:16") == "1024x1536"
    assert map_aspect_ratio_to_size("16:9") == "1536x1024"
    assert map_aspect_ratio_to_size(None) == "1024x1024"
    assert map_aspect_ratio_to_size("invalid") == "1024x1024"

    # DALL-E 3 provider - native ratios (7:4 and 4:7 match actual 1792x1024/1024x1792 dimensions)
    assert map_aspect_ratio_to_size("1:1", provider="dalle") == "1024x1024"
    assert map_aspect_ratio_to_size("7:4", provider="dalle") == "1792x1024"
    assert map_aspect_ratio_to_size("4:7", provider="dalle") == "1024x1792"
    # DALL-E 3 provider - legacy ratios (backwards compatibility)
    assert map_aspect_ratio_to_size("16:9", provider="dalle") == "1792x1024"
    assert map_aspect_ratio_to_size("9:16", provider="dalle") == "1024x1792"


def test_derive_style_from_tags():
    """Test style derivation from tags."""
    assert derive_style_from_tags(["cinematic", "natural"], None) == "natural"
    assert derive_style_from_tags(["vivid", "dramatic"], None) == "vivid"
    assert derive_style_from_tags(None, "natural") == "natural"
    assert derive_style_from_tags(["cinematic"], "vivid") == "vivid"
    assert derive_style_from_tags(None, None) == "vivid"


@pytest.mark.anyio("asyncio")
async def test_generate_for_selection_dry_run(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
    anyio_backend_name: str,
):
    if anyio_backend_name != "asyncio":
        pytest.skip("ImageGenerationService requires the asyncio backend")
    """Test dry-run mode doesn't generate images."""
    scene = scene_factory()
    prompt = prompt_factory(scene)

    config = ImageGenerationConfig(dry_run=True)
    service = ImageGenerationService(db, config=config, api_key="test-key")

    # Mock should not be called in dry-run
    monkeypatch.setattr(
        dalle_image_api,
        "generate_images",
        lambda **_: pytest.fail("Should not call API in dry-run"),
    )

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
        dry_run=True,
    )

    assert result_ids == []

    # Verify no images were created
    image_repo = GeneratedImageRepository(db)
    images = image_repo.list_for_scene(scene.id)
    assert len(images) == 0


@pytest.mark.anyio("asyncio")
async def test_generate_for_selection_idempotency(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
    anyio_backend_name: str,
):
    if anyio_backend_name != "asyncio":
        pytest.skip("ImageGenerationService requires the asyncio backend")
    """Test that existing images are not regenerated."""
    scene = scene_factory()
    prompt = prompt_factory(scene)

    # Create an existing image
    image_repo = GeneratedImageRepository(db)
    image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "book_slug": scene.book_slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai",
            "model": "dall-e-3",
            "size": "1792x1024",
            "quality": "standard",
            "style": "vivid",
            "aspect_ratio": "16:9",
            "response_format": "b64_json",
            "storage_path": f"img/generated/{scene.book_slug}/chapter-{scene.chapter_number}",
            "file_name": f"scene-{scene.scene_number}-v0.png",
        },
        commit=True,
    )

    service = ImageGenerationService(db, api_key="test-key")

    # Mock should not be called due to idempotency
    monkeypatch.setattr(
        dalle_image_api,
        "generate_images",
        lambda **_: pytest.fail("Should not call API when image exists"),
    )

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
    )

    # Should skip generation
    assert result_ids == []


@pytest.mark.anyio("asyncio")
async def test_generate_for_selection_filters_by_book(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    anyio_backend_name: str,
):
    if anyio_backend_name != "asyncio":
        pytest.skip("ImageGenerationService requires the asyncio backend")
    """Test filtering prompts by book slug."""
    book_slug = f"test-book-{uuid4()}"
    scene1 = scene_factory(book_slug=book_slug, chapter_number=1)
    scene2 = scene_factory(book_slug=book_slug, chapter_number=2)
    scene3 = scene_factory(book_slug="other-book", chapter_number=1)

    prompt_factory(scene1)
    prompt_factory(scene2)
    prompt_factory(scene3)

    service = ImageGenerationService(db, api_key="test-key")

    result_ids = await service.generate_for_selection(
        book_slug=book_slug,
        dry_run=True,
    )

    # Should return empty list in dry-run
    assert result_ids == []


@pytest.mark.anyio("asyncio")
async def test_generate_for_selection_handles_errors(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
    anyio_backend_name: str,
):
    if anyio_backend_name != "asyncio":
        pytest.skip("ImageGenerationService requires the asyncio backend")
    """Test error handling during generation."""
    scene = scene_factory()
    prompt = prompt_factory(scene)

    # Mock API to raise error
    monkeypatch.setattr(
        dalle_image_api,
        "generate_images",
        lambda **kwargs: [],  # Empty result simulates failure
    )

    service = ImageGenerationService(db, api_key="test-key")

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
    )

    # Should handle error gracefully
    assert result_ids == []

    # Check if failed record was created
    image_repo = GeneratedImageRepository(db)
    images = image_repo.list_for_scene(scene.id)
    assert len(images) == 1
    assert images[0].error is not None
    assert "Failed to generate image" in images[0].error


@pytest.mark.anyio("asyncio")
async def test_generate_for_selection_filters_by_chapter_range(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    anyio_backend_name: str,
):
    if anyio_backend_name != "asyncio":
        pytest.skip("ImageGenerationService requires the asyncio backend")
    """Test filtering prompts by chapter range."""
    book_slug = f"test-book-{uuid4()}"
    scene1 = scene_factory(book_slug=book_slug, chapter_number=1)
    scene2 = scene_factory(book_slug=book_slug, chapter_number=5)
    scene3 = scene_factory(book_slug=book_slug, chapter_number=10)

    prompt_factory(scene1)
    prompt_factory(scene2)
    prompt_factory(scene3)

    service = ImageGenerationService(db, api_key="test-key")

    # Test chapter range filter in dry-run mode
    result_ids = await service.generate_for_selection(
        book_slug=book_slug,
        chapter_range=(3, 8),  # Should only include scene2
        dry_run=True,
    )

    assert result_ids == []
