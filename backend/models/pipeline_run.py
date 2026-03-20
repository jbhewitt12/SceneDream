"""Pipeline run persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .document import Document
    from .generated_asset import GeneratedAsset
    from .generated_image import GeneratedImage
    from .image_prompt import ImagePrompt
    from .scene_ranking import SceneRanking


class PipelineRun(SQLModel, table=True):
    """Tracks one pipeline execution for a source document."""

    __tablename__ = "pipeline_runs"

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="documents.id",
        nullable=True,
        index=True,
    )
    book_slug: str | None = Field(default=None, max_length=255, index=True)
    status: str = Field(default="pending", max_length=32, nullable=False, index=True)
    current_stage: str | None = Field(default=None, max_length=64, index=True)
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    config_overrides: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    usage_summary: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    stage_progress: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    document: "Document" | None = Relationship(
        sa_relationship=relationship("Document", back_populates="pipeline_runs")
    )
    rankings: list["SceneRanking"] = Relationship(
        sa_relationship=relationship("SceneRanking", back_populates="pipeline_run")
    )
    image_prompts: list["ImagePrompt"] = Relationship(
        sa_relationship=relationship("ImagePrompt", back_populates="pipeline_run")
    )
    generated_images: list["GeneratedImage"] = Relationship(
        sa_relationship=relationship("GeneratedImage", back_populates="pipeline_run")
    )
    generated_assets: list["GeneratedAsset"] = Relationship(
        sa_relationship=relationship("GeneratedAsset", back_populates="pipeline_run")
    )
