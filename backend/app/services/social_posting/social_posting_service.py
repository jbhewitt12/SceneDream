"""Main orchestrating service for social media posting."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from models.generated_image import GeneratedImage
from models.social_media_post import SocialMediaPost

from .exceptions import RateLimitError
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

    @staticmethod
    def get_cooldown_hours(service_name: str | None) -> float:
        """Get the cooldown hours for a specific service."""
        if service_name == "x":
            return settings.X_HOURS_BETWEEN_POSTS
        elif service_name == "flickr":
            return settings.FLICKR_HOURS_BETWEEN_POSTS
        # Default to the longer X delay if service unknown or None
        return settings.X_HOURS_BETWEEN_POSTS

    def should_post_now(self, service_name: str | None = None) -> bool:
        """Check if enough time has passed since the last post.

        Args:
            service_name: If provided, check cooldown for this specific service.
                          If None, check global cooldown across all services.
        """
        last_posted_at = self._repo.get_last_posted_at(service_name)
        if last_posted_at is None:
            return True

        cooldown_hours = self.get_cooldown_hours(service_name)
        cooldown = timedelta(hours=cooldown_hours)
        next_allowed = last_posted_at + cooldown
        return datetime.now(timezone.utc) >= next_allowed

    async def process_queue(
        self, *, process_all_services: bool = False
    ) -> SocialMediaPost | None:
        """
        Process queued posts if the per-service cooldown has passed.

        Checks each enabled service independently, allowing one service to post
        even if another service recently posted.

        Args:
            process_all_services: If True, process one post for EACH eligible
                service (useful for startup recovery after laptop sleep).
                If False (default), process only the first eligible post.

        Returns:
            The last processed SocialMediaPost if any were posted, None otherwise
        """
        enabled_services = self.get_enabled_services()
        last_result: SocialMediaPost | None = None

        for service_name in enabled_services:
            # Check per-service cooldown
            if not self.should_post_now(service_name):
                logger.debug(
                    "Cooldown not passed for service %s, checking next",
                    service_name,
                )
                continue

            # Get oldest queued post for this service
            cooldown_hours = self.get_cooldown_hours(service_name)
            post = self._repo.get_oldest_queued(service_name, cooldown_hours)
            if not post:
                logger.debug("No queued posts for service %s", service_name)
                continue

            logger.info(
                "Processing queued post %s for service %s",
                post.id,
                service_name,
            )
            result = await self._post_to_service(post)
            last_result = result

            # Unless we want to process all services, return after first post
            if not process_all_services:
                return result

        if last_result is None:
            logger.debug("No posts eligible for processing across any service")
        return last_result

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

        except RateLimitError as e:
            # Keep as queued so it will be retried after cooldown
            # last_attempt_at is already set, so get_oldest_queued will skip it
            post.error_message = f"Rate limited: {e}"
            logger.warning(
                f"Rate limited posting image {post.generated_image_id} to "
                f"{post.service_name}: {e}. Will retry after cooldown."
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

    def retry_failed(
        self,
        service_name: str | None = None,
        since: datetime | None = None,
    ) -> list[SocialMediaPost]:
        """Reset failed posts back to queued for retry.

        Args:
            service_name: Optionally filter by service (e.g. "flickr").
            since: Optionally only requeue posts that failed after this time.

        Returns:
            The list of posts that were requeued.
        """
        posts = self._repo.requeue_failed(service_name=service_name, since=since)
        logger.info("Requeued %d failed posts for retry", len(posts))
        return posts
