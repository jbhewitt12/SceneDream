import asyncio
import random
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories import ImagePromptRepository
from app.services.image_prompt_generation import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
    ImagePromptPreview,
)
from app.services.langchain import gemini_api, openai_api
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

EXCESSION_EPUB = (
    Path(__file__).resolve().parents[4]
    / "books"
    / "Iain Banks"
    / "Excession"
    / "Excession - Iain M. Banks.epub"
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
    repository = ImagePromptRepository(db)
    assert repository.list_for_scene(scene.id) == []


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
                "raw_response": {"response": []},
                "temperature": 0.4,
                "max_output_tokens": 8192,
                "llm_request_id": None,
                "execution_time_ms": 100,
            }
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


def test_generate_for_scene_overwrites_when_allowed(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    assert len(results) == 2
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    assert all(
        prompt.title in {"Neon Watchtower", "Garden Overwatch"} for prompt in stored
    )

    repository.delete_for_scene(scene.id, commit=True)


def test_sample_styles_respects_formula(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
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


def test_sample_styles_filters_blocked_terms(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    from app.services.image_prompt_generation.core.style_sampler import StyleSampler

    # Create a custom StyleSampler with test styles including blocked terms
    test_sampler = StyleSampler(
        recommended_styles=("Stylised", "Photorealistic ink", "Shared"),
        other_styles=("Shared", "live-action still", "Safe Option"),
    )
    monkeypatch.setattr(random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(random, "shuffle", lambda seq: None)

    styles = test_sampler.sample(variants_count=2)

    # "Photorealistic ink" and "live-action still" should be filtered
    assert "Photorealistic ink" not in styles
    assert "live-action still" not in styles
    assert "Stylised" in styles


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
        recommended_styles=("Style A", "Style B", "Style C", "Style D", "Style E", "Style F"),
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
    for style in sampled_styles:
        assert style in prompt


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
