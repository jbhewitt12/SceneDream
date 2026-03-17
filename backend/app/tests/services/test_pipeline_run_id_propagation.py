"""Tests for pipeline_run_id propagation into created outputs (Phase 4)."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

import app.services.image_generation.image_generation_service as image_generation_service_module
from app.repositories import (
    GeneratedImageRepository,
    ImagePromptRepository,
    PipelineRunRepository,
    SceneRankingRepository,
)
from app.services.image_generation.base_provider import GeneratedImageResult
from app.services.image_generation.image_generation_service import (
    ImageGenerationConfig,
    ImageGenerationService,
)
from app.services.image_prompt_generation import (
    ImagePromptGenerationService,
)
from app.services.langchain import gemini_api
from app.services.scene_ranking import SceneRankingService
from models.image_prompt import ImagePrompt
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _default_llm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture()
def pipeline_run(db: Session) -> PipelineRun:
    """Create a test pipeline run."""
    repo = PipelineRunRepository(db)
    run = repo.create(
        data={
            "book_slug": f"test-book-{uuid4()}",
            "status": "running",
            "config_overrides": {},
        },
        commit=True,
        refresh=True,
    )
    yield run
    db.delete(run)
    db.commit()


# ---------------------------------------------------------------------------
# SceneRanking + pipeline_run_id
# ---------------------------------------------------------------------------


def _mock_ranking_response(score: float = 6.0) -> dict[str, object]:
    scores = {
        "originality": score,
        "visual_style_potential": score,
        "image_prompt_fit": score,
        "video_prompt_fit": score,
        "emotional_intensity": score,
        "worldbuilding_depth": score,
        "character_focus": score,
        "action_dynamism": score,
        "clarity_for_prompting": score,
    }
    return {
        "scores": scores,
        "overall_priority": score,
        "justification": "Test justification for ranking.",
        "warnings": [],
        "character_tags": [],
    }


def test_ranking_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rank_scene with pipeline_run_id should persist it on the SceneRanking row."""
    scene = scene_factory()

    async def fake_json_output(**_: object) -> dict[str, object]:
        return _mock_ranking_response(7.0)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = SceneRankingService(db)
    result = asyncio.run(service.rank_scene(scene, pipeline_run_id=pipeline_run.id))

    assert result is not None
    assert result.pipeline_run_id == pipeline_run.id

    repo = SceneRankingRepository(db)
    stored = repo.get(result.id)
    assert stored is not None
    assert stored.pipeline_run_id == pipeline_run.id


