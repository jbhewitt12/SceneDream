from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

from app.repositories import AppSettingsRepository, GeneratedImageRepository
from app.services.social_posting.exceptions import SocialPostingDisabledError
from app.services.social_posting.repository import SocialMediaPostRepository
from app.services.social_posting.social_posting_service import SocialPostingService


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _set_social_posting_enabled(db: Session, enabled: bool) -> bool:
    repository = AppSettingsRepository(db)
    settings = repository.get_or_create_global(commit=True, refresh=True)
    previous = settings.social_posting_enabled
    repository.update(
        settings,
        data={"social_posting_enabled": enabled},
        commit=True,
        refresh=True,
    )
    return previous


def _create_generated_image(db: Session, scene_factory, prompt_factory):
    scene = scene_factory()
    prompt = prompt_factory(scene)
    repository = GeneratedImageRepository(db)
    return repository.create(
        data={
            "scene_extraction_id": scene.id,
            "image_prompt_id": prompt.id,
            "book_slug": scene.book_slug,
            "chapter_number": scene.chapter_number,
            "variant_index": 0,
            "provider": "openai",
            "model": "gpt-image-1",
            "size": "1024x1024",
            "quality": "high",
            "style": "vivid",
            "response_format": "b64_json",
            "storage_path": "img/generated/test",
            "file_name": f"{scene.id}.png",
            "user_approved": True,
        },
        commit=True,
        refresh=True,
    )


def test_queue_image_raises_when_social_posting_disabled(
    db: Session,
    scene_factory,
    prompt_factory,
) -> None:
    image = _create_generated_image(db, scene_factory, prompt_factory)
    previous = _set_social_posting_enabled(db, False)
    service = SocialPostingService(db)

    try:
        with pytest.raises(
            SocialPostingDisabledError, match="Social media posting is disabled"
        ):
            service.queue_image(image.id)
    finally:
        _set_social_posting_enabled(db, previous)


@pytest.mark.anyio("asyncio")
async def test_process_queue_noops_when_social_posting_disabled(
    db: Session,
    scene_factory,
    prompt_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _create_generated_image(db, scene_factory, prompt_factory)
    post = SocialMediaPostRepository(db).create(
        data={
            "generated_image_id": image.id,
            "service_name": "x",
            "status": "queued",
        },
        commit=True,
        refresh=True,
    )
    previous = _set_social_posting_enabled(db, False)
    service = SocialPostingService(db)
    post_mock = AsyncMock()

    monkeypatch.setattr(service, "_post_to_service", post_mock)
    monkeypatch.setattr(
        SocialPostingService,
        "get_enabled_services",
        staticmethod(lambda: ["x"]),
    )

    try:
        result = await service.process_queue()
        assert result is None
        post_mock.assert_not_awaited()
    finally:
        db.delete(post)
        db.commit()
        _set_social_posting_enabled(db, previous)


def test_retry_failed_raises_when_social_posting_disabled(db: Session) -> None:
    previous = _set_social_posting_enabled(db, False)
    service = SocialPostingService(db)

    try:
        with pytest.raises(
            SocialPostingDisabledError, match="Social media posting is disabled"
        ):
            service.retry_failed()
    finally:
        _set_social_posting_enabled(db, previous)
