import uuid

import pytest
from sqlalchemy import delete
from sqlmodel import Session

from app.repositories import ImagePromptRepository, SceneExtractionRepository
from models.image_prompt import ImagePrompt


@pytest.fixture()
def scene(db: Session) -> object:
    repository = SceneExtractionRepository(db)
    book_slug = f"test-book-{uuid.uuid4()}"
    scene = repository.create(
        data={
            "book_slug": book_slug,
            "source_book_path": "documents/test.epub",
            "chapter_number": 1,
            "chapter_title": "Chapter 1",
            "chapter_source_name": "Test",
            "scene_number": 1,
            "location_marker": f"{book_slug}-chapter-1-scene-1",
            "raw": "A hero steps onto a neon-lit promenade.",
            "refined": "A hero steps onto a neon-lit promenade buzzing with drones.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 2,
            "raw_word_count": 12,
            "raw_char_count": 64,
            "refined_word_count": 14,
            "refined_char_count": 78,
            "scene_paragraph_start": 4,
            "scene_paragraph_end": 6,
            "scene_word_start": 10,
            "scene_word_end": 48,
            "extraction_model": "unit-test",
            "refinement_model": "unit-test",
        },
        commit=True,
    )
    yield scene
    db.execute(delete(ImagePrompt).where(ImagePrompt.scene_extraction_id == scene.id))
    db.delete(scene)
    db.commit()


def _prompt_payload(
    scene,
    *,
    variant_index: int,
    model_name: str = "gemini-2.5-flash",
    prompt_version: str = "image-prompts-v1",
    title: str | None = None,
    style_tags: list[str] | None = None,
) -> dict:
    return {
        "scene_extraction_id": scene.id,
        "model_vendor": "google",
        "model_name": model_name,
        "prompt_version": prompt_version,
        "variant_index": variant_index,
        "title": title or f"Variant {variant_index}",
        "prompt_text": f"Prompt text {variant_index}",
        "negative_prompt": None,
        "style_tags": style_tags,
        "attributes": {
            "composition": "dynamic",
            "camera": "35mm",
        },
        "notes": None,
        "context_window": {
            "chapter_number": scene.chapter_number,
            "paragraph_span": [
                scene.scene_paragraph_start or 0,
                scene.scene_paragraph_end or 0,
            ],
            "paragraphs_before": 3,
            "paragraphs_after": 1,
        },
        "raw_response": {
            "variants": [],
        },
        "temperature": 0.4,
        "max_output_tokens": 4096,
        "llm_request_id": f"req-{uuid.uuid4()}",
        "execution_time_ms": 1200 + variant_index,
    }


def test_create_and_get_image_prompt(db: Session, scene) -> None:
    repository = ImagePromptRepository(db)
    created = repository.create(
        data=_prompt_payload(scene, variant_index=0), commit=True
    )

    fetched = repository.get(created.id)
    assert fetched is not None
    assert fetched.prompt_text == "Prompt text 0"
    assert fetched.context_window["paragraphs_before"] == 3

    repository.delete_for_scene(scene.id, commit=True)


def test_list_for_scene_orders_by_created_at(db: Session, scene) -> None:
    repository = ImagePromptRepository(db)
    repository.create(data=_prompt_payload(scene, variant_index=0), commit=True)
    repository.create(data=_prompt_payload(scene, variant_index=1), commit=True)

    newest_first = repository.list_for_scene(scene.id)
    assert [prompt.variant_index for prompt in newest_first] == [1, 0]

    oldest_first = repository.list_for_scene(scene.id, newest_first=False)
    assert [prompt.variant_index for prompt in oldest_first] == [0, 1]

    filtered = repository.list_for_scene(
        scene.id, model_name="gemini-2.5-flash", prompt_version="image-prompts-v1"
    )
    assert len(filtered) == 2

    repository.delete_for_scene(scene.id, commit=True)


