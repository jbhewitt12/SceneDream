from collections.abc import Callable
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.repositories import ImagePromptRepository, SceneExtractionRepository
from app.services.image_prompt_generation import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationService,
    ImagePromptPreview,
)
from app.services.langchain import gemini_api


from models.scene_extraction import SceneExtraction


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


def _variants(payload: list[dict[str, object]] | None = None) -> list[dict[str, object]]:
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


def _patch_context(service: ImagePromptGenerationService, monkeypatch: pytest.MonkeyPatch) -> None:
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
        service,
        "_load_book_context",
        lambda _: {1: chapter},
    )
    monkeypatch.setattr(
        service,
        "_load_cheatsheet_text",
        lambda _p: "Cheat sheet guidance",
    )


def test_generate_for_scene_creates_prompts(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)

    captured_prompt: dict[str, str] = {}

    def fake_json_output(**kwargs: object) -> list[dict[str, object]]:
        captured_prompt["prompt"] = kwargs.get("prompt", "")  # type: ignore[arg-type]
        return _variants()

    monkeypatch.setattr(gemini_api, "json_output", fake_json_output)

    results = service.generate_for_scene(scene)

    assert len(results) == 2
    assert captured_prompt["prompt"].startswith("You are an elite prompt engineer")

    repository = ImagePromptRepository(db)
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    first = stored[0]
    assert first.context_window["paragraph_span"] == [2, 6]
    assert "prompt" not in first.raw_response
    assert first.raw_response["service"]["prompt_hash"]

    repository.delete_for_scene(scene.id, commit=True)


def test_generate_for_scene_dry_run_returns_previews(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory()
    config = ImagePromptGenerationConfig(dry_run=True, variants_count=2)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(gemini_api, "json_output", lambda **_: _variants())

    results = service.generate_for_scene(scene)

    assert all(isinstance(item, ImagePromptPreview) for item in results)
    preview = results[0]
    assert "prompt" in preview.raw_response
    repository = ImagePromptRepository(db)
    assert repository.list_for_scene(scene.id) == []


def test_generate_for_scene_returns_existing_when_overwrite_disabled(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory()
    repository = ImagePromptRepository(db)
    existing = repository.bulk_create(
        [
            {
                "scene_extraction_id": scene.id,
                "model_vendor": "google",
                "model_name": "gemini-2.5-pro",
                "prompt_version": "image-prompts-v1",
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

    config = ImagePromptGenerationConfig(variants_count=2, allow_overwrite=False)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(
        gemini_api,
        "json_output",
        lambda **_: pytest.fail("json_output should not be invoked"),
    )

    results = service.generate_for_scene(scene)

    assert results == existing
    repository.delete_for_scene(scene.id, commit=True)


def test_generate_for_scene_overwrites_when_allowed(db: Session, scene_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    scene = scene_factory()
    repository = ImagePromptRepository(db)
    repository.create(
        data={
            "scene_extraction_id": scene.id,
            "model_vendor": "google",
            "model_name": "gemini-2.5-pro",
            "prompt_version": "image-prompts-v1",
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

    config = ImagePromptGenerationConfig(variants_count=2, allow_overwrite=True)
    service = ImagePromptGenerationService(db, config=config)
    _patch_context(service, monkeypatch)
    monkeypatch.setattr(gemini_api, "json_output", lambda **_: _variants())

    results = service.generate_for_scene(scene)

    assert len(results) == 2
    stored = repository.list_for_scene(scene.id)
    assert len(stored) == 2
    assert all(prompt.title in {"Neon Watchtower", "Garden Overwatch"} for prompt in stored)

    repository.delete_for_scene(scene.id, commit=True)
