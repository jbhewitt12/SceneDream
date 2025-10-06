"""Scene extraction persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Float, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class SceneExtraction(SQLModel, table=True):
    """Stores raw and refined scene excerpts plus extraction metadata."""

    __tablename__ = "scene_extractions"
    __table_args__ = (
        UniqueConstraint(
            "book_slug",
            "chapter_number",
            "scene_number",
            name="uq_scene_extraction_chapter_scene",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    book_slug: str = Field(max_length=255, index=True)
    source_book_path: str = Field(max_length=1024)
    chapter_number: int = Field(index=True, ge=0)
    chapter_title: str = Field(max_length=512)
    chapter_source_name: str | None = Field(default=None, max_length=255)
    scene_number: int = Field(index=True, ge=0)
    location_marker: str = Field(max_length=255)
    raw: str = Field(sa_column=Column(Text, nullable=False))
    refined: str | None = Field(default=None, sa_column=Column(Text))
    refinement_decision: str | None = Field(default=None, max_length=32)
    refinement_rationale: str | None = Field(default=None, sa_column=Column(Text))
    chunk_index: int = Field(default=0, ge=0)
    chunk_paragraph_start: int = Field(default=0, ge=0)
    chunk_paragraph_end: int = Field(default=0, ge=0)
    raw_word_count: int | None = Field(default=None, ge=0)
    raw_char_count: int | None = Field(default=None, ge=0)
    refined_word_count: int | None = Field(default=None, ge=0)
    refined_char_count: int | None = Field(default=None, ge=0)
    raw_signature: str | None = Field(default=None, max_length=128)
    provisional_id: int | None = Field(default=None, ge=0)
    location_marker_normalized: str | None = Field(default=None, max_length=255)
    scene_paragraph_start: int | None = Field(default=None, ge=0)
    scene_paragraph_end: int | None = Field(default=None, ge=0)
    scene_word_start: int | None = Field(default=None, ge=0)
    scene_word_end: int | None = Field(default=None, ge=0)
    extraction_model: str | None = Field(default=None, max_length=255)
    extraction_temperature: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    refinement_model: str | None = Field(default=None, max_length=255)
    refinement_temperature: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    refined_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    refinement_has_refined_excerpt: bool | None = Field(
        default=None,
        sa_column=Column(Boolean, nullable=True),
    )
    props: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )

    def touch_refined_timestamp(self) -> None:
        """Helper to stamp the refinement timestamp when mutating refined text."""

        self.refined_at = datetime.now(timezone.utc)
