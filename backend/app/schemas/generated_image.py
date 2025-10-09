"""Schemas for Generated Image API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GeneratedImageBase(BaseModel):
    """Base fields for generated images."""

    scene_extraction_id: UUID
    image_prompt_id: UUID
    book_slug: str
    chapter_number: int
    variant_index: int
    provider: str
    model: str
    size: str
    quality: str
    style: str
    aspect_ratio: str | None = None
    response_format: str
    storage_path: str
    file_name: str
    width: int | None = None
    height: int | None = None
    bytes_approx: int | None = None
    checksum_sha256: str | None = None
    request_id: str | None = None
    error: str | None = None


class GeneratedImageCreate(GeneratedImageBase):
    """Schema for creating a new generated image record."""

    pass


class GeneratedImageRead(GeneratedImageBase):
    """Detailed representation of a generated image."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImagePromptSummary(BaseModel):
    """Summary of image prompt for context."""

    id: UUID
    prompt_text: str
    style_tags: list[str] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SceneSummary(BaseModel):
    """Summary of scene for context."""

    id: UUID
    book_slug: str
    chapter_number: int
    chapter_title: str
    scene_number: int
    location_marker: str
    raw: str
    refined: str | None = None

    model_config = ConfigDict(from_attributes=True)


class GeneratedImageWithContext(BaseModel):
    """Generated image with full prompt and scene context."""

    image: GeneratedImageRead
    prompt: ImagePromptSummary | None = None
    scene: SceneSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class GeneratedImageListResponse(BaseModel):
    """Collection response for generated images with optional metadata."""

    data: list[GeneratedImageRead]
    meta: dict[str, Any] = Field(default_factory=dict)


class GeneratedImageGenerateRequest(BaseModel):
    """Request schema for triggering image generation."""

    book_slug: str | None = None
    chapter_range: tuple[int, int] | None = None
    scene_ids: list[UUID] | None = None
    prompt_ids: list[UUID] | None = None
    limit: int | None = Field(None, ge=1, le=100)
    overwrite: bool = False
    quality: str = Field("standard", pattern="^(standard|hd)$")
    preferred_style: str | None = Field(None, pattern="^(vivid|natural)$")
    aspect_ratio: str | None = Field(None, pattern="^(1:1|9:16|16:9)$")
    provider: str = "openai"
    model: str = "dall-e-3"
    response_format: str = Field("b64_json", pattern="^(b64_json|url)$")
    concurrency: int = Field(3, ge=1, le=10)
    dry_run: bool = False


class GeneratedImageGenerateResponse(BaseModel):
    """Response schema for image generation results."""

    generated_image_ids: list[UUID]
    count: int
    dry_run: bool
