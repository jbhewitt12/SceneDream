"""Generated image persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlalchemy import Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .image_prompt import ImagePrompt
    from .scene_extraction import SceneExtraction


class GeneratedImage(SQLModel, table=True):
    """Stores generated images with metadata and idempotency controls."""

    model_config = ConfigDict(protected_namespaces=())

    __tablename__ = "generated_images"
    __table_args__ = (
        UniqueConstraint(
            "image_prompt_id",
            "variant_index",
            "provider",
            "model",
            "size",
            "quality",
            "style",
            name="uq_generated_image_idempotency",
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
    image_prompt_id: uuid.UUID = Field(
        foreign_key="image_prompts.id",
        nullable=False,
        index=True,
    )
    book_slug: str = Field(max_length=255, nullable=False, index=True)
    chapter_number: int = Field(ge=0, nullable=False, index=True)
    variant_index: int = Field(ge=0, nullable=False)
    provider: str = Field(max_length=64, nullable=False)
    model: str = Field(max_length=128, nullable=False)
    size: str = Field(max_length=32, nullable=False)
    quality: str = Field(max_length=32, nullable=False)
    style: str = Field(max_length=32, nullable=False)
    aspect_ratio: str | None = Field(default=None, max_length=16)
    response_format: str = Field(max_length=32, nullable=False)
    storage_path: str = Field(max_length=1024, nullable=False)
    file_name: str = Field(max_length=255, nullable=False)
    width: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    height: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    bytes_approx: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    checksum_sha256: str | None = Field(default=None, max_length=64)
    request_id: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        index=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    error: str | None = Field(default=None, sa_column=Column(Text))

    scene_extraction: "SceneExtraction" | None = Relationship(
        sa_relationship=relationship(
            "SceneExtraction", back_populates="generated_images"
        )
    )
    image_prompt: "ImagePrompt" | None = Relationship(
        sa_relationship=relationship("ImagePrompt", back_populates="generated_images")
    )
