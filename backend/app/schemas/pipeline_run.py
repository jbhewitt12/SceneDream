"""Schemas for pipeline runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PipelineRunCreate(BaseModel):
    """Schema for creating a pipeline run."""

    document_id: UUID | None = None
    book_slug: str | None = None
    status: str = "pending"
    current_stage: str | None = None
    error_message: str | None = None
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PipelineRunStartRequest(BaseModel):
    """Request payload for launching a pipeline run."""

    document_id: UUID | None = None
    book_slug: str | None = None
    book_path: str | None = None
    prompts_per_scene: int | None = Field(default=None, ge=1)
    ignore_ranking_recommendations: bool = False
    prompts_for_scenes: int | None = Field(default=None, ge=1)
    images_for_scenes: int | None = Field(default=None, ge=1)
    skip_extraction: bool = False
    skip_ranking: bool = False
    skip_prompts: bool = False
    quality: Literal["standard", "hd"] = "standard"
    style: Literal["vivid", "natural"] | None = None
    aspect_ratio: Literal["1:1", "9:16", "16:9"] | None = None
    mode: Literal["batch", "sync"] = "sync"
    poll_timeout: int = Field(default=3600, ge=1)
    poll_interval: int = Field(default=30, ge=1)
    dry_run: bool = False


class PipelineRunRead(BaseModel):
    """Detailed representation of a pipeline run."""

    id: UUID
    document_id: UUID | None
    book_slug: str | None
    status: str
    current_stage: str | None
    error_message: str | None
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineRunListResponse(BaseModel):
    """Collection response for pipeline runs."""

    data: list[PipelineRunRead]
    total: int
