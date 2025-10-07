"""Schemas for Scene Ranking API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SceneRankingSceneSummary(BaseModel):
    """High-level information about a ranked scene."""

    id: UUID
    book_slug: str
    chapter_number: int
    chapter_title: str
    scene_number: int
    location_marker: str
    refined: str | None
    raw: str
    refinement_decision: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SceneRankingRead(BaseModel):
    """Detailed representation of a scene ranking record."""

    id: UUID
    scene_extraction_id: UUID
    model_vendor: str
    model_name: str
    prompt_version: str
    justification: str | None
    scores: dict[str, float]
    overall_priority: float
    weight_config: dict[str, float]
    weight_config_hash: str
    warnings: list[str] | None
    character_tags: list[str] | None
    raw_response: dict[str, Any]
    execution_time_ms: int | None
    temperature: float | None
    llm_request_id: str | None
    created_at: datetime
    updated_at: datetime
    scene: SceneRankingSceneSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class SceneRankingListResponse(BaseModel):
    """Collection response for scene rankings with optional metadata."""

    data: list[SceneRankingRead]
    meta: dict[str, Any] = Field(default_factory=dict)

