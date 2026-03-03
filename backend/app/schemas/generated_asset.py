"""Schemas for canonical generated assets."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GeneratedAssetCreate(BaseModel):
    """Schema for creating a canonical generated asset."""

    document_id: UUID | None = None
    pipeline_run_id: UUID | None = None
    scene_extraction_id: UUID | None = None
    image_prompt_id: UUID | None = None
    asset_type: str
    status: str = "created"
    provider: str | None = None
    model: str | None = None
    storage_path: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    asset_metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedAssetRead(BaseModel):
    """Detailed representation of a canonical generated asset."""

    id: UUID
    document_id: UUID | None
    pipeline_run_id: UUID | None
    scene_extraction_id: UUID | None
    image_prompt_id: UUID | None
    asset_type: str
    status: str
    provider: str | None
    model: str | None
    storage_path: str | None
    file_name: str | None
    mime_type: str | None
    asset_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedAssetListResponse(BaseModel):
    """Collection response for generated assets."""

    data: list[GeneratedAssetRead]
    total: int
