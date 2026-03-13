"""Schemas for global app settings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.prompt_art_style import (
    PromptArtStyleMode,
    coerce_prompt_art_style_selection,
    normalize_prompt_art_style_text,
)
from .art_style import ArtStyleRead


class AppSettingsRead(BaseModel):
    """Detailed representation of current global settings."""

    id: UUID
    default_scenes_per_run: int
    default_prompt_art_style_mode: PromptArtStyleMode
    default_prompt_art_style_text: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppSettingsUpdateRequest(BaseModel):
    """Patch payload for updating global defaults."""

    default_scenes_per_run: int | None = Field(default=None, ge=1, le=100)
    default_prompt_art_style_mode: PromptArtStyleMode | None = None
    default_prompt_art_style_text: str | None = None

    @field_validator("default_prompt_art_style_text")
    @classmethod
    def _normalize_prompt_art_style_text(cls, value: str | None) -> str | None:
        return normalize_prompt_art_style_text(value)

    @model_validator(mode="after")
    def _validate_single_style_text(self) -> "AppSettingsUpdateRequest":
        if self.default_prompt_art_style_mode is None:
            return self
        coerce_prompt_art_style_selection(
            mode=self.default_prompt_art_style_mode,
            text=self.default_prompt_art_style_text,
            mode_field_name="default_prompt_art_style_mode",
            text_field_name="default_prompt_art_style_text",
        )
        return self


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
