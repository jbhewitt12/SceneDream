"""Unit tests for ImageGenerationService."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel import Session

import app.services.image_generation.image_generation_service as image_generation_service_module
from app.repositories import GeneratedImageRepository
from app.services.image_generation import dalle_image_api
from app.services.image_generation.image_generation_service import (
    ImageFileNotFoundError,
    ImageFileWriteError,
    ImageGenerationConfig,
    ImageGenerationService,
    ImageNotFoundError,
    _default_project_root_from_path,
    derive_style_from_tags,
    map_aspect_ratio_to_size,
)
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture()
def anyio_backend() -> str:
    """ImageGenerationService requires the asyncio backend."""
    return "asyncio"


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


def test_default_project_root_detects_local_layout() -> None:
    source_file = Path(
        "/Users/test/SceneDream/backend/app/services/image_generation/image_generation_service.py"
    )
    assert _default_project_root_from_path(source_file) == Path(
        "/Users/test/SceneDream"
    )


def test_default_project_root_detects_container_layout() -> None:
    source_file = Path("/app/app/services/image_generation/image_generation_service.py")
    assert _default_project_root_from_path(source_file) == Path("/app")


async def test_generate_for_selection_dry_run(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
):
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


async def test_generate_for_selection_idempotency(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
):
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


async def test_generate_for_selection_filters_by_book(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
):
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


async def test_fetch_prompts_for_top_scenes_skips_duplicate_rankings(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
):
    """Duplicate ranking rows should not block later prompt-ready scenes."""
    book_slug = f"test-book-{uuid4()}"
    scene_with_image = scene_factory(book_slug=book_slug, chapter_number=1)
    prompt_with_image = prompt_factory(scene_with_image, variant_index=0)

    image_repo = GeneratedImageRepository(db)
    image_repo.create(
        data={
            "scene_extraction_id": scene_with_image.id,
            "image_prompt_id": prompt_with_image.id,
            "book_slug": scene_with_image.book_slug,
            "chapter_number": scene_with_image.chapter_number,
            "variant_index": 0,
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "aspect_ratio": "1:1",
            "response_format": "b64_json",
            "storage_path": f"img/generated/{scene_with_image.book_slug}/chapter-{scene_with_image.chapter_number}",
            "file_name": f"scene-{scene_with_image.scene_number}-v0.png",
        },
        commit=True,
    )

    scene_without_prompts = scene_factory(book_slug=book_slug, chapter_number=2)
    scene_prompt_ready = scene_factory(book_slug=book_slug, chapter_number=3)
    prompt_ready = prompt_factory(scene_prompt_ready, variant_index=0)

    rankings = [
        SimpleNamespace(
            scene_extraction_id=scene_with_image.id,
            overall_priority=9.5,
            warnings=[],
        ),
        SimpleNamespace(
            scene_extraction_id=scene_with_image.id,
            overall_priority=9.4,
            warnings=[],
        ),
        SimpleNamespace(
            scene_extraction_id=scene_without_prompts.id,
            overall_priority=9.3,
            warnings=[],
        ),
        SimpleNamespace(
            scene_extraction_id=scene_prompt_ready.id,
            overall_priority=9.2,
            warnings=[],
        ),
    ]

    service = ImageGenerationService(db, api_key="test-key")
    monkeypatch.setattr(
        service._ranking_repo,
        "list_top_rankings_for_book",
        lambda **_kwargs: rankings,
    )

    prompts = await service._fetch_prompts_for_top_scenes(
        book_slug=book_slug,
        top_scenes_count=1,
    )

    assert [prompt.id for prompt in prompts] == [prompt_ready.id]


async def test_generate_for_selection_handles_errors(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
):
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


async def test_generate_for_selection_filters_by_chapter_range(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
):
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


def test_resolve_image_file_falls_back_to_legacy_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    generated_root = (project_root / "img").resolve()
    generated_root.mkdir(parents=True, exist_ok=True)

    legacy_project_root = tmp_path / "legacy"
    legacy_file = (
        legacy_project_root / "img" / "generated" / "book" / "chapter" / "image.png"
    )
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes(b"png")

    monkeypatch.setattr(image_generation_service_module, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        image_generation_service_module,
        "_GENERATED_IMAGES_ROOT",
        generated_root,
    )
    monkeypatch.setattr(
        image_generation_service_module,
        "_LEGACY_PROJECT_ROOT",
        legacy_project_root,
    )
    monkeypatch.setattr(
        image_generation_service_module,
        "_LEGACY_GENERATED_IMAGES_ROOT",
        (legacy_project_root / "img" / "generated").resolve(),
    )

    resolved = image_generation_service_module._resolve_image_file(
        "img/generated/book/chapter",
        "image.png",
    )

    assert resolved == legacy_file.resolve()


async def test_save_cropped_image_writes_file_contents(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ImageGenerationService(db, api_key="test-key")
    image_id = uuid4()
    image = SimpleNamespace(
        id=image_id,
        storage_path="img/generated/book/chapter-1",
        file_name="image.png",
        file_deleted=False,
    )
    file_path = MagicMock(spec=Path)
    file_path.exists.return_value = True
    file_path.is_file.return_value = True

    class FakeLoop:
        def __init__(self) -> None:
            self.run_in_executor_called = False

        async def run_in_executor(
            self,
            _executor: object | None,
            func: Callable[..., object],
            *args: object,
        ) -> object:
            self.run_in_executor_called = True
            return func(*args)

    fake_loop = FakeLoop()
    monkeypatch.setattr(service._image_repo, "get", lambda _: image)
    monkeypatch.setattr(
        image_generation_service_module,
        "_resolve_image_file",
        lambda _storage_path, _file_name: file_path,
    )
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    payload = b"cropped-image-bytes"
    await service.save_cropped_image(image_id, payload)

    assert fake_loop.run_in_executor_called is True
    file_path.write_bytes.assert_called_once_with(payload)


async def test_save_cropped_image_raises_when_image_not_found(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ImageGenerationService(db, api_key="test-key")
    image_id = uuid4()
    monkeypatch.setattr(service._image_repo, "get", lambda _: None)

    with pytest.raises(ImageNotFoundError, match="Generated image not found"):
        await service.save_cropped_image(image_id, b"cropped-image-bytes")


async def test_save_cropped_image_raises_when_write_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ImageGenerationService(db, api_key="test-key")
    image_id = uuid4()
    image = SimpleNamespace(
        id=image_id,
        storage_path="img/generated/book/chapter-1",
        file_name="image.png",
        file_deleted=False,
    )
    file_path = MagicMock(spec=Path)
    file_path.exists.return_value = True
    file_path.is_file.return_value = True
    file_path.write_bytes.side_effect = OSError("disk full")

    class FakeLoop:
        async def run_in_executor(
            self,
            _executor: object | None,
            func: Callable[..., object],
            *args: object,
        ) -> object:
            return func(*args)

    monkeypatch.setattr(service._image_repo, "get", lambda _: image)
    monkeypatch.setattr(
        image_generation_service_module,
        "_resolve_image_file",
        lambda _storage_path, _file_name: file_path,
    )
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: FakeLoop())

    with pytest.raises(ImageFileWriteError, match="Failed to save cropped image"):
        await service.save_cropped_image(image_id, b"cropped-image-bytes")


async def test_save_cropped_image_raises_when_file_missing(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ImageGenerationService(db, api_key="test-key")
    image_id = uuid4()
    image = SimpleNamespace(
        id=image_id,
        storage_path="img/generated/book/chapter-1",
        file_name="image.png",
        file_deleted=False,
    )
    file_path = MagicMock(spec=Path)
    file_path.exists.return_value = False
    file_path.is_file.return_value = False

    monkeypatch.setattr(service._image_repo, "get", lambda _: image)
    monkeypatch.setattr(
        image_generation_service_module,
        "_resolve_image_file",
        lambda _storage_path, _file_name: file_path,
    )

    with pytest.raises(
        ImageFileNotFoundError,
        match="Original image file not found on disk",
    ):
        await service.save_cropped_image(image_id, b"cropped-image-bytes")
