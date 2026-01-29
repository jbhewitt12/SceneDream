"""Main orchestrating service for social media posting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from models.generated_image import GeneratedImage
from models.social_media_post import SocialMediaPost

from .flickr_poster import FlickrPoster
from .repository import SocialMediaPostRepository
from .x_poster import XPoster

logger = logging.getLogger(__name__)


class SocialPostingService:
    """Orchestrates posting images to configured social media services."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = SocialMediaPostRepository(session)
        self._flickr_poster: FlickrPoster | None = None
        self._x_poster: XPoster | None = None

    @staticmethod
    def get_enabled_services() -> list[str]:
        """Return list of enabled social media services based on config."""
        services: list[str] = []
        if settings.FLICKR_ENABLED and settings.FLICKR_API_KEY:
            services.append("flickr")
        if settings.X_ENABLED and settings.X_CONSUMER_KEY:
            services.append("x")
        return services

    def queue_image(self, image_id: UUID) -> list[SocialMediaPost]:
        """
        Queue an image for posting to all enabled social media services.

        Args:
            image_id: The UUID of the GeneratedImage to queue

        Returns:
            List of created SocialMediaPost records

        Raises:
            ValueError: If image not found or not approved
        """
        image = self._session.get(GeneratedImage, image_id)
        if not image:
            raise ValueError(f"Image not found: {image_id}")

        if not image.user_approved:
            raise ValueError("Cannot queue non-approved image for posting")

        enabled_services = self.get_enabled_services()
        if not enabled_services:
            logger.warning("No social media services are enabled")
            return []

        created_posts: list[SocialMediaPost] = []

        for service_name in enabled_services:
            # Check if already queued or posted for this service
            existing = self._repo.get_by_image_and_service(image_id, service_name)
            if existing:
                logger.info(
                    f"Image {image_id} already has a {service_name} post "
                    f"with status: {existing.status}"
                )
                continue

            # Create the queue record
            post = self._repo.create(
                data={
                    "generated_image_id": image_id,
                    "service_name": service_name,
                    "status": "queued",
                },
                commit=False,
            )
            created_posts.append(post)
            logger.info(f"Queued image {image_id} for {service_name}")

        if created_posts:
            self._session.commit()

        return created_posts

    def should_post_now(self) -> bool:
        """Check if enough time has passed since the last post."""
        last_posted_at = self._repo.get_last_posted_at()
        if last_posted_at is None:
            return True

        cooldown = timedelta(hours=settings.HOURS_BETWEEN_POSTING_IMAGES)
        next_allowed = last_posted_at + cooldown
        return datetime.now(timezone.utc) >= next_allowed

    async def process_queue(self) -> SocialMediaPost | None:
        """
        Process the oldest queued post if the cooldown has passed.

        Returns:
            The processed SocialMediaPost if one was posted, None otherwise
        """
        if not self.should_post_now():
            logger.debug("Cooldown period not yet passed, skipping queue processing")
            return None

        post = self._repo.get_oldest_queued()
        if not post:
            logger.debug("No queued posts to process")
            return None

        return await self._post_to_service(post)

    async def _post_to_service(self, post: SocialMediaPost) -> SocialMediaPost:
        """
        Attempt to post a queued item to its service.

        Args:
            post: The SocialMediaPost record to process

        Returns:
            The updated SocialMediaPost record
        """
        post.last_attempt_at = datetime.now(timezone.utc)
        post.attempt_count += 1

        try:
            # Load the image and prompt
            image = self._session.get(GeneratedImage, post.generated_image_id)
            if not image:
                raise ValueError(f"Image not found: {post.generated_image_id}")

            prompt = image.image_prompt
            if not prompt:
                raise ValueError(f"Image {image.id} has no associated prompt")

            if post.service_name == "flickr":
                if self._flickr_poster is None:
                    self._flickr_poster = FlickrPoster()
                photo_id, photo_url = await self._flickr_poster.post(image, prompt)
                post.external_id = photo_id
                post.external_url = photo_url
            elif post.service_name == "x":
                if self._x_poster is None:
                    self._x_poster = XPoster()
                tweet_id, tweet_url = await self._x_poster.post(image, prompt)
                post.external_id = tweet_id
                post.external_url = tweet_url
            else:
                raise ValueError(f"Unknown service: {post.service_name}")

            post.status = "posted"
            post.posted_at = datetime.now(timezone.utc)
            post.error_message = None
            logger.info(
                f"Successfully posted image {image.id} to {post.service_name}: "
                f"{post.external_url}"
            )

        except Exception as e:
            post.status = "failed"
            post.error_message = str(e)
            logger.error(
                f"Failed to post image {post.generated_image_id} to "
                f"{post.service_name}: {e}"
            )

        self._repo.update(post, commit=True)
        return post

    def get_posting_status(self, image_id: UUID) -> list[SocialMediaPost]:
        """Get all social media post records for an image."""
        return self._repo.get_by_image_id(image_id)

    def has_been_posted(self, image_id: UUID) -> bool:
        """Check if an image has been successfully posted to any service."""
        posts = self._repo.get_by_image_id(image_id)
        return any(p.status == "posted" for p in posts)

    def is_queued(self, image_id: UUID) -> bool:
        """Check if an image is currently queued for any service."""
        posts = self._repo.get_by_image_id(image_id)
        return any(p.status == "queued" for p in posts)