def test_ranking_without_pipeline_run_id_leaves_null(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rank_scene without pipeline_run_id should leave it as None."""
    scene = scene_factory()

    async def fake_json_output(**_: object) -> dict[str, object]:
        return _mock_ranking_response(5.0)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = SceneRankingService(db)
    result = asyncio.run(service.rank_scene(scene))

    assert result is not None
    assert result.pipeline_run_id is None


def test_rank_scenes_propagates_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rank_scenes should pass pipeline_run_id through to each ranking."""
    scene1 = scene_factory()
    scene2 = scene_factory(book_slug=scene1.book_slug)

    async def fake_json_output(**_: object) -> dict[str, object]:
        return _mock_ranking_response(6.0)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = SceneRankingService(db)
    results = asyncio.run(
        service.rank_scenes([scene1, scene2], pipeline_run_id=pipeline_run.id)
    )

    for result in results:
        assert result is not None
        assert result.pipeline_run_id == pipeline_run.id


# ---------------------------------------------------------------------------
# ImagePrompt + pipeline_run_id
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_prompt_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_generate(self, prompts, *, dry_run=False, **_kwargs):  # noqa: ARG001
        results = []
        for prompt in prompts:
            title = (getattr(prompt, "title", None) or "Test Title").strip()
            flavour = "Test flavour."
            if dry_run:
                results.append(
                    {
                        "prompt_id": str(getattr(prompt, "id", uuid4())),
                        "title": title,
                        "flavour_text": flavour,
                        "skipped": False,
                    }
                )
            else:
                prompt.title = title
                prompt.flavour_text = flavour
                results.append(prompt)
        return results

    monkeypatch.setattr(
        "app.services.prompt_metadata.prompt_metadata_service.PromptMetadataGenerationService.generate_metadata_for_prompts",
        _fake_generate,
    )


def _prompt_gen_variants(count: int = 2) -> list[dict[str, object]]:
    return [
        {
            "title": f"Variant {i}",
            "prompt_text": f"A dramatic scene variant {i}.",
            "style_tags": ["cinematic"],
            "attributes": {
                "camera": "dslr",
                "lens": "35mm",
                "composition": "rule-of-thirds",
                "lighting": "neon",
                "palette": "blue",
                "aspect_ratio": "1:1",
            },
        }
        for i in range(count)
    ]


def _patch_context(
    service: ImagePromptGenerationService, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapter = SimpleNamespace(
        number=1,
        title="Chapter 1",
        paragraphs=[
            "Dull intro.",
            "More setup.",
            "City hum.",
            "Rooftop access.",
            "A scout steps onto the roof.",
            "Drones streak across the clouds.",
        ],
        source_name="chapter1.xhtml",
    )
    monkeypatch.setattr(
        service._context_builder,
        "_load_book_context",
        lambda _: {1: chapter},
    )
    monkeypatch.setattr(
        service._prompt_builder,
        "_load_cheatsheet",
        lambda _p: "Cheat sheet guidance",
    )


def test_prompt_generation_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_for_scene with pipeline_run_id should persist it on created prompts."""
    scene = scene_factory(
        chunk_paragraph_start=4,
        chunk_paragraph_end=6,
        scene_paragraph_start=5,
        scene_paragraph_end=6,
    )

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _prompt_gen_variants(2)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = ImagePromptGenerationService(db)
    _patch_context(service, monkeypatch)

    prompts = asyncio.run(
        service.generate_for_scene(
            scene,
            variants_count=2,
            pipeline_run_id=pipeline_run.id,
        )
    )

    assert len(prompts) == 2
    repo = ImagePromptRepository(db)
    for prompt in prompts:
        assert prompt.pipeline_run_id == pipeline_run.id
        stored = repo.get(prompt.id)
        assert stored is not None
        assert stored.pipeline_run_id == pipeline_run.id


def test_prompt_generation_without_pipeline_run_id_leaves_null(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_for_scene without pipeline_run_id should leave it as None."""
    scene = scene_factory(
        chunk_paragraph_start=4,
        chunk_paragraph_end=6,
        scene_paragraph_start=5,
        scene_paragraph_end=6,
    )

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _prompt_gen_variants(1)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = ImagePromptGenerationService(db)
    _patch_context(service, monkeypatch)

    prompts = asyncio.run(service.generate_for_scene(scene, variants_count=1))

    assert len(prompts) == 1
    assert prompts[0].pipeline_run_id is None


def test_remix_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_remix_variants with pipeline_run_id should persist it."""
    scene = scene_factory()
    source_prompt = prompt_factory(scene)

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _prompt_gen_variants(2)

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    service = ImagePromptGenerationService(db)
    prompts = asyncio.run(
        service.generate_remix_variants(
            source_prompt,
            variants_count=2,
            pipeline_run_id=pipeline_run.id,
        )
    )

    assert len(prompts) == 2
    for prompt in prompts:
        assert prompt.pipeline_run_id == pipeline_run.id


def test_custom_remix_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    pipeline_run: PipelineRun,
) -> None:
    """create_custom_remix_variant with pipeline_run_id should persist it."""
    scene = scene_factory()
    source_prompt = prompt_factory(scene)

    service = ImagePromptGenerationService(db)
    result = asyncio.run(
        service.create_custom_remix_variant(
            source_prompt,
            "A completely custom prompt text for testing.",
            pipeline_run_id=pipeline_run.id,
        )
    )

    assert result.pipeline_run_id == pipeline_run.id
    repo = ImagePromptRepository(db)
    stored = repo.get(result.id)
    assert stored is not None
    assert stored.pipeline_run_id == pipeline_run.id


# ---------------------------------------------------------------------------
# GeneratedImage + pipeline_run_id
# ---------------------------------------------------------------------------


async def test_image_generation_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_for_selection with pipeline_run_id should persist it on created images."""
    scene = scene_factory()
    prompt = prompt_factory(
        scene,
        style_tags=["vivid"],
        attributes={"aspect_ratio": "1:1"},
    )

    monkeypatch.setattr(image_generation_service_module, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        image_generation_service_module,
        "_GENERATED_IMAGES_ROOT",
        (tmp_path / "img").resolve(),
    )

    provider = image_generation_service_module.ProviderRegistry.get("openai_gpt_image")
    assert provider is not None

    async def fake_generate_image(**_: object) -> GeneratedImageResult:
        return GeneratedImageResult(image_data=b"test-image-data")

    monkeypatch.setattr(provider, "generate_image", fake_generate_image)

    service = ImageGenerationService(
        db,
        config=ImageGenerationConfig(storage_base="img/generated"),
        api_key="test-key",
    )

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
        provider="openai_gpt_image",
        model="gpt-image-1.5",
        pipeline_run_id=pipeline_run.id,
    )

    assert len(result_ids) == 1
    image_repo = GeneratedImageRepository(db)
    image = image_repo.get(result_ids[0])
    assert image is not None
    assert image.pipeline_run_id == pipeline_run.id


async def test_image_generation_without_pipeline_run_id_leaves_null(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_for_selection without pipeline_run_id should leave it as None."""
    scene = scene_factory()
    prompt = prompt_factory(
        scene,
        style_tags=["vivid"],
        attributes={"aspect_ratio": "1:1"},
    )

    monkeypatch.setattr(image_generation_service_module, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        image_generation_service_module,
        "_GENERATED_IMAGES_ROOT",
        (tmp_path / "img").resolve(),
    )

    provider = image_generation_service_module.ProviderRegistry.get("openai_gpt_image")
    assert provider is not None

    async def fake_generate_image(**_: object) -> GeneratedImageResult:
        return GeneratedImageResult(image_data=b"test-image-data")

    monkeypatch.setattr(provider, "generate_image", fake_generate_image)

    service = ImageGenerationService(
        db,
        config=ImageGenerationConfig(storage_base="img/generated"),
        api_key="test-key",
    )

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
        provider="openai_gpt_image",
        model="gpt-image-1.5",
    )

    assert len(result_ids) == 1
    image_repo = GeneratedImageRepository(db)
    image = image_repo.get(result_ids[0])
    assert image is not None
    assert image.pipeline_run_id is None


async def test_failed_image_record_persists_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    pipeline_run: PipelineRun,
) -> None:
    """Failed image records should carry pipeline_run_id."""
    scene = scene_factory()
    prompt = prompt_factory(
        scene,
        style_tags=["vivid"],
        attributes={"aspect_ratio": "1:1"},
    )

    service = ImageGenerationService(db, api_key="test-key")

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
        pipeline_run_id=pipeline_run.id,
    )

    # Generation failed (no provider mock), so should be empty
    assert result_ids == []

    # But a failed record should have been created with pipeline_run_id
    image_repo = GeneratedImageRepository(db)
    images = image_repo.list_for_scene(scene.id)
    assert len(images) == 1
    assert images[0].error is not None
    assert images[0].pipeline_run_id == pipeline_run.id


async def test_revived_deleted_image_carries_pipeline_run_id(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
    pipeline_run: PipelineRun,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Revived deleted-image rows should be relinked to the current pipeline_run_id."""
    scene = scene_factory()
    prompt = prompt_factory(
        scene,
        style_tags=["vivid"],
        attributes={"aspect_ratio": "1:1"},
    )

    # Create a deleted image record (no pipeline_run_id initially)
    image_repo = GeneratedImageRepository(db)
    image_repo.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "book_slug": scene.book_slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai_gpt_image",
            "model": "gpt-image-1.5",
            "size": "1024x1024",
            "quality": "standard",
            "style": "vivid",
            "aspect_ratio": "1:1",
            "response_format": "b64_json",
            "storage_path": f"img/generated/{scene.book_slug}/chapter-{scene.chapter_number}",
            "file_name": f"scene-{scene.scene_number}-deleted.png",
            "file_deleted": True,
        },
        commit=True,
    )

    monkeypatch.setattr(image_generation_service_module, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        image_generation_service_module,
        "_GENERATED_IMAGES_ROOT",
        (tmp_path / "img").resolve(),
    )

    provider = image_generation_service_module.ProviderRegistry.get("openai_gpt_image")
    assert provider is not None

    async def fake_generate_image(**_: object) -> GeneratedImageResult:
        return GeneratedImageResult(image_data=b"revived-image")

    monkeypatch.setattr(provider, "generate_image", fake_generate_image)

    service = ImageGenerationService(
        db,
        config=ImageGenerationConfig(storage_base="img/generated"),
        api_key="test-key",
    )

    result_ids = await service.generate_for_selection(
        prompt_ids=[prompt.id],
        provider="openai_gpt_image",
        model="gpt-image-1.5",
        pipeline_run_id=pipeline_run.id,
    )

    assert len(result_ids) == 1

    revived = image_repo.get(result_ids[0])
    assert revived is not None
    assert revived.file_deleted is False
    assert revived.pipeline_run_id == pipeline_run.id
