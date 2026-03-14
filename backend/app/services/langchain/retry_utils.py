"""Utility helpers for retrying LangChain API calls with exponential backoff."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable, Coroutine, Iterable
from typing import Any, TypeVar

T = TypeVar("T")


def _load_known_rate_limit_errors() -> tuple[type, ...]:
    """Lazily import known rate limit exception types, tolerating missing deps."""

    candidates: Iterable[tuple[str, str]] = (
        ("google.api_core.exceptions", "ResourceExhausted"),
        ("google.api_core.exceptions", "TooManyRequests"),
        ("google.api_core.exceptions", "RetryError"),
        ("openai.error", "RateLimitError"),
        ("openai.error", "APIError"),
    )
    resolved = []
    for module_name, attr_name in candidates:
        try:
            module = __import__(module_name, fromlist=[attr_name])
            exc = getattr(module, attr_name)
        except (ImportError, AttributeError):
            continue
        if isinstance(exc, type):
            resolved.append(exc)
    return tuple(resolved)


KNOWN_RATE_LIMIT_ERRORS = _load_known_rate_limit_errors()


def is_rate_limit_error(exc: BaseException) -> bool:
    """Detect whether the exception represents a rate limiting response."""

    if KNOWN_RATE_LIMIT_ERRORS and isinstance(exc, KNOWN_RATE_LIMIT_ERRORS):
        return True

    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True

    message = str(exc).lower()
    return any(
        keyword in message
        for keyword in ("rate limit", "quota", "resourceexhausted", "429")
    )


def retry_with_backoff(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    **kwargs: Any,
) -> T:
    """Invoke ``func`` with retries when rate limiting errors occur.

    Prints a message when the remote API throttles the call and retries with
    exponential backoff until ``max_attempts`` is reached.
    """

    attempt = 0
    delay = base_delay
    while True:
        try:
            return func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 allow non-Exception types from SDKs
            if not is_rate_limit_error(exc):
                raise

            attempt += 1
            if attempt >= max_attempts:
                raise

            sleep_for = delay + random.uniform(0, delay * jitter)
            func_name = getattr(func, "__name__", func.__class__.__name__)
            print(
                f"Rate limit encountered on attempt {attempt}/{max_attempts} for {func_name}. "
                f"Retrying in {sleep_for:.1f}s."
            )
            time.sleep(sleep_for)
            delay *= backoff_factor


async def async_retry_with_backoff(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    **kwargs: Any,
) -> T:
    """Async version of ``retry_with_backoff``.

    Invokes an async ``func`` with retries when rate limiting errors occur,
    using ``asyncio.sleep`` for non-blocking backoff.
    """

    attempt = 0
    delay = base_delay
    while True:
        try:
            return await func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 allow non-Exception types from SDKs
            if not is_rate_limit_error(exc):
                raise

            attempt += 1
            if attempt >= max_attempts:
                raise

            sleep_for = delay + random.uniform(0, delay * jitter)
            func_name = getattr(func, "__name__", func.__class__.__name__)
            print(
                f"Rate limit encountered on attempt {attempt}/{max_attempts} for {func_name}. "
                f"Retrying in {sleep_for:.1f}s."
            )
            await asyncio.sleep(sleep_for)
            delay *= backoff_factor
