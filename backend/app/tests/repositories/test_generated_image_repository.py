"""Tests for GeneratedImageRepository file-deletion tracking methods."""

from __future__ import annotations

from collections.abc import Callable

from sqlmodel import Session

from app.repositories import GeneratedImageRepository
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction


def _image_payload(
    scene: SceneExtraction, prompt: ImagePrompt, **overrides: object
) -> dict:
    data: dict[str, object] = {
        "scene_extraction_id": scene.id,
        "image_prompt_id": prompt.id,
        "book_slug": scene.book_slug,
        "chapter_number": scene.chapter_number,
        "variant_index": 0,
        "provider": "openai",
        "model": "dall-e-3",
        "size": "1024x1024",
        "quality": "standard",
        "style": "vivid",
        "response_format": "b64_json",
        "storage_path": "img/generated/test",
        "file_name": "test.png",
    }
    data.update(overrides)
    return data


def test_mark_file_deleted(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repo = GeneratedImageRepository(db)
    image = repo.create(data=_image_payload(scene, prompt), commit=True)

    assert image.file_deleted is False
    assert image.file_deleted_at is None

    updated = repo.mark_file_deleted(image.id, commit=True)
    assert updated is not None
    assert updated.file_deleted is True
    assert updated.file_deleted_at is not None


def test_mark_file_deleted_nonexistent(db: Session) -> None:
    from uuid import uuid4

    repo = GeneratedImageRepository(db)
    result = repo.mark_file_deleted(uuid4(), commit=True)
    assert result is None


def test_bulk_mark_files_deleted(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repo = GeneratedImageRepository(db)

    img1 = repo.create(
        data=_image_payload(scene, prompt, variant_index=0),
        commit=True,
    )
    img2 = repo.create(
        data=_image_payload(scene, prompt, variant_index=1),
        commit=True,
    )

    count = repo.bulk_mark_files_deleted([img1.id, img2.id], commit=True)
    assert count == 2

    db.refresh(img1)
    db.refresh(img2)
    assert img1.file_deleted is True
    assert img1.file_deleted_at is not None
    assert img2.file_deleted is True
    assert img2.file_deleted_at is not None


def test_bulk_mark_files_deleted_empty(db: Session) -> None:
    repo = GeneratedImageRepository(db)
    count = repo.bulk_mark_files_deleted([], commit=True)
    assert count == 0


def test_list_non_approved_with_files(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repo = GeneratedImageRepository(db)

    # Approved image - should NOT appear
    approved = repo.create(
        data=_image_payload(scene, prompt, variant_index=0),
        commit=True,
    )
    repo.update_approval(approved.id, True, commit=True)

    # Rejected image - should appear
    rejected = repo.create(
        data=_image_payload(scene, prompt, variant_index=1),
        commit=True,
    )
    repo.update_approval(rejected.id, False, commit=True)

    # Unapproved (None) image - should appear
    unapproved = repo.create(
        data=_image_payload(scene, prompt, variant_index=2),
        commit=True,
    )

    # Already file-deleted image - should NOT appear
    already_deleted = repo.create(
        data=_image_payload(scene, prompt, variant_index=3),
        commit=True,
    )
    repo.mark_file_deleted(already_deleted.id, commit=True)

    results = repo.list_non_approved_with_files(book_slug=scene.book_slug)
    result_ids = {r.id for r in results}

    assert rejected.id in result_ids
    assert unapproved.id in result_ids
    assert approved.id not in result_ids
    assert already_deleted.id not in result_ids


def test_list_non_approved_with_files_book_filter(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene_a = scene_factory(book_slug="test-book-cleanup-a")
    prompt_a = prompt_factory(scene_a)
    scene_b = scene_factory(book_slug="test-book-cleanup-b")
    prompt_b = prompt_factory(scene_b)
    repo = GeneratedImageRepository(db)

    img_a = repo.create(data=_image_payload(scene_a, prompt_a), commit=True)
    img_b = repo.create(data=_image_payload(scene_b, prompt_b), commit=True)

    results_a = repo.list_non_approved_with_files(book_slug="test-book-cleanup-a")
    result_ids_a = {r.id for r in results_a}
    assert img_a.id in result_ids_a
    assert img_b.id not in result_ids_a


def test_list_methods_exclude_file_deleted_by_default(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repo = GeneratedImageRepository(db)

    active = repo.create(
        data=_image_payload(scene, prompt, variant_index=0),
        commit=True,
    )
    deleted = repo.create(
        data=_image_payload(scene, prompt, variant_index=1),
        commit=True,
    )
    repo.mark_file_deleted(deleted.id, commit=True)

    scene_ids = {img.id for img in repo.list_for_scene(scene.id)}
    prompt_ids = {img.id for img in repo.list_for_prompt(prompt.id)}
    book_ids = {img.id for img in repo.list_for_book(scene.book_slug)}
    all_ids = {img.id for img in repo.list_all()}

    assert active.id in scene_ids
    assert active.id in prompt_ids
    assert active.id in book_ids
    assert active.id in all_ids
    assert deleted.id not in scene_ids
    assert deleted.id not in prompt_ids
    assert deleted.id not in book_ids
    assert deleted.id not in all_ids


def test_list_for_scene_can_include_file_deleted(
    db: Session,
    scene_factory: Callable[..., SceneExtraction],
    prompt_factory: Callable[..., ImagePrompt],
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repo = GeneratedImageRepository(db)

    image = repo.create(
        data=_image_payload(scene, prompt),
        commit=True,
    )
    repo.mark_file_deleted(image.id, commit=True)

    excluded = repo.list_for_scene(scene.id)
    included = repo.list_for_scene(scene.id, include_file_deleted=True)

    assert excluded == []
    assert len(included) == 1
    assert included[0].id == image.id
