"""Art style catalog model for prompt generation defaults."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ArtStyle(SQLModel, table=True):
    """Catalog of styles available for prompt-generation sampling."""

    __tablename__ = "art_styles"
    __table_args__ = (UniqueConstraint("slug", name="uq_art_styles_slug"),)

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    slug: str = Field(max_length=255, nullable=False, index=True)
    display_name: str = Field(max_length=255, nullable=False)
    description: str | None = Field(default=None, sa_column=Column(Text))
    is_recommended: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, index=True),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, index=True),
    )
    sort_order: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
