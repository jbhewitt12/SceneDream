"""Schemas for pipeline runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
