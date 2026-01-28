"""Social media post tracking models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .generated_image import GeneratedImage


class SocialMediaPost(SQLModel, table=True):
    """Tracks posting queue and history for generated images to social media services."""

    __tablename__ = "social_media_posts"
    __table_args__ = (
        UniqueConstraint(
            "generated_image_id",
            "service_name",
            name="uq_social_media_post_image_service",
        ),
    )

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    generated_image_id: uuid.UUID = Field(
        foreign_key="generated_images.id",
        nullable=False,
        index=True,
    )
    service_name: str = Field(max_length=64, nullable=False, index=True)
    status: str = Field(max_length=32, nullable=False, index=True)
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1024)
    queued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    posted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_attempt_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    attempt_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text))

    generated_image: "GeneratedImage" | None = Relationship(
        sa_relationship=relationship(
            "GeneratedImage", back_populates="social_media_posts"
        )
    )
