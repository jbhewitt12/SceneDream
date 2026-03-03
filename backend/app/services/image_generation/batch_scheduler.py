"""Background scheduler that checks for pending OpenAI batch jobs and processes results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from openai import OpenAI
from sqlmodel import Session

from app.repositories.image_generation_batch import ImageGenerationBatchRepository

logger = logging.getLogger(__name__)

# Check every 5 minutes for completed batches
CHECK_INTERVAL_MINUTES = 5

# Handle missed executions during laptop sleep (24 hours)
MISFIRE_GRACE_TIME_SECONDS = 60 * 60 * 24


def check_pending_batches(session: Session, client: OpenAI) -> None:
    """Check for pending batches and process completed results.

    Extracted as a standalone function so it can be called from tests
    without needing to mock deferred imports.
    """
    from app.services.image_generation.batch_image_generation_service import (
        BatchImageGenerationService,
    )

    batch_repo = ImageGenerationBatchRepository(session)
    pending = batch_repo.list_pending()

    if not pending:
        logger.debug("No pending batches")
        return

    logger.info("Found %d pending batch(es)", len(pending))

    for batch in pending:
        try:
            openai_batch = client.batches.retrieve(batch.openai_batch_id)
            new_status = openai_batch.status

            # Update progress counts
            counts = openai_batch.request_counts
            update_kwargs: dict[str, object] = {}
            if counts:
                update_kwargs["completed_requests"] = counts.completed
                update_kwargs["failed_requests"] = counts.failed

            if new_status == "completed":
                update_kwargs["openai_output_file_id"] = openai_batch.output_file_id
                update_kwargs["openai_error_file_id"] = openai_batch.error_file_id
                update_kwargs["completed_at"] = datetime.now(timezone.utc)
                batch_repo.update_status(batch.id, "completed", **update_kwargs)
                session.commit()

                # Refresh batch after commit
                session.refresh(batch)

                # Process results
                service = BatchImageGenerationService(session, api_key=client.api_key)
                results = service.process_completed_batch(batch)
                logger.info(
                    "Processed batch %s: %d images, %d errors",
                    batch.openai_batch_id,
                    sum(1 for r in results if r.generated_image_id is not None),
                    sum(1 for r in results if r.error),
                )

            elif new_status in ("failed", "expired", "cancelled"):
                errors = []
                batch_errors = getattr(openai_batch, "errors", None)
                if batch_errors and batch_errors.data:
                    for err in batch_errors.data:
                        errors.append(f"{err.code}: {err.message}")
                update_kwargs["error"] = "; ".join(errors) if errors else new_status
                update_kwargs["completed_at"] = datetime.now(timezone.utc)
                batch_repo.update_status(batch.id, new_status, **update_kwargs)
                session.commit()
                logger.warning(
                    "Batch %s ended with status: %s",
                    batch.openai_batch_id,
                    new_status,
                )

            elif new_status != batch.status:
                batch_repo.update_status(batch.id, new_status, **update_kwargs)
                session.commit()
                logger.info(
                    "Batch %s status: %s -> %s",
                    batch.openai_batch_id,
                    batch.status,
                    new_status,
                )

        except Exception:
            logger.exception("Error checking batch %s", batch.openai_batch_id)


class BatchImageScheduler:
    """Periodically checks for pending image generation batches and processes results."""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self._scheduler is not None

    def start(self) -> None:
        """Start the background scheduler."""
        if self._started:
            logger.warning("Batch image scheduler already started")
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._check_batches_job,
            trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
            id="batch_image_checker",
            name="Batch Image Generation Checker",
            replace_existing=True,
            misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
            coalesce=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info(
            "Batch image scheduler started (interval: %d minutes)",
            CHECK_INTERVAL_MINUTES,
        )

    def stop(self) -> None:
        """Stop the background scheduler gracefully."""
        if not self._started or self._scheduler is None:
            return

        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        self._started = False
        logger.info("Batch image scheduler stopped")

    async def _check_batches_job(self) -> None:
        """Check for pending batches and process any that have completed."""
        import os

        from app.core.config import settings
        from app.core.db import engine

        logger.debug("Batch check job started")

        try:
            api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
            client = OpenAI(api_key=api_key)

            with Session(engine) as session:
                check_pending_batches(session, client)

        except Exception:
            logger.exception("Error during batch check job")


# Global scheduler instance
_scheduler: BatchImageScheduler | None = None


def get_batch_scheduler() -> BatchImageScheduler:
    """Get the global batch scheduler instance, creating it if necessary."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BatchImageScheduler()
    return _scheduler


async def start_batch_scheduler() -> None:
    """Start the global batch scheduler (call from FastAPI startup)."""
    scheduler = get_batch_scheduler()
    scheduler.start()


async def stop_batch_scheduler() -> None:
    """Stop the global batch scheduler (call from FastAPI shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None
