"""Schemas for global app settings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .art_style import ArtStyleRead


class AppSettingsRead(BaseModel):
    """Detailed representation of current global settings."""

    id: UUID
    default_scenes_per_run: int
    default_art_style_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppSettingsUpdateRequest(BaseModel):
    """Patch payload for updating global defaults."""

    default_scenes_per_run: int | None = Field(default=None, ge=1, le=100)
    default_art_style_id: UUID | None = None


class AppSettingsBundleResponse(BaseModel):
    """Settings payload bundled with active art styles."""

    settings: AppSettingsRead
    art_styles: list[ArtStyleRead]


class ArtStyleListsRead(BaseModel):
    """Line-oriented art-style settings payload split by style pool."""

    recommended_styles: list[str]
    other_styles: list[str]
    updated_at: datetime


class ArtStyleListsUpdateRequest(BaseModel):
    """Full-replacement payload for editable style pools."""

    recommended_styles: list[str]
    other_styles: list[str]
