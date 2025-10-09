"""API routes for viewing image prompts."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.repositories import ImagePromptRepository, SceneExtractionRepository
from app.schemas import (
    ImagePromptListResponse,
    ImagePromptRead,
    ImagePromptSceneSummary,
)


router = APIRouter(prefix="/image-prompts", tags=["image-prompts"])

_DEFAULT_HISTORY_LIMIT = 20
_MAX_HISTORY_LIMIT = 100
_DEFAULT_BOOK_LIMIT = 24
_MAX_BOOK_LIMIT = 200


def _serialize_prompt(record, *, include_scene: bool) -> ImagePromptRead:
    item = ImagePromptRead.model_validate(record)
    if include_scene and getattr(record, "scene_extraction", None) is not None:
        item = item.model_copy(
            update={
                "scene": ImagePromptSceneSummary.model_validate(record.scene_extraction)
            }
        )
    return item


@router.get("/scene/{scene_id}", response_model=ImagePromptListResponse)
def list_prompts_for_scene(
    *,
    session: SessionDep,
    scene_id: UUID,
    limit: int = Query(_DEFAULT_HISTORY_LIMIT, ge=1, le=_MAX_HISTORY_LIMIT),
    newest_first: bool = Query(True),
    model_name: str | None = Query(None, min_length=1),
    prompt_version: str | None = Query(None, min_length=1),
    include_scene: bool = Query(False),
) -> ImagePromptListResponse:
    """Return image prompts for a specific scene."""

    extraction_repository = SceneExtractionRepository(session)
    scene = extraction_repository.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")

    repository = ImagePromptRepository(session)
    prompts = repository.list_for_scene(
        scene_id,
        model_name=model_name,
        prompt_version=prompt_version,
        newest_first=newest_first,
        limit=limit,
    )
    data = [_serialize_prompt(record, include_scene=include_scene) for record in prompts]
    meta: dict[str, object] = {
        "scene_extraction_id": str(scene_id),
        "count": len(data),
        "newest_first": newest_first,
    }
    if include_scene:
        meta["scene"] = ImagePromptSceneSummary.model_validate(scene).model_dump()
    if model_name:
        meta["model_name"] = model_name
    if prompt_version:
        meta["prompt_version"] = prompt_version
    return ImagePromptListResponse(data=data, meta=meta)


@router.get("/book/{book_slug}", response_model=ImagePromptListResponse)
def list_prompts_for_book(
    *,
    session: SessionDep,
    book_slug: str,
    chapter_number: int | None = Query(None, ge=0),
    model_name: str | None = Query(None, min_length=1),
    prompt_version: str | None = Query(None, min_length=1),
    style_tag: str | None = Query(None, min_length=1),
    newest_first: bool = Query(True),
    limit: int = Query(_DEFAULT_BOOK_LIMIT, ge=1, le=_MAX_BOOK_LIMIT),
    offset: int | None = Query(None, ge=0),
    include_scene: bool = Query(False),
) -> ImagePromptListResponse:
    """List prompts across a book with optional filters and pagination."""

    repository = ImagePromptRepository(session)
    prompts = repository.list_for_book(
        book_slug=book_slug,
        model_name=model_name,
        prompt_version=prompt_version,
        style_tag=style_tag,
        chapter_number=chapter_number,
        newest_first=newest_first,
        limit=limit,
        offset=offset,
        include_scene=include_scene,
    )
    data = [_serialize_prompt(record, include_scene=include_scene) for record in prompts]
    meta: dict[str, object] = {
        "book_slug": book_slug,
        "count": len(data),
        "newest_first": newest_first,
        "limit": limit,
    }
    if offset is not None:
        meta["offset"] = offset
    if chapter_number is not None:
        meta["chapter_number"] = chapter_number
    if model_name:
        meta["model_name"] = model_name
    if prompt_version:
        meta["prompt_version"] = prompt_version
    if style_tag:
        meta["style_tag"] = style_tag
    return ImagePromptListResponse(data=data, meta=meta)


@router.get("/{prompt_id}", response_model=ImagePromptRead)
def get_image_prompt(
    *, session: SessionDep, prompt_id: UUID, include_scene: bool = Query(False)
) -> ImagePromptRead:
    """Fetch a single image prompt by identifier."""

    repository = ImagePromptRepository(session)
    record = repository.get(prompt_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image prompt not found")
    return _serialize_prompt(record, include_scene=bool(include_scene))


