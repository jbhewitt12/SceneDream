"""Global application defaults for pipeline behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class AppSettings(SQLModel, table=True):
    """Singleton row storing user-configurable global defaults."""

    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("singleton_key", name="uq_app_settings_singleton_key"),
    )

    __allow_unmapped__ = True

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    singleton_key: str = Field(
        default="global",
        max_length=32,
        nullable=False,
        index=True,
    )
    default_scenes_per_run: int = Field(default=5, ge=1, le=100, nullable=False)
    default_prompt_art_style_mode: str = Field(
        default="random_mix",
        max_length=32,
        nullable=False,
    )
    default_prompt_art_style_text: str | None = Field(
        default=None,
        max_length=255,
        nullable=True,
    )
    social_posting_enabled: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
