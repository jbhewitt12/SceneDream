import asyncio
import random
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
)
from app.repositories import ImagePromptRepository
from app.services.image_prompt_generation import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
    ImagePromptPreview,
)
from app.services.image_prompt_generation.strategies.dalle_strategy import (
    DallePromptStrategy,
)
from app.services.image_prompt_generation.strategies.gpt_image_strategy import (
    GptImagePromptStrategy,
)
from app.services.langchain import gemini_api, openai_api
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

DOCUMENTS_DIR = Path(__file__).resolve().parents[4] / "documents"
LEGACY_BOOKS_DIR = Path(__file__).resolve().parents[4] / "books"
CONTENT_DIR = DOCUMENTS_DIR if DOCUMENTS_DIR.exists() else LEGACY_BOOKS_DIR

EXCESSION_EPUB = (
    CONTENT_DIR / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"
)


@pytest.fixture(autouse=True)
def _stub_prompt_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_generate(self, prompts, *, dry_run=False, **_kwargs):  # type: ignore[no-untyped-def]  # noqa: ARG001
        results = []
        for prompt in prompts:
            title = (getattr(prompt, "title", None) or "Shareable Moment").strip()
            flavour = "Test flavour text for preview."
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


@pytest.fixture(autouse=True)
def _default_llm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "")


