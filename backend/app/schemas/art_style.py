"""Schemas for art style catalog responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ArtStyleRead(BaseModel):
    """Detailed representation of an art style entry."""

    id: UUID
    slug: str
    display_name: str
    description: str | None
    is_recommended: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArtStyleListResponse(BaseModel):
    """Collection response for art styles."""

    data: list[ArtStyleRead]
