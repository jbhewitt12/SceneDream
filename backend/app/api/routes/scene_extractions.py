"""API routes for viewing scene extraction results."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.repositories import SceneExtractionRepository
from app.schemas import (
    SceneExtractionFilterOptions,
    SceneExtractionListResponse,
    SceneExtractionRead,
)

router = APIRouter(prefix="/scene-extractions", tags=["scene-extractions"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get("/", response_model=SceneExtractionListResponse)
def list_scene_extractions(
    *,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    book_slug: str | None = Query(None),
    chapter_number: int | None = Query(None, ge=0),
    decision: str | None = Query(None),
    has_refined: bool | None = Query(None),
    search: str | None = Query(None, min_length=1),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    order: Literal["asc", "desc"] = Query("desc"),
) -> SceneExtractionListResponse:
    """Return a paginated list of scene extractions with optional filters."""

    repository = SceneExtractionRepository(session)
    records, total = repository.search(
        page=page,
        page_size=page_size,
        book_slug=book_slug,
        chapter_number=chapter_number,
        decision=decision,
        has_refined=has_refined,
        search_term=search,
        start_date=start_date,
        end_date=end_date,
        order=order,
    )

    data = [SceneExtractionRead.model_validate(record) for record in records]

    return SceneExtractionListResponse(
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/filters", response_model=SceneExtractionFilterOptions)
def get_filter_options(
    *, session: SessionDep
) -> SceneExtractionFilterOptions:
    """Expose the available filter options for scene extractions."""

    repository = SceneExtractionRepository(session)
    options = repository.filter_options()
    return SceneExtractionFilterOptions.model_validate(options)


@router.get("/{scene_id}", response_model=SceneExtractionRead)
def get_scene_extraction(
    *, session: SessionDep, scene_id: UUID
) -> SceneExtractionRead:
    """Fetch a single scene extraction by its identifier."""

    repository = SceneExtractionRepository(session)
    record = repository.get(scene_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scene extraction not found")
    return SceneExtractionRead.model_validate(record)