def _variants(
    payload: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if payload is not None:
        return payload
    return [
        {
            "title": "Neon Watchtower",
            "prompt_text": "Ultra wide shot of a scout on a rooftop garden overlooking a neon megacity at dusk.",
            "style_tags": ["cinematic", "neon", "ultra-wide"],
            "attributes": {
                "camera": "mirrorless",
                "lens": "24mm",
                "composition": "rule-of-thirds",
                "lighting": "dusk glow",
                "palette": "violet and teal",
                "aspect_ratio": "16:9",
                "references": ["Syd Mead"],
            },
        },
        {
            "title": "Garden Overwatch",
            "prompt_text": "Medium shot of a vigilant scout amid bioluminescent plants above a bustling street.",
            "style_tags": ["noir", "moody"],
            "attributes": {
                "camera": "dslr",
                "lens": "50mm",
                "composition": "leading-lines",
                "lighting": "rain-soaked neon",
                "palette": "amber and magenta",
                "aspect_ratio": "3:2",
                "references": ["Blade Runner"],
            },
        },
    ]


def _patch_context(
    service: ImagePromptGenerationService, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapter = SimpleNamespace(
        number=1,
        title="Chapter 1",
        paragraphs=[
            "Dull intro paragraph.",
            "More setup text.",
            "City hum intensifies.",
            "Rooftop access tunnel.",
            "A scout steps onto the roof garden and scans the skyline.",
            "Drones streak across the clouds as neon reflections ripple.",
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


def _create_prompt(
    db: Session,
    scene: SceneExtraction,
    *,
    variant_index: int = 0,
) -> ImagePrompt:
    repository = ImagePromptRepository(db)
    return repository.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "google",
            "model_name": "gemini-2.5-flash",
            "prompt_version": "image-prompts-v1",
            "variant_index": variant_index,
            "title": "Original prompt",
            "flavour_text": "Original flavour",
            "prompt_text": "Wide shot of a scout on a rooftop garden.",
            "negative_prompt": None,
            "style_tags": ["cinematic"],
            "attributes": {"camera": "mirrorless"},
            "notes": None,
            "context_window": {
                "chapter_number": scene.chapter_number,
                "paragraph_span": [2, 4],
                "paragraphs_before": 2,
                "paragraphs_after": 1,
            },
            "raw_response": {
                "response": [],
                "service": {"mode": "baseline"},
            },
            "temperature": 0.4,
            "max_output_tokens": 8192,
            "llm_request_id": "test-llm-request",
            "execution_time_ms": 1200,
        },
        commit=True,
        refresh=True,
    )


def test_generate_for_scene_creates_prompts(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory(
        chunk_paragraph_start=4,
        chunk_paragraph_end=6,
        scene_paragraph_start=5,
        scene_paragraph_end=6,
    )
    config = ImagePromptGenerationConfig(variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    captured_prompt: dict[str, str] = {}
    monkeypatch.setattr(random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)

    async def fake_json_output(**kwargs: object) -> list[dict[str, object]]:
        captured_prompt["prompt"] = kwargs.get("prompt", "")
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert len(results) == 2
    assert captured_prompt["prompt"].startswith("You are an elite prompt engineer")

    repository = ImagePromptRepository(db)
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    first = stored[0]
    # paragraph_span is now just the scene span, not including context
    assert first.context_window["paragraph_span"] == [5, 6]
    assert "prompt" not in first.raw_response
    assert first.raw_response["service"]["prompt_hash"]
    assert first.raw_response["service"]["prompt_art_style_mode"] == "random_mix"
    # Check that sampled_styles contains expected styles (order may vary due to shuffle)
    sampled_styles = first.raw_response["service"]["sampled_styles"]
    assert len(sampled_styles) >= 4

    repository.delete_for_scene(scene.id, commit=True)


def test_generate_for_scene_dry_run_returns_previews(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(dry_run=True, variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert all(isinstance(item, ImagePromptPreview) for item in results)
    preview = results[0]
    assert "prompt" in preview.raw_response
    assert preview.raw_response["service"]["prompt_art_style_mode"] == "random_mix"
    assert preview.raw_response["service"]["prompt_art_style_text"] is None
    assert preview.raw_response["service"]["prompt_art_style"]["mode"] == "random_mix"
    assert preview.raw_response["service"]["prompt_art_style"]["style_text"] is None
    assert (
        preview.raw_response["service"]["prompt_art_style"]["sampled_styles"]
        == (preview.raw_response["service"]["sampled_styles"])
    )
    repository = ImagePromptRepository(db)
    assert repository.list_for_scene(scene.id) == []


def test_generate_for_scene_falls_back_to_openai(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(dry_run=True, variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fail_gemini(**_: object) -> list[dict[str, object]]:
        raise AssertionError("Gemini should not be called when key is missing")

    captured_force_json: dict[str, object] = {}

    async def fake_openai_json_output(**kwargs: object) -> list[dict[str, object]]:
        captured_force_json["value"] = kwargs.get("force_json_object")
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)
    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    previews = asyncio.run(service.generate_for_scene(scene))

    assert all(isinstance(item, ImagePromptPreview) for item in previews)
    assert previews[0].model_vendor == "openai"
    assert previews[0].model_name == "gpt-5-mini"
    assert captured_force_json["value"] is False


def test_generate_for_scene_includes_exception_type_when_retry_error_is_blank(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(
        dry_run=True,
        variants_count=1,
        retry_attempts=0,
    )
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fail_gemini(**_: object) -> list[dict[str, object]]:
        raise TimeoutError()

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)

    with pytest.raises(
        ImagePromptGenerationServiceError,
        match="LLM prompt generation failed after retries: TimeoutError",
    ):
        asyncio.run(service.generate_for_scene(scene))


def test_generate_for_scene_includes_exception_message_in_retry_error(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(
        dry_run=True,
        variants_count=1,
        retry_attempts=0,
    )
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fail_gemini(**_: object) -> list[dict[str, object]]:
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)

    with pytest.raises(
        ImagePromptGenerationServiceError,
        match="LLM prompt generation failed after retries: RuntimeError: quota exceeded",
    ):
        asyncio.run(service.generate_for_scene(scene))


def test_generate_for_scene_returns_existing_when_overwrite_disabled(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    repository = ImagePromptRepository(db)
    config = ImagePromptGenerationConfig(
        variants_count=2,
        allow_overwrite=False,
        model_name="gemini-2.5-flash",
    )
    existing = repository.bulk_create(
        [
            {
                "scene_extraction_id": scene.id,
                "model_vendor": "google",
                "model_name": "gemini-2.5-flash",
                "prompt_version": config.prompt_version,
                "variant_index": 0,
                "title": "Existing",
                "prompt_text": "Existing prompt",
                "negative_prompt": None,
                "style_tags": ["legacy"],
                "attributes": {"camera": "dslr"},
                "notes": None,
                "context_window": {
                    "chapter_number": scene.chapter_number,
                    "paragraph_span": [1, 3],
                    "paragraphs_before": 3,
                    "paragraphs_after": 1,
                },
                "raw_response": {
                    "response": [],
                    "service": {
                        "prompt_art_style_mode": "random_mix",
                        "prompt_art_style_text": None,
                        "target_provider": "gpt-image",
                    },
                },
                "temperature": 0.4,
                "max_output_tokens": 8192,
                "llm_request_id": None,
                "execution_time_ms": 100,
            },
            {
                "scene_extraction_id": scene.id,
                "model_vendor": "google",
                "model_name": "gemini-2.5-flash",
                "prompt_version": config.prompt_version,
                "target_provider": config.target_provider,
                "variant_index": 1,
                "title": "Existing Two",
                "prompt_text": "Existing prompt two",
                "negative_prompt": None,
                "style_tags": ["legacy"],
                "attributes": {"camera": "dslr"},
                "notes": None,
                "context_window": {
                    "chapter_number": scene.chapter_number,
                    "paragraph_span": [1, 3],
                    "paragraphs_before": 3,
                    "paragraphs_after": 1,
                },
                "raw_response": {
                    "response": [],
                    "service": {
                        "prompt_art_style_mode": "random_mix",
                        "prompt_art_style_text": None,
                        "target_provider": config.target_provider,
                    },
                },
                "temperature": 0.4,
                "max_output_tokens": 8192,
                "llm_request_id": None,
                "execution_time_ms": 100,
            },
        ],
        commit=True,
    )

    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fail_json_output(**_: object) -> list[dict[str, object]]:
        pytest.fail("json_output should not be invoked")

    monkeypatch.setattr(gemini_api, "json_output", fail_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert results == existing
    repository.delete_for_scene(scene.id, commit=True)


def test_generate_for_scene_appends_new_prompts_when_style_selection_changes(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing prompts are never deleted; new variants are appended at the next index."""
    scene = scene_factory()
    repository = ImagePromptRepository(db)
    config = ImagePromptGenerationConfig(
        variants_count=2,
        allow_overwrite=False,
        model_name="gemini-2.5-flash",
        prompt_art_style_mode=PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    )
    existing = repository.bulk_create(
        [
            {
                "scene_extraction_id": scene.id,
                "model_vendor": "google",
                "model_name": "gemini-2.5-flash",
                "prompt_version": config.prompt_version,
                "target_provider": config.target_provider,
                "variant_index": 0,
                "title": "Existing",
                "prompt_text": "Existing prompt",
                "negative_prompt": None,
                "style_tags": ["legacy"],
                "attributes": {"camera": "dslr"},
                "notes": None,
                "context_window": {
                    "chapter_number": scene.chapter_number,
                    "paragraph_span": [1, 3],
                    "paragraphs_before": 3,
                    "paragraphs_after": 1,
                },
                "raw_response": {
                    "response": [],
                    "service": {
                        "prompt_art_style_mode": "single_style",
                        "prompt_art_style_text": "Graphite realism",
                        "target_provider": config.target_provider,
                    },
                },
                "temperature": 0.4,
                "max_output_tokens": 8192,
                "llm_request_id": None,
                "execution_time_ms": 100,
            },
            {
                "scene_extraction_id": scene.id,
                "model_vendor": "google",
                "model_name": "gemini-2.5-flash",
                "prompt_version": config.prompt_version,
                "target_provider": config.target_provider,
                "variant_index": 1,
                "title": "Existing Two",
                "prompt_text": "Existing prompt two",
                "negative_prompt": None,
                "style_tags": ["legacy"],
                "attributes": {"camera": "dslr"},
                "notes": None,
                "context_window": {
                    "chapter_number": scene.chapter_number,
                    "paragraph_span": [1, 3],
                    "paragraphs_before": 3,
                    "paragraphs_after": 1,
                },
                "raw_response": {
                    "response": [],
                    "service": {
                        "prompt_art_style_mode": "single_style",
                        "prompt_art_style_text": "Graphite realism",
                        "target_provider": config.target_provider,
                    },
                },
                "temperature": 0.4,
                "max_output_tokens": 8192,
                "llm_request_id": None,
                "execution_time_ms": 100,
            },
        ],
        commit=True,
    )

    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    # New prompts are created, not the existing ones
    assert len(results) == 2
    assert [prompt.id for prompt in results] != [prompt.id for prompt in existing]

    # New prompts get the next available variant indices (2, 3)
    new_indices = sorted(prompt.variant_index for prompt in results)
    assert new_indices == [2, 3]

    # Existing prompts are preserved — total is now 4
    stored = repository.list_for_scene(
        scene.id,
        model_name=config.model_name,
        prompt_version=config.prompt_version,
    )
    assert len(stored) == 4
    existing_ids = {p.id for p in existing}
    assert all(p.id in existing_ids for p in stored if p.variant_index < 2)
    repository.delete_for_scene(scene.id, commit=True)


def test_create_custom_remix_variant_persists_prompt(
    db: Session, scene_factory
) -> None:
    scene = scene_factory()
    base_prompt = _create_prompt(db, scene)
    service = ImagePromptGenerationService(db)

    edited_text = "Close-up portrait of the rooftop scout with neon reflections."
    created = asyncio.run(service.create_custom_remix_variant(base_prompt, edited_text))

    assert isinstance(created, ImagePrompt)
    assert created.scene_extraction_id == scene.id
    assert created.variant_index == base_prompt.variant_index + 1
    assert created.prompt_text == edited_text
    assert created.style_tags == base_prompt.style_tags
    assert created.attributes == base_prompt.attributes
    assert created.raw_response["custom_remix"] is True
    assert created.raw_response["custom_prompt_text"] == edited_text
    assert created.title == "Shareable Moment"

    repository = ImagePromptRepository(db)
    stored_prompts = repository.list_for_scene(scene.id, newest_first=False)
    assert any(prompt.id == created.id for prompt in stored_prompts)


def test_create_custom_remix_variant_rejects_empty_text(
    db: Session, scene_factory
) -> None:
    scene = scene_factory()
    base_prompt = _create_prompt(db, scene)
    service = ImagePromptGenerationService(db)

    with pytest.raises(ImagePromptGenerationServiceError):
        asyncio.run(service.create_custom_remix_variant(base_prompt, "   "))


def test_create_custom_remix_variant_dry_run_returns_preview(
    db: Session, scene_factory
) -> None:
    scene = scene_factory()
    base_prompt = _create_prompt(db, scene)
    service = ImagePromptGenerationService(db)

    preview = asyncio.run(
        service.create_custom_remix_variant(
            base_prompt,
            "Wide shot of the scout overlooking traffic trails.",
            dry_run=True,
        )
    )

    assert isinstance(preview, ImagePromptPreview)
    assert preview.variant_index == base_prompt.variant_index + 1
    assert preview.raw_response["custom_remix"] is True
    assert preview.prompt_text.endswith("traffic trails.")

    repository = ImagePromptRepository(db)
    stored_prompts = repository.list_for_scene(scene.id)
    assert stored_prompts == [base_prompt]


def test_generate_for_scene_appends_when_overwrite_allowed(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """allow_overwrite=True appends new prompts at next indices; existing are preserved."""
    scene = scene_factory()
    repository = ImagePromptRepository(db)
    config = ImagePromptGenerationConfig(
        variants_count=2,
        allow_overwrite=True,
        model_name="gemini-2.5-flash",
    )
    repository.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "google",
            "model_name": "gemini-2.5-flash",
            "prompt_version": config.prompt_version,
            "variant_index": 0,
            "title": "Old",
            "prompt_text": "Old prompt",
            "negative_prompt": None,
            "style_tags": ["legacy"],
            "attributes": {"camera": "dslr"},
            "notes": None,
            "context_window": {
                "chapter_number": scene.chapter_number,
                "paragraph_span": [1, 3],
                "paragraphs_before": 3,
                "paragraphs_after": 1,
            },
            "raw_response": {"response": []},
            "temperature": 0.4,
            "max_output_tokens": 8192,
            "llm_request_id": None,
            "execution_time_ms": 100,
        },
        commit=True,
    )

    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    # Two new prompts created at indices 1, 2 (next after existing index 0)
    assert len(results) == 2
    new_indices = sorted(prompt.variant_index for prompt in results)
    assert new_indices == [1, 2]

    # Old prompt is preserved — total is now 3
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 3
    assert any(prompt.title == "Old" for prompt in stored)
    assert all(
        prompt.title in {"Neon Watchtower", "Garden Overwatch", "Old"}
        for prompt in stored
    )

    repository.delete_for_scene(scene.id, commit=True)


def test_sample_styles_respects_formula(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.image_prompt_generation.core.style_sampler import StyleSampler

    # Create a custom StyleSampler with test styles
    test_sampler = StyleSampler(
        recommended_styles=("A", "B", "C", "D", "E"),
        other_styles=("X", "Y", "Z"),
    )
    monkeypatch.setattr(random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)

    styles = test_sampler.sample(variants_count=4)

    assert styles == ["A", "B", "C", "D", "E", "X", "Y"]


def test_sample_styles_keeps_realism_related_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.image_prompt_generation.core.style_sampler import StyleSampler

    # Realism-related styles should pass through sampling unchanged.
    test_sampler = StyleSampler(
        recommended_styles=("Stylised", "Photorealistic ink", "Shared"),
        other_styles=("live-action still", "Safe Option"),
    )
    monkeypatch.setattr(random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)

    styles = test_sampler.sample(variants_count=4)

    assert "Photorealistic ink" in styles
    assert "live-action still" in styles
    assert "Stylised" in styles


def test_config_defaults_to_random_mix_mode() -> None:
    config = ImagePromptGenerationConfig()

    assert config.prompt_art_style_mode == PROMPT_ART_STYLE_MODE_RANDOM_MIX
    assert config.prompt_art_style_text is None


def test_config_preserves_single_style_text() -> None:
    config = ImagePromptGenerationConfig(
        prompt_art_style_mode=PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
        prompt_art_style_text="Painterly realism",
    )

    assert config.prompt_art_style_mode == PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    assert config.prompt_art_style_text == "Painterly realism"


def test_service_resolves_random_mix_style_plan(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_factory()
    service = ImagePromptGenerationService(
        db,
        config=ImagePromptGenerationConfig(variants_count=2),
    )
    monkeypatch.setattr(
        service._prompt_builder,
        "sample_styles",
        lambda variants_count: ["Style A", "Style B", "Style C"],
    )

    plan = service._resolve_prompt_art_style_plan(config=service._config)

    assert plan.mode == PROMPT_ART_STYLE_MODE_RANDOM_MIX
    assert plan.style_text is None
    assert plan.sampled_styles == ["Style A", "Style B", "Style C"]


def test_service_resolves_single_style_plan_without_sampling(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_factory()
    service = ImagePromptGenerationService(
        db,
        config=ImagePromptGenerationConfig(
            prompt_art_style_mode=PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
            prompt_art_style_text="Runtime Override Style",
        ),
    )
    monkeypatch.setattr(
        service._prompt_builder,
        "sample_styles",
        lambda variants_count: pytest.fail(
            "sample_styles should not run for single_style"
        ),
    )

    plan = service._resolve_prompt_art_style_plan(config=service._config)

    assert plan.mode == PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    assert plan.style_text == "Runtime Override Style"
    assert plan.sampled_styles == []


def test_service_raises_when_random_mix_style_catalog_is_empty(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_factory()
    monkeypatch.setattr(
        "app.services.art_style.art_style_service.ArtStyleService.get_sampling_distribution",
        lambda self: ([], []),
    )
    service = ImagePromptGenerationService(db)

    with pytest.raises(
        ImagePromptGenerationServiceError,
        match="Art style catalog is empty",
    ):
        service._resolve_prompt_art_style_plan(config=service._config)


def test_service_allows_single_style_with_empty_catalog(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene_factory()
    monkeypatch.setattr(
        "app.services.art_style.art_style_service.ArtStyleService.get_sampling_distribution",
        lambda self: ([], []),
    )
    service = ImagePromptGenerationService(
        db,
        config=ImagePromptGenerationConfig(
            prompt_art_style_mode=PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
            prompt_art_style_text="Graphite realism",
        ),
    )

    plan = service._resolve_prompt_art_style_plan(config=service._config)

    assert plan.mode == PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    assert plan.style_text == "Graphite realism"
    assert plan.sampled_styles == []


def test_render_prompt_template_includes_suggested_styles(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.image_prompt_generation.core.style_sampler import StyleSampler
    from app.services.image_prompt_generation.prompt_builder import PromptBuilder

    scene = scene_factory()
    config = ImagePromptGenerationConfig(variants_count=4)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    # Create a custom StyleSampler and PromptBuilder with test styles
    test_sampler = StyleSampler(
        recommended_styles=(
            "Style A",
            "Style B",
            "Style C",
            "Style D",
            "Style E",
            "Style F",
        ),
        other_styles=("Other A", "Other B", "Other C"),
    )
    service._prompt_builder = PromptBuilder(style_sampler=test_sampler)
    # Re-patch the cheatsheet loader on the new prompt builder
    monkeypatch.setattr(
        service._prompt_builder,
        "_load_cheatsheet",
        lambda _p: "Cheat sheet guidance",
    )
    monkeypatch.setattr(random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)

    prompt, resolved_config, _, _, sampled_styles = service.render_prompt_template(
        scene
    )

    assert resolved_config.variants_count == 4
    assert sampled_styles == [
        "Style A",
        "Style B",
        "Style C",
        "Style D",
        "Style E",
        "Style F",
        "Other A",
        "Other B",
    ]
    assert "Suggested Styles for This Request" in prompt
    assert (
        "Explicitly weave the chosen medium or art era into prompt_text and style_tags"
        in prompt
    )
    for style in sampled_styles:
        assert style in prompt


def test_render_prompt_template_uses_fixed_style_section_for_single_style(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    service = ImagePromptGenerationService(
        db,
        config=ImagePromptGenerationConfig(
            variants_count=3,
            prompt_art_style_mode=PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
            prompt_art_style_text="Painterly realism",
        ),
    )
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(
        service._prompt_builder,
        "sample_styles",
        lambda variants_count: pytest.fail(
            "sample_styles should not run for single_style"
        ),
    )

    prompt, resolved_config, _, _, sampled_styles = service.render_prompt_template(
        scene
    )

    assert resolved_config.prompt_art_style_mode == PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    assert resolved_config.prompt_art_style_text == "Painterly realism"
    assert sampled_styles == []
    assert "Fixed Art Style for This Request" in prompt
    assert "Painterly realism" in prompt
    assert "Suggested Styles for This Request" not in prompt
    assert "do not reuse the same style family or medium twice" not in prompt
    assert "keeping the same art style across the full set" in prompt


def test_generate_for_scene_dry_run_single_style_records_mode_specific_metadata(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(
        dry_run=True,
        variants_count=2,
        prompt_art_style_mode=PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
        prompt_art_style_text="Painterly realism",
    )
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(
        service._prompt_builder,
        "sample_styles",
        lambda variants_count: pytest.fail(
            "sample_styles should not run for single_style"
        ),
    )

    async def fake_json_output(**_: object) -> list[dict[str, object]]:
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert all(isinstance(item, ImagePromptPreview) for item in results)
    preview = results[0]
    assert preview.raw_response["service"]["prompt_art_style_mode"] == "single_style"
    assert (
        preview.raw_response["service"]["prompt_art_style_text"] == "Painterly realism"
    )
    assert preview.raw_response["service"]["prompt_art_style"] == {
        "mode": "single_style",
        "style_text": "Painterly realism",
    }
    assert "sampled_styles" not in preview.raw_response["service"]
    assert "Fixed Art Style for This Request" in preview.raw_response["prompt"]


def test_dalle_strategy_returns_mode_specific_style_guidance() -> None:
    strategy = DallePromptStrategy()

    random_mix_guidance = strategy.get_style_strategy(PROMPT_ART_STYLE_MODE_RANDOM_MIX)
    single_style_guidance = strategy.get_style_strategy(
        PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    )

    assert "pick unique candidates for each variant" in random_mix_guidance
    assert "Keep the fixed art style consistent across every variant" in (
        single_style_guidance
    )
    assert "pick unique candidates for each variant" not in single_style_guidance


def test_gpt_image_strategy_returns_mode_specific_style_guidance() -> None:
    strategy = GptImagePromptStrategy()

    random_mix_guidance = strategy.get_style_strategy(PROMPT_ART_STYLE_MODE_RANDOM_MIX)
    single_style_guidance = strategy.get_style_strategy(
        PROMPT_ART_STYLE_MODE_SINGLE_STYLE
    )

    assert "pick unique candidates for each variant" in random_mix_guidance
    assert "Use the fixed art style for every variant" in single_style_guidance
    assert "pick unique candidates for each variant" not in single_style_guidance


def test_gpt_image_strategy_creative_guidance_preserves_style_anchoring() -> None:
    strategy = GptImagePromptStrategy()

    guidance = strategy.get_creative_guidance()
    random_mix_guidance = strategy.get_style_strategy(PROMPT_ART_STYLE_MODE_RANDOM_MIX)

    assert "clear central subject" in guidance
    assert "composition, perspective, palette" in guidance
    assert (
        "Explicitly weave the chosen medium or art era into prompt_text and style_tags"
        in random_mix_guidance
    )


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_build_scene_context_paragraph_numbering(
    db: Session,
    scene_factory,
) -> None:
    """Context builder should return scene span in paragraph_span and only
    include context paragraphs OUTSIDE the scene span in context_text."""
    scene = scene_factory(
        book_slug="excession",
        source_book_path=str(EXCESSION_EPUB),
        chapter_number=1,
        chapter_title="Chapter 1",
        scene_paragraph_start=5,
        scene_paragraph_end=8,
        chunk_paragraph_start=5,
        chunk_paragraph_end=8,
    )

    service = ImagePromptGenerationService(db)
    config = ImagePromptGenerationConfig()
    config.context_before = 3
    config.context_after = 1

    context_window, context_text = service._context_builder.build_scene_context(
        scene=scene,
        config=config,
    )

    # paragraph_span should be the scene span, not including context
    assert context_window["paragraph_span"] == [
        scene.scene_paragraph_start,
        scene.scene_paragraph_end,
    ]

    # context_before_span should be paragraphs before scene start
    expected_before_start = max(1, scene.scene_paragraph_start - config.context_before)
    expected_before_end = scene.scene_paragraph_start - 1
    assert context_window["context_before_span"] == [
        expected_before_start,
        expected_before_end,
    ]

    # context_after_span should be paragraphs after scene end
    cached_chapters = service._context_builder._book_cache[scene.source_book_path]
    total_paragraphs = len(cached_chapters[scene.chapter_number].paragraphs)
    expected_after_start = scene.scene_paragraph_end + 1
    expected_after_end = min(
        total_paragraphs,
        scene.scene_paragraph_end + config.context_after,
    )
    assert context_window["context_after_span"] == [
        expected_after_start,
        expected_after_end,
    ]

    # context_text should have section headers and only context paragraphs
    assert "### Context Before Scene" in context_text
    assert "### Context After Scene" in context_text
    assert f"[Paragraph {expected_before_start}]" in context_text
    assert f"[Paragraph {expected_after_end}]" in context_text
    # Scene paragraphs should NOT be in context text (they're in the scene excerpt)
    for para_num in range(scene.scene_paragraph_start, scene.scene_paragraph_end + 1):
        assert f"[Paragraph {para_num}]" not in context_text


@pytest.mark.skipif(not EXCESSION_EPUB.exists(), reason="Test EPUB not available")
def test_build_scene_context_clamps_stale_scene_paragraph_span(
    db: Session,
    scene_factory,
) -> None:
    scene = scene_factory(
        book_slug="excession",
        source_book_path=str(EXCESSION_EPUB),
        chapter_number=80,
        chapter_title="VII",
        scene_paragraph_start=13,
        scene_paragraph_end=13,
        chunk_paragraph_start=1,
        chunk_paragraph_end=45,
    )

    service = ImagePromptGenerationService(db)
    config = ImagePromptGenerationConfig()

    context_window, context_text = service._context_builder.build_scene_context(
        scene=scene,
        config=config,
    )

    cached_chapters = service._context_builder._book_cache[scene.source_book_path]
    total_paragraphs = len(cached_chapters[scene.chapter_number].paragraphs)

    assert total_paragraphs == 11
    assert context_window["paragraph_span"] == [11, 11]
    assert context_window["requested_paragraph_span"] == [13, 13]
    assert context_window["context_before_span"] == [8, 10]
    assert context_window["context_after_span"] is None
    assert "[Paragraph 10]" in context_text
