"""Image generation batch tracking models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ConfigDict
from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ImageGenerationBatch(SQLModel, table=True):
    """Tracks OpenAI Batch API jobs for image generation."""

    model_config = ConfigDict(protected_namespaces=())

    __tablename__ = "image_generation_batches"

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    openai_batch_id: str = Field(max_length=255, nullable=False, index=True)
    openai_input_file_id: str = Field(max_length=255, nullable=False)
    openai_output_file_id: str | None = Field(default=None, max_length=255)
    openai_error_file_id: str | None = Field(default=None, max_length=255)
    status: str = Field(max_length=32, nullable=False, index=True)
    task_mapping: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    provider: str = Field(max_length=64, nullable=False)
    model: str = Field(max_length=128, nullable=False)
    quality: str = Field(max_length=32, nullable=False)
    style: str = Field(max_length=32, nullable=False)
    size: str = Field(max_length=32, nullable=False)
    total_requests: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )
    completed_requests: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )
    failed_requests: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )
    book_slug: str | None = Field(default=None, max_length=255, index=True)
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
