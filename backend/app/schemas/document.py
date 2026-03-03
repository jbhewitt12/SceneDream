"""Schemas for canonical documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Schema for creating a canonical document."""

    slug: str
    display_name: str | None = None
    source_path: str
    source_type: str
    ingestion_state: str = "pending"
    ingestion_error: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    """Detailed representation of a canonical document."""

    id: UUID
    slug: str
    display_name: str | None
    source_path: str
    source_type: str
    ingestion_state: str
    ingestion_error: str | None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Collection response for documents."""

    data: list[DocumentRead]
    total: int
