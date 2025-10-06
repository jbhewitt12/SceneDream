"""Schemas for Scene Extraction API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SceneExtractionRead(BaseModel):
    """Detailed representation of a scene extraction record."""

    id: UUID
    book_slug: str
    source_book_path: str
    chapter_number: int
    chapter_title: str
    chapter_source_name: str | None
    scene_number: int
    location_marker: str
    raw: str
    refined: str | None
    refinement_decision: str | None
    refinement_rationale: str | None
    chunk_index: int
    chunk_paragraph_start: int
    chunk_paragraph_end: int
    raw_word_count: int | None
    raw_char_count: int | None
    refined_word_count: int | None
    refined_char_count: int | None
    raw_signature: str | None
    extraction_model: str | None
    extraction_temperature: float | None
    refinement_model: str | None
    refinement_temperature: float | None
    extracted_at: datetime
    refined_at: datetime | None
    props: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SceneExtractionListResponse(BaseModel):
    """Paginated scene extraction response."""

    data: list[SceneExtractionRead]
    total: int
    page: int
    page_size: int


class SceneExtractionDateRange(BaseModel):
    """Bounds for extraction timestamps."""

    earliest: datetime | None
    latest: datetime | None


class SceneExtractionFilterOptions(BaseModel):
    """Available filter options for scene extractions."""

    books: list[str]
    chapters_by_book: dict[str, list[int]]
    refinement_decisions: list[str]
    has_refined_options: list[bool]
    date_range: SceneExtractionDateRange

