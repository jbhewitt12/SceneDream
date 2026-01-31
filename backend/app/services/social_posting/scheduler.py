"""Background scheduler for social media posting queue processing.

This scheduler is designed to be robust to system sleep/wake cycles:
- Jobs are persisted in the database, not in memory
- On startup, an immediate queue check processes any overdue posts
- APScheduler is configured with misfire_grace_time to handle missed firings
- The startup check logs queue state for visibility
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum interval between queue checks (cap)
MAX_SCHEDULER_INTERVAL_MINUTES = 15

# Grace period for missed job executions (e.g., during laptop sleep)
# Jobs missed within this window will still fire when the system wakes
MISFIRE_GRACE_TIME_SECONDS = 60 * 60 * 24  # 24 hours


def _get_scheduler_interval_minutes() -> float:
    """
    Calculate scheduler interval based on posting cooldown.

    The scheduler checks at least as often as the posting interval,
    but never more than every 15 minutes.
    """
    posting_interval_minutes = settings.HOURS_BETWEEN_POSTING_IMAGES * 60
    return min(posting_interval_minutes, MAX_SCHEDULER_INTERVAL_MINUTES)


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
            logger.info("No social media services enabled, scheduler will not start")
            return

        interval_minutes = _get_scheduler_interval_minutes()

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._process_queue_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="social_posting_queue_processor",
            name="Social Media Posting Queue Processor",
            replace_existing=True,
            # Handle missed executions during laptop sleep
            misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
            # Combine multiple missed firings into one execution
            coalesce=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info(
            "Social posting scheduler started (interval: %.1f minutes, enabled services: %s)",
            interval_minutes,
            ", ".join(enabled_services),
        )

        # Schedule an immediate startup check with error handling
        asyncio.create_task(self._safe_startup_check())

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
        from app.services.social_posting.social_posting_service import (
            SocialPostingService,
        )

        return SocialPostingService.get_enabled_services()

    async def _safe_startup_check(self) -> None:
        """
        Wrapper for startup check with error handling.

        This ensures that startup check failures don't go unnoticed and
        don't prevent the scheduler from running.
        """
        try:
            await self._startup_check()
        except Exception:
            logger.exception(
                "Startup queue check failed - scheduler will continue running "
                "and retry on next interval"
            )

    async def _startup_check(self) -> None:
        """
        Run an immediate queue check on startup with queue status logging.

        This provides visibility into the queue state when the server starts,
        which is especially useful after laptop sleep/wake cycles.
        """
        from sqlmodel import Session

        from app.core.db import engine
        from app.services.social_posting.repository import SocialMediaPostRepository

        # Log queue state for visibility
        try:
            with Session(engine) as session:
                repo = SocialMediaPostRepository(session)
                queued_count = repo.count_queued()
                if queued_count > 0:
                    logger.info("Startup: %d posts queued for processing", queued_count)
                else:
                    logger.info("Startup: no posts in queue")

                # Log last post time per service
                for service in self._get_enabled_services():
                    last_posted = repo.get_last_posted_at(service)
                    if last_posted:
                        logger.info(
                            "Startup: last %s post was at %s",
                            service,
                            last_posted.isoformat(),
                        )
        except Exception:
            logger.exception("Failed to log queue state on startup")

        # Process the queue - on startup, process all eligible services at once
        # to catch up after laptop sleep
        logger.info("Running startup queue check")
        await self._process_queue_job(process_all_services=True)

    async def _process_queue_job(self, *, process_all_services: bool = False) -> None:
        """
        Job that processes the posting queue.

        This is called periodically by APScheduler. It creates a new database
        session and delegates to SocialPostingService.process_queue().

        The service handles per-service cooldowns internally, so we don't
        need to check cooldown here.

        Args:
            process_all_services: If True, process one post for each eligible
                service. Used on startup to recover from laptop sleep.
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

                # process_queue() handles per-service cooldowns internally
                result = await service.process_queue(
                    process_all_services=process_all_services
                )
                if result:
                    if result.status == "posted":
                        logger.info(
                            "Queue processing completed: posted image %s to %s",
                            result.generated_image_id,
                            result.service_name,
                        )
                    else:
                        logger.warning(
                            "Queue processing completed: %s image %s to %s",
                            result.status,
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