def test_get_latest_set_for_scene_returns_variants_sorted(db: Session, scene) -> None:
    repository = ImagePromptRepository(db)
    repository.bulk_create(
        [
            _prompt_payload(scene, variant_index=0),
            _prompt_payload(scene, variant_index=1),
            _prompt_payload(scene, variant_index=2),
        ],
        commit=True,
    )

    latest = repository.get_latest_set_for_scene(
        scene.id, model_name="gemini-2.5-flash", prompt_version="image-prompts-v1"
    )
    assert [prompt.variant_index for prompt in latest] == [0, 1, 2]

    repository.delete_for_scene(scene.id, commit=True)


def test_list_for_book_filters(db: Session) -> None:
    scene_repo = SceneExtractionRepository(db)
    repository = ImagePromptRepository(db)
    book_slug = f"gallery-book-{uuid.uuid4()}"

    scene_one = scene_repo.create(
        data={
            "book_slug": book_slug,
            "source_book_path": "documents/test.epub",
            "chapter_number": 1,
            "chapter_title": "Chapter 1",
            "chapter_source_name": "Test",
            "scene_number": 1,
            "location_marker": f"{book_slug}-chapter-1-scene-1",
            "raw": "Explorers enter an ancient ruin.",
            "refined": "Explorers enter an ancient ruin lit by bioluminescent vines.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 2,
            "raw_word_count": 10,
            "raw_char_count": 55,
            "refined_word_count": 12,
            "refined_char_count": 70,
            "scene_paragraph_start": 3,
            "scene_paragraph_end": 5,
            "scene_word_start": 5,
            "scene_word_end": 35,
            "extraction_model": "unit-test",
            "refinement_model": "unit-test",
        },
        commit=True,
    )
    scene_two = scene_repo.create(
        data={
            "book_slug": book_slug,
            "source_book_path": "documents/test.epub",
            "chapter_number": 2,
            "chapter_title": "Chapter 2",
            "chapter_source_name": "Test",
            "scene_number": 1,
            "location_marker": f"{book_slug}-chapter-2-scene-1",
            "raw": "Pilots prep a starfighter.",
            "refined": "Pilots prep a starfighter beneath a glass-domed hangar.",
            "chunk_index": 0,
            "chunk_paragraph_start": 1,
            "chunk_paragraph_end": 2,
            "raw_word_count": 8,
            "raw_char_count": 44,
            "refined_word_count": 11,
            "refined_char_count": 68,
            "scene_paragraph_start": 6,
            "scene_paragraph_end": 7,
            "scene_word_start": 3,
            "scene_word_end": 28,
            "extraction_model": "unit-test",
            "refinement_model": "unit-test",
        },
        commit=True,
    )

    repository.bulk_create(
        [
            _prompt_payload(
                scene_one, variant_index=0, style_tags=["neon", "cinematic"]
            ),
            _prompt_payload(scene_two, variant_index=0, style_tags=["moody", "noir"]),
        ],
        commit=True,
    )

    neon_prompts = repository.list_for_book(
        book_slug=book_slug, style_tag="neon", include_scene=True
    )
    assert len(neon_prompts) == 1
    assert neon_prompts[0].scene_extraction_id == scene_one.id
    assert neon_prompts[0].scene_extraction is not None

    chapter_two_prompts = repository.list_for_book(
        book_slug=book_slug, chapter_number=2
    )
    assert {prompt.scene_extraction_id for prompt in chapter_two_prompts} == {
        scene_two.id
    }

    repository.delete_for_scene(scene_one.id, commit=True)
    repository.delete_for_scene(scene_two.id, commit=True)
    db.delete(scene_one)
    db.delete(scene_two)
    db.commit()


def test_delete_for_scene_removes_prompts(db: Session, scene) -> None:
    repository = ImagePromptRepository(db)
    repository.bulk_create(
        [
            _prompt_payload(scene, variant_index=0),
            _prompt_payload(scene, variant_index=1),
        ],
        commit=True,
    )

    deleted = repository.delete_for_scene(
        scene.id, prompt_version="image-prompts-v1", commit=True
    )
    assert deleted == 2
    assert repository.list_for_scene(scene.id) == []
