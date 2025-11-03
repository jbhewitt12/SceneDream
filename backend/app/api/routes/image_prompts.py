"""API routes for viewing image prompts."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.repositories import ImagePromptRepository, SceneExtractionRepository
from app.schemas import (
    ImagePromptListResponse,
    ImagePromptRead,
    ImagePromptSceneSummary,
    MetadataGenerationRequest,
    MetadataGenerationResponse,
    MetadataUpdateRequest,
    MetadataVariant,
)
from app.services.prompt_metadata.prompt_metadata_service import (
    PromptMetadataGenerationService,
    PromptMetadataGenerationServiceError,
)


router = APIRouter(prefix="/image-prompts", tags=["image-prompts"])
logger = logging.getLogger(__name__)

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
        include_scene=include_scene,
    )
    data = [
        _serialize_prompt(record, include_scene=include_scene) for record in prompts
    ]
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
    data = [
        _serialize_prompt(record, include_scene=include_scene) for record in prompts
    ]
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


@router.post("/{prompt_id}/metadata/generate", response_model=MetadataGenerationResponse)
async def generate_metadata_variants(
    *,
    session: SessionDep,
    prompt_id: UUID,
    request: MetadataGenerationRequest | None = None,
) -> MetadataGenerationResponse:
    """Generate multiple metadata variants for an image prompt without persisting them."""

    request = request or MetadataGenerationRequest()
    repository = ImagePromptRepository(session)
    prompt = repository.get(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Image prompt not found")

    service = PromptMetadataGenerationService(session)
    try:
        variants = await service.generate_metadata_variants(
            prompt,
            variants_count=request.variants_count,
        )
    except PromptMetadataGenerationServiceError as exc:
        logger.exception(
            "Failed to generate metadata variants for prompt %s", prompt_id
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate metadata variants",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error generating metadata variants for prompt %s", prompt_id
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate metadata variants",
        ) from exc

    return MetadataGenerationResponse(
        prompt_id=prompt_id,
        variants=[MetadataVariant(**variant) for variant in variants],
        count=len(variants),
    )


@router.patch("/{prompt_id}/metadata", response_model=ImagePromptRead)
async def update_prompt_metadata(
    *,
    session: SessionDep,
    prompt_id: UUID,
    update: MetadataUpdateRequest,
) -> ImagePromptRead:
    """Update stored metadata for an image prompt."""

    if update.title is None and update.flavour_text is None:
        raise HTTPException(
            status_code=422,
            detail="At least one metadata field must be provided",
        )

    repository = ImagePromptRepository(session)
    prompt = repository.update_metadata(
        prompt_id,
        title=update.title,
        flavour_text=update.flavour_text,
        commit=True,
    )
    if prompt is None:
        raise HTTPException(status_code=404, detail="Image prompt not found")

    return ImagePromptRead.model_validate(prompt)
