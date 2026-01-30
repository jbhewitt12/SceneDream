"""Repository for SocialMediaPost persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.config import settings
from models.social_media_post import SocialMediaPost

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


class SocialMediaPostRepository:
    """Provides common queries for working with social media posts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, post_id: UUID) -> SocialMediaPost | None:
        return self._session.get(SocialMediaPost, post_id)

    def get_by_image_id(self, image_id: UUID) -> list[SocialMediaPost]:
        """Get all social media posts for a specific image."""
        statement = (
            select(SocialMediaPost)
            .where(SocialMediaPost.generated_image_id == image_id)
            .order_by(SocialMediaPost.queued_at.desc())
        )
        return list(self._session.exec(statement))

    def get_by_image_and_service(
        self, image_id: UUID, service_name: str
    ) -> SocialMediaPost | None:
        """Get the post record for a specific image and service."""
        statement = select(SocialMediaPost).where(
            SocialMediaPost.generated_image_id == image_id,
            SocialMediaPost.service_name == service_name,
        )
        return self._session.exec(statement).first()

    def get_oldest_queued(self) -> SocialMediaPost | None:
        """
        Get the oldest queued post that hasn't been posted yet.

        Excludes posts that were recently attempted (e.g., rate-limited)
        and are still within the cooldown period.
        """
        cooldown = timedelta(hours=settings.HOURS_BETWEEN_POSTING_IMAGES)
        cooldown_threshold = datetime.now(timezone.utc) - cooldown

        statement = (
            select(SocialMediaPost)
            .where(SocialMediaPost.status == "queued")
            .where(
                or_(
                    SocialMediaPost.last_attempt_at.is_(None),
                    SocialMediaPost.last_attempt_at <= cooldown_threshold,
                )
            )
            .order_by(SocialMediaPost.queued_at.asc())
            .limit(1)
        )
        return self._session.exec(statement).first()

    def get_last_successful_post(self) -> SocialMediaPost | None:
        """Get the most recently posted item."""
        statement = (
            select(SocialMediaPost)
            .where(SocialMediaPost.status == "posted")
            .order_by(SocialMediaPost.posted_at.desc())
            .limit(1)
        )
        return self._session.exec(statement).first()

    def get_last_posted_at(self) -> datetime | None:
        """Get the timestamp of the most recent successful post."""
        post = self.get_last_successful_post()
        return post.posted_at if post else None

    def create(
        self,
        *,
        data: Mapping[str, Any],
        commit: bool = False,
        refresh: bool = True,
    ) -> SocialMediaPost:
        post = SocialMediaPost(**data)
        self._session.add(post)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(post)
        return post

    def update(
        self,
        post: SocialMediaPost,
        *,
        commit: bool = False,
        refresh: bool = True,
    ) -> SocialMediaPost:
        self._session.add(post)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(post)
        return post

    def count_queued(self) -> int:
        """Count the number of images currently in the queue."""
        statement = select(SocialMediaPost).where(SocialMediaPost.status == "queued")
        return len(list(self._session.exec(statement)))
