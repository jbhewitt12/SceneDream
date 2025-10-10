"""Schemas for Image Prompt API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImagePromptSceneSummary(BaseModel):
    """High-level information about a scene for prompt context."""

    id: UUID
    book_slug: str
    chapter_number: int
    chapter_title: str
    scene_number: int
    location_marker: str
    refined: str | None = None
    raw: str

    model_config = ConfigDict(from_attributes=True)


class ImagePromptRead(BaseModel):
    """Detailed representation of an image prompt variant."""

    id: UUID
    scene_extraction_id: UUID
    model_vendor: str
    model_name: str
    prompt_version: str
    variant_index: int
    title: str | None
    prompt_text: str
    negative_prompt: str | None
    style_tags: list[str] | None
    attributes: dict[str, Any]
    notes: str | None
    context_window: dict[str, Any]
    raw_response: dict[str, Any]
    temperature: float | None
    max_output_tokens: int | None
    llm_request_id: str | None
    execution_time_ms: int | None
    created_at: datetime
    updated_at: datetime
    scene: ImagePromptSceneSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class ImagePromptListResponse(BaseModel):
    """Collection response for image prompts with optional metadata."""

    data: list[ImagePromptRead]
    meta: dict[str, Any] = Field(default_factory=dict)
