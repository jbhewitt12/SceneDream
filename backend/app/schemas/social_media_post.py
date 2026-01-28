"""Schemas for Social Media Post API responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SocialMediaPostRead(BaseModel):
    """Detailed representation of a social media post record."""

    id: UUID
    generated_image_id: UUID
    service_name: str
    status: str
    external_id: str | None = None
    external_url: str | None = None
    queued_at: datetime
    posted_at: datetime | None = None
    last_attempt_at: datetime | None = None
    attempt_count: int
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class QueueForPostingResponse(BaseModel):
    """Response schema for queue for posting action."""

    posts: list[SocialMediaPostRead]
    message: str


class PostingStatusResponse(BaseModel):
    """Response schema for posting status query."""

    posts: list[SocialMediaPostRead]
    has_been_posted: bool
    is_queued: bool
