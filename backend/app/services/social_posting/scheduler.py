"""Background scheduler for social media posting queue processing."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]

from app.core.config import settings

if TYPE_CHECKING:
    from sqlmodel import Session

logger = logging.getLogger(__name__)

# Run the queue processor every 15 minutes
SCHEDULER_INTERVAL_MINUTES = 15


class SocialPostingScheduler:
    """
    Manages the background scheduler for processing the social media posting queue.

    The scheduler runs periodically and checks if any queued posts should be
    processed based on the cooldown period (HOURS_BETWEEN_POSTING_IMAGES).
    """

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self._scheduler is not None

    def start(self) -> None:
        """Start the background scheduler."""
        if self._started:
            logger.warning("Scheduler already started")
            return

        # Check if any posting services are enabled
        enabled_services = self._get_enabled_services()
        if not enabled_services:
            logger.info(
                "No social media services enabled, scheduler will not start"
            )
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._process_queue_job,
            trigger=IntervalTrigger(minutes=SCHEDULER_INTERVAL_MINUTES),
            id="social_posting_queue_processor",
            name="Social Media Posting Queue Processor",
            replace_existing=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info(
            "Social posting scheduler started (interval: %d minutes, enabled services: %s)",
            SCHEDULER_INTERVAL_MINUTES,
            ", ".join(enabled_services),
        )

    def stop(self) -> None:
        """Stop the background scheduler gracefully."""
        if not self._started or self._scheduler is None:
            return

        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        self._started = False
        logger.info("Social posting scheduler stopped")

    @staticmethod
    def _get_enabled_services() -> list[str]:
        """Return list of enabled social media services."""
        services: list[str] = []
        if settings.FLICKR_ENABLED and settings.FLICKR_API_KEY:
            services.append("flickr")
        return services

    async def _process_queue_job(self) -> None:
        """
        Job that processes the posting queue.

        This is called periodically by APScheduler. It creates a new database
        session and delegates to SocialPostingService.process_queue().
        """
        from sqlmodel import Session

        from app.core.db import engine
        from app.services.social_posting.social_posting_service import (
            SocialPostingService,
        )

        logger.debug("Queue processing job started")

        try:
            with Session(engine) as session:
                service = SocialPostingService(session)

                if not service.should_post_now():
                    logger.debug(
                        "Cooldown period not passed (%.1f hours between posts)",
                        settings.HOURS_BETWEEN_POSTING_IMAGES,
                    )
                    return

                result = await service.process_queue()
                if result:
                    logger.info(
                        "Queue processing completed: posted image %s to %s",
                        result.generated_image_id,
                        result.service_name,
                    )
                else:
                    logger.debug("No posts in queue to process")

        except Exception:
            logger.exception("Error during queue processing job")

    async def trigger_immediate_check(self) -> None:
        """
        Trigger an immediate queue check.

        Call this when a new image is queued to potentially post it immediately
        if the cooldown has passed.
        """
        logger.debug("Triggering immediate queue check")
        await self._process_queue_job()


# Global scheduler instance
_scheduler: SocialPostingScheduler | None = None


def get_scheduler() -> SocialPostingScheduler:
    """Get the global scheduler instance, creating it if necessary."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SocialPostingScheduler()
    return _scheduler


async def start_scheduler() -> None:
    """Start the global scheduler (call from FastAPI startup)."""
    scheduler = get_scheduler()
    scheduler.start()


async def stop_scheduler() -> None:
    """Stop the global scheduler (call from FastAPI shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
