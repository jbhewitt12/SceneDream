"""Shared background-task helpers for pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    task_name: str,
) -> asyncio.Task[Any]:
    """Schedule a coroutine as an asyncio task and log unhandled exceptions."""

    task = asyncio.create_task(coro, name=task_name)

    def _handle_task_result(completed: asyncio.Task[Any]) -> None:
        try:
            completed.result()
        except Exception:
            logger.exception("Unhandled exception in background task %s", task_name)

    task.add_done_callback(_handle_task_result)
    return task
