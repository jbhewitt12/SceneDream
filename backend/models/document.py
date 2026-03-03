"""Canonical document persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .generated_asset import GeneratedAsset
    from .pipeline_run import PipelineRun
    from .scene_extraction import SceneExtraction


class Document(SQLModel, table=True):
    """Canonical source file tracked by the pipeline."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("slug", name="uq_documents_slug"),)

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    slug: str = Field(max_length=255, nullable=False, index=True)
    display_name: str | None = Field(default=None, max_length=255)
    source_path: str = Field(max_length=1024, nullable=False)
    source_type: str = Field(max_length=32, nullable=False, index=True)
    ingestion_state: str = Field(
        default="pending",
        max_length=32,
        nullable=False,
        index=True,
    )
    ingestion_error: str | None = Field(default=None, sa_column=Column(Text))
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    scenes: list["SceneExtraction"] = Relationship(
        sa_relationship=relationship("SceneExtraction", back_populates="document")
    )
    pipeline_runs: list["PipelineRun"] = Relationship(
        sa_relationship=relationship("PipelineRun", back_populates="document")
    )
    generated_assets: list["GeneratedAsset"] = Relationship(
        sa_relationship=relationship("GeneratedAsset", back_populates="document")
    )
