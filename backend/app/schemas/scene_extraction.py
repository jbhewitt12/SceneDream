"""Schemas for Scene Extraction API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.prompt_art_style import (
    PromptArtStyleMode,
    coerce_prompt_art_style_selection,
    normalize_prompt_art_style_text,
)


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
    provisional_id: int | None
    location_marker_normalized: str | None
    scene_paragraph_start: int | None
    scene_paragraph_end: int | None
    scene_word_start: int | None
    scene_word_end: int | None
    extraction_model: str | None
    extraction_temperature: float | None
    refinement_model: str | None
    refinement_temperature: float | None
    extracted_at: datetime
    refined_at: datetime | None
    refinement_has_refined_excerpt: bool | None
    props: dict[str, Any] = Field(default_factory=dict)
    ranking_score: float | None = None
    has_content_warnings: bool = False

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


class SceneGenerateRequest(BaseModel):
    """Request payload for scene-targeted prompt + image generation."""

    num_images: int = Field(ge=1, le=20)
    prompt_art_style_mode: PromptArtStyleMode | None = None
    prompt_art_style_text: str | None = None
    quality: Literal["standard", "hd"] = "standard"
    style: Literal["vivid", "natural"] | None = None
    aspect_ratio: Literal["1:1", "9:16", "16:9"] | None = None

    @field_validator("prompt_art_style_text")
    @classmethod
    def _normalize_prompt_art_style_text(cls, value: str | None) -> str | None:
        return normalize_prompt_art_style_text(value)

    def model_post_init(self, __context: Any) -> None:
        if self.prompt_art_style_mode is not None:
            coerce_prompt_art_style_selection(
                mode=self.prompt_art_style_mode,
                text=self.prompt_art_style_text,
            )


class SceneGenerateResponse(BaseModel):
    """Response for scene-targeted generation with pipeline run tracking."""

    pipeline_run_id: UUID
    status: str
    message: str
