"""Scene ranking persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict
from sqlalchemy import Column, DateTime, Float, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .scene_extraction import SceneExtraction


class SceneRanking(SQLModel, table=True):
    """Stores LLM-evaluated ranking metadata for extracted scenes."""

    model_config = ConfigDict(protected_namespaces=())

    __tablename__ = "scene_rankings"
    __table_args__ = (
        UniqueConstraint(
            "scene_extraction_id",
            "model_name",
            "prompt_version",
            "weight_config_hash",
            name="uq_scene_ranking_unique_run",
        ),
    )

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    scene_extraction_id: uuid.UUID = Field(
        foreign_key="scene_extractions.id",
        nullable=False,
        index=True,
    )
    model_vendor: str = Field(max_length=128)
    model_name: str = Field(max_length=128)
    prompt_version: str = Field(max_length=64)
    justification: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    scores: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    overall_priority: float = Field(
        sa_column=Column(Float, nullable=False),
    )
    weight_config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    weight_config_hash: str = Field(max_length=64)
    warnings: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    character_tags: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    recommended_prompt_count: int | None = Field(
        default=None,
        ge=1,
        le=10,
        sa_column=Column(Integer, nullable=True),
    )
    complexity_rationale: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    distinct_visual_moments: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    raw_response: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    execution_time_ms: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    temperature: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    llm_request_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    scene_extraction: "SceneExtraction" | None = Relationship(
        sa_relationship=relationship("SceneExtraction", back_populates="rankings")
    )
