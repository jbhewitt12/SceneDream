"""Canonical generated asset persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .document import Document
    from .generated_image import GeneratedImage
    from .image_prompt import ImagePrompt
    from .pipeline_run import PipelineRun
    from .scene_extraction import SceneExtraction


class GeneratedAsset(SQLModel, table=True):
    """Normalized record for prompts/images produced by the pipeline."""

    __tablename__ = "generated_assets"

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
    pipeline_run_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="pipeline_runs.id",
        nullable=True,
        index=True,
    )
    scene_extraction_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="scene_extractions.id",
        nullable=True,
        index=True,
    )
    image_prompt_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="image_prompts.id",
        nullable=True,
        index=True,
    )
    asset_type: str = Field(max_length=32, nullable=False, index=True)
    status: str = Field(default="created", max_length=32, nullable=False, index=True)
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    storage_path: str | None = Field(default=None, max_length=1024)
    file_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=128)
    asset_metadata: dict[str, Any] = Field(
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

    document: "Document" | None = Relationship(
        sa_relationship=relationship("Document", back_populates="generated_assets")
    )
    pipeline_run: "PipelineRun" | None = Relationship(
        sa_relationship=relationship("PipelineRun", back_populates="generated_assets")
    )
    scene_extraction: "SceneExtraction" | None = Relationship(
        sa_relationship=relationship(
            "SceneExtraction", back_populates="generated_assets"
        )
    )
    image_prompt: "ImagePrompt" | None = Relationship(
        sa_relationship=relationship("ImagePrompt", back_populates="generated_assets")
    )
    generated_images: list["GeneratedImage"] = Relationship(
        sa_relationship=relationship("GeneratedImage", back_populates="generated_asset")
    )
