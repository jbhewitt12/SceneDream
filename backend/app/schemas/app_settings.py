"""Schemas for global app settings."""

from __future__ import annotations

from typing import Any, Literal
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
    social_posting_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppSettingsUpdateRequest(BaseModel):
    """Patch payload for updating global defaults."""

    default_scenes_per_run: int | None = Field(default=None, ge=1, le=100)
    default_prompt_art_style_mode: PromptArtStyleMode | None = None
    default_prompt_art_style_text: str | None = None
    social_posting_enabled: bool | None = None

    @field_validator("default_prompt_art_style_text")
    @classmethod
    def _normalize_prompt_art_style_text(cls, value: str | None) -> str | None:
        return normalize_prompt_art_style_text(value)

    @model_validator(mode="after")
    def _validate_single_style_text(self) -> AppSettingsUpdateRequest:
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


ConfigurationCheckStatus = Literal["passed", "failed", "warning"]
ConfigurationCheckKey = Literal[
    "scene_extraction",
    "scene_ranking",
    "prompt_generation",
    "image_generation",
]


class ConfigurationCheckRead(BaseModel):
    """Single configuration-test result shown in Settings."""

    key: ConfigurationCheckKey
    label: str
    status: ConfigurationCheckStatus
    provider: str | None = None
    model: str | None = None
    used_backup_model: bool = False
    message: str
    hint: str | None = None
    action_items: list[str] = Field(default_factory=list)
    cause_messages: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfigurationTestResponse(BaseModel):
    """Aggregate Settings response for pipeline configuration checks."""

    status: ConfigurationCheckStatus
    ready_for_pipeline: bool
    summary: str
    checked_at: datetime
    checks: list[ConfigurationCheckRead]
