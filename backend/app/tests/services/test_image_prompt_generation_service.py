import asyncio
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories import ImagePromptRepository, SceneExtractionRepository
import app.services.image_prompt_generation.image_prompt_generation_service as service_module
from app.services.image_prompt_generation import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptGenerationServiceError,
    ImagePromptPreview,
)
from app.services.langchain import openai_api
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
    async def _fake_generate(self, prompts, *, dry_run=False, **kwargs):  # type: ignore[no-untyped-def]
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
                setattr(prompt, "title", title)
                setattr(prompt, "flavour_text", flavour)
                results.append(prompt)
        return results

    monkeypatch.setattr(
        "app.services.prompt_metadata.prompt_metadata_service.PromptMetadataGenerationService.generate_metadata_for_prompts",
        _fake_generate,
    )


@pytest.fixture()
def scene_factory(db: Session) -> Callable[..., SceneExtraction]:
    created = []

    def _create(**overrides: object) -> SceneExtraction:
        repository = SceneExtractionRepository(db)
        counter = len(created) + 1
        data: dict[str, object] = {
            "book_slug": f"test-book-{uuid4()}",
            "source_book_path": "books/test.epub",
            "chapter_number": 1,
            "chapter_title": "Chapter 1",
            "chapter_source_name": "Test",
            "scene_number": counter,
            "location_marker": f"chapter-1-scene-{counter}",
            "raw": "A scout surveys a neon city skyline from a rooftop garden.",
            "refined": "A lone scout surveys a neon skyline from a windswept rooftop garden.",
            "chunk_index": 0,
            "chunk_paragraph_start": 4,
            "chunk_paragraph_end": 6,
            "raw_word_count": 12,
            "raw_char_count": 72,
            "refined_word_count": 15,
            "refined_char_count": 92,
            "scene_paragraph_start": 5,
            "scene_paragraph_end": 6,
            "scene_word_start": 10,
            "scene_word_end": 52,
            "extraction_model": "unit-test",
            "refinement_model": "unit-test",
        }
        data.update(overrides)
        scene = repository.create(data=data, commit=True)
        created.append(scene)
        return scene

    yield _create

    image_prompt_repo = ImagePromptRepository(db)
    for scene in created:
        image_prompt_repo.delete_for_scene(scene.id, commit=False)
        db.delete(scene)
    db.commit()


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
        service,
        "_load_cheatsheet_text",
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
    scene = scene_factory()
    config = ImagePromptGenerationConfig(variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    captured_prompt: dict[str, str] = {}
    monkeypatch.setattr(
        service_module.random, "sample", lambda seq, k: list(seq)[:k]
    )
    monkeypatch.setattr(service_module.random, "shuffle", lambda seq: None)

    async def fake_json_output(**kwargs: object) -> list[dict[str, object]]:
        captured_prompt["prompt"] = kwargs.get("prompt", "")  # type: ignore[arg-type]
        return _variants()

    monkeypatch.setattr(openai_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert len(results) == 2
    assert captured_prompt["prompt"].startswith("You are an elite prompt engineer")

    repository = ImagePromptRepository(db)
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    first = stored[0]
    assert first.context_window["paragraph_span"] == [2, 6]
    assert "prompt" not in first.raw_response
    assert first.raw_response["service"]["prompt_hash"]
    assert first.raw_response["service"]["sampled_styles"] == [
        "90's anime",
        "Ukiyo-e woodblock",
        "stained glass mosaic",
        "Art Nouveau",
        "Abstract art",
    ]

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

    monkeypatch.setattr(openai_api, "json_output", fake_json_output)

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

    monkeypatch.setattr(openai_api, "json_output", fail_json_output)

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

    monkeypatch.setattr(openai_api, "json_output", fake_json_output)

    results = asyncio.run(service.generate_for_scene(scene))

    assert len(results) == 2
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    assert all(
        prompt.title in {"Neon Watchtower", "Garden Overwatch"} for prompt in stored
    )

    repository.delete_for_scene(scene.id, commit=True)


def test_sample_styles_respects_formula(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    service = ImagePromptGenerationService(db)
    monkeypatch.setattr(
        service_module,
        "RECOMMENDED_STYLES",
        ("A", "B", "C", "D", "E"),
    )
    monkeypatch.setattr(service_module, "OTHER_STYLES", ("X", "Y", "Z"))
    monkeypatch.setattr(service_module.random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(service_module.random, "shuffle", lambda seq: None)

    styles = service._sample_styles(variants_count=4)

    assert styles == ["A", "B", "C", "D", "E", "X", "Y"]


def test_sample_styles_filters_blocked_terms(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    service = ImagePromptGenerationService(db)
    monkeypatch.setattr(
        service_module,
        "RECOMMENDED_STYLES",
        ("Stylised", "Photorealistic ink", "Shared"),
    )
    monkeypatch.setattr(
        service_module,
        "OTHER_STYLES",
        ("Shared", "live-action still", "Safe Option"),
    )
    monkeypatch.setattr(service_module.random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(service_module.random, "shuffle", lambda seq: None)

    styles = service._sample_styles(variants_count=2)

    assert styles == ["Stylised", "Shared"]


def test_render_prompt_template_includes_suggested_styles(
    db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(variants_count=4)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(
        service_module,
        "RECOMMENDED_STYLES",
        ("Style A", "Style B", "Style C", "Style D", "Style E", "Style F"),
    )
    monkeypatch.setattr(
        service_module,
        "OTHER_STYLES",
        ("Other A", "Other B", "Other C"),
    )
    monkeypatch.setattr(service_module.random, "sample", lambda seq, k: list(seq)[:k])
    monkeypatch.setattr(service_module.random, "shuffle", lambda seq: None)

    prompt, resolved_config, _, _, sampled_styles = service.render_prompt_template(scene)

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

    expected_start = max(1, scene.scene_paragraph_start - config.context_before)
    cached_chapters = service._context_builder._book_cache[scene.source_book_path]
    total_paragraphs = len(cached_chapters[scene.chapter_number].paragraphs)
    expected_end = min(
        total_paragraphs,
        scene.scene_paragraph_end + config.context_after,
    )

    assert context_window["paragraph_span"] == [expected_start, expected_end]
    lines = context_text.splitlines()
    assert lines
    assert lines[0].startswith(f"[Paragraph {expected_start}]")
    assert lines[-1].startswith(f"[Paragraph {expected_end}]")
    assert len(lines) == expected_end - expected_start + 1
