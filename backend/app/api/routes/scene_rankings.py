"""API routes for viewing scene ranking results."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.repositories import SceneExtractionRepository, SceneRankingRepository
from app.schemas import (
    SceneRankingListResponse,
    SceneRankingRead,
    SceneRankingSceneSummary,
)

router = APIRouter(prefix="/scene-rankings", tags=["scene-rankings"])

_DEFAULT_TOP_LIMIT = 10
_MAX_TOP_LIMIT = 100
_DEFAULT_HISTORY_LIMIT = 20
_MAX_HISTORY_LIMIT = 100


def _serialize_ranking(
    record,
    *,
    include_scene: bool,
) -> SceneRankingRead:
    item = SceneRankingRead.model_validate(record)
    if include_scene and getattr(record, "scene_extraction", None) is not None:
        item = item.model_copy(
            update={
                "scene": SceneRankingSceneSummary.model_validate(record.scene_extraction)
            }
        )
    return item


@router.get("/top", response_model=SceneRankingListResponse)
def list_top_scene_rankings(
    *,
    session: SessionDep,
    book_slug: str = Query(..., min_length=1),
    limit: int = Query(_DEFAULT_TOP_LIMIT, ge=1, le=_MAX_TOP_LIMIT),
    model_name: str | None = Query(None, min_length=1),
    prompt_version: str | None = Query(None, min_length=1),
    weight_config_hash: str | None = Query(None, min_length=1),
    include_scene: bool = Query(False),
) -> SceneRankingListResponse:
    """Return the highest ranked scenes for a book with optional filters."""

    repository = SceneRankingRepository(session)
    rankings = repository.list_top_rankings_for_book(
        book_slug=book_slug,
        limit=limit,
        model_name=model_name,
        prompt_version=prompt_version,
        weight_config_hash=weight_config_hash,
        include_scene=include_scene,
    )
    data = [_serialize_ranking(record, include_scene=include_scene) for record in rankings]
    meta: dict[str, object] = {
        "book_slug": book_slug,
        "limit": limit,
        "count": len(data),
    }
    if model_name:
        meta["model_name"] = model_name
    if prompt_version:
        meta["prompt_version"] = prompt_version
    if weight_config_hash:
        meta["weight_config_hash"] = weight_config_hash
    return SceneRankingListResponse(data=data, meta=meta)


@router.get("/scene/{scene_id}", response_model=SceneRankingListResponse)
def list_scene_ranking_history(
    *,
    session: SessionDep,
    scene_id: UUID,
    limit: int = Query(_DEFAULT_HISTORY_LIMIT, ge=1, le=_MAX_HISTORY_LIMIT),
    newest_first: bool = Query(True),
    include_scene: bool = Query(True),
) -> SceneRankingListResponse:
    """Return ranking history for a specific scene."""

    extraction_repository = SceneExtractionRepository(session)
    scene = extraction_repository.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")

    ranking_repository = SceneRankingRepository(session)
    rankings = ranking_repository.list_for_scene(
        scene_id,
        limit=limit,
        newest_first=newest_first,
    )
    data = [_serialize_ranking(record, include_scene=include_scene) for record in rankings]
    meta: dict[str, object] = {
        "scene_extraction_id": str(scene_id),
        "count": len(data),
        "newest_first": newest_first,
    }
    if include_scene:
        meta["scene"] = SceneRankingSceneSummary.model_validate(scene).model_dump()
    return SceneRankingListResponse(data=data, meta=meta)


@router.get("/{ranking_id}", response_model=SceneRankingRead)
def get_scene_ranking(
    *,
    session: SessionDep,
    ranking_id: UUID,
    include_scene: bool = Query(False),
) -> SceneRankingRead:
    """Fetch a single scene ranking by identifier."""

    repository = SceneRankingRepository(session)
    ranking = repository.get(ranking_id)
    if ranking is None:
        raise HTTPException(status_code=404, detail="Scene ranking not found")
    include_scene = bool(include_scene)
    return _serialize_ranking(ranking, include_scene=include_scene)

