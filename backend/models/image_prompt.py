"""Image prompt persistence models."""

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
    from .generated_image import GeneratedImage
    from .scene_extraction import SceneExtraction


class ImagePrompt(SQLModel, table=True):
    """Stores structured image prompt variants generated from scenes."""

    model_config = ConfigDict(protected_namespaces=())

    __tablename__ = "image_prompts"
    __table_args__ = (
        UniqueConstraint(
            "scene_extraction_id",
            "model_name",
            "prompt_version",
            "variant_index",
            name="uq_image_prompt_unique_variant",
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
    model_name: str = Field(max_length=128, index=True)
    prompt_version: str = Field(max_length=64, index=True)
    variant_index: int = Field(ge=0)
    title: str | None = Field(default=None, max_length=255)
    prompt_text: str = Field(sa_column=Column(Text, nullable=False))
    negative_prompt: str | None = Field(default=None, sa_column=Column(Text))
    style_tags: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    notes: str | None = Field(default=None, sa_column=Column(Text))
    context_window: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    raw_response: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    temperature: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    max_output_tokens: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    llm_request_id: str | None = Field(default=None, max_length=64)
    execution_time_ms: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    scene_extraction: "SceneExtraction" | None = Relationship(
        sa_relationship=relationship("SceneExtraction", back_populates="image_prompts")
    )
    generated_images: list["GeneratedImage"] = Relationship(
        sa_relationship=relationship("GeneratedImage", back_populates="image_prompt")
    )
