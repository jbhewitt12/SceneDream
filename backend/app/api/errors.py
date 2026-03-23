"""Shared API error translation helpers for migrated endpoints."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas.common import ApiErrorDetail, ApiErrorResponse

logger = logging.getLogger(__name__)

_MAX_ERROR_MESSAGE_LENGTH = 2000
_UNSAFE_MESSAGE_PATTERNS = (
    re.compile(r"traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r'file "[^"]+", line \d+', re.IGNORECASE),
    re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp|https?)://\S+"),
    re.compile(r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:^|[\s'\"=])/(?:[^/\s]+/)+[^/\s]+"),
    re.compile(
        r"\b(select|insert|update|delete)\b.+\b(from|into|set|where)\b",
        re.IGNORECASE,
    ),
)
_GENERIC_MESSAGE_PATTERNS = (
    re.compile(r"^failed to\b", re.IGNORECASE),
    re.compile(r"^unexpected error\b", re.IGNORECASE),
    re.compile(r"^internal error\b", re.IGNORECASE),
    re.compile(r"^metadata generation failed after \d+ attempts\b", re.IGNORECASE),
)


class AppHTTPException(HTTPException):
    """HTTP exception whose `detail` is the canonical ApiErrorDetail shape."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: ApiErrorDetail,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=detail.model_dump(mode="json"),
            headers=headers,
        )
        self.app_detail = detail


def build_error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    """Return FastAPI response-model declarations for the app error envelope."""

    return {
        status_code: {"model": ApiErrorResponse}
        for status_code in status_codes
    }


def _truncate_message(message: str | None, *, fallback: str) -> str:
    text = (message or "").strip()
    if not text:
        text = fallback
    return text[:_MAX_ERROR_MESSAGE_LENGTH]


def extract_exception_chain(exc: BaseException | None) -> list[str]:
    """Return a de-duplicated message chain across `__cause__` / `__context__`."""

    messages: list[str] = []
    seen_ids: set[int] = set()
    seen_messages: set[str] = set()
    current = exc

    while current is not None and id(current) not in seen_ids:
        seen_ids.add(id(current))
        raw = str(current).strip() or current.__class__.__name__
        message = _truncate_message(raw, fallback=current.__class__.__name__)
        if message not in seen_messages:
            messages.append(message)
            seen_messages.add(message)
        current = current.__cause__ or current.__context__

    return messages


def is_safe_error_message(message: str) -> bool:
    """Heuristic filter for messages that are safe to surface in the UI."""

    text = message.strip()
    if not text:
        return False
    return not any(pattern.search(text) for pattern in _UNSAFE_MESSAGE_PATTERNS)


def _is_generic_error_message(message: str) -> bool:
    text = message.strip()
    if not text:
        return True
    return any(pattern.search(text) for pattern in _GENERIC_MESSAGE_PATTERNS)


def _select_display_message(
    safe_messages: list[str],
    *,
    default_message: str,
) -> str:
    for message in safe_messages:
        if not _is_generic_error_message(message):
            return _truncate_message(message, fallback=default_message)
    if safe_messages:
        return _truncate_message(safe_messages[0], fallback=default_message)
    return _truncate_message(default_message, fallback="Request failed")


def build_api_error_detail(
    *,
    code: str,
    message: str,
    cause_messages: list[str] | None = None,
    stage: str | None = None,
    run_id: UUID | None = None,
    error_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApiErrorDetail:
    """Construct a normalized ApiErrorDetail payload."""

    trimmed_causes = [
        _truncate_message(item, fallback=message)
        for item in (cause_messages or [])
        if isinstance(item, str) and item.strip()
    ]
    return ApiErrorDetail(
        code=code,
        message=_truncate_message(message, fallback="Request failed"),
        cause_messages=trimmed_causes,
        stage=stage,
        run_id=run_id,
        error_id=error_id,
        metadata=metadata or {},
    )


def build_api_error_detail_from_exception(
    *,
    code: str,
    exc: BaseException,
    default_message: str,
    stage: str | None = None,
    run_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> ApiErrorDetail:
    """Build ApiErrorDetail from an exception without creating an HTTP exception."""

    chain = extract_exception_chain(exc)
    safe_chain = [message for message in chain if is_safe_error_message(message)]
    expose_specific_message = bool(safe_chain)
    error_id: str | None = None

    if expose_specific_message:
        message = _select_display_message(safe_chain, default_message=default_message)
        cause_messages = safe_chain
    else:
        error_id = uuid4().hex[:12]
        logger.exception(
            "Redacted unsafe app error message: code=%s error_id=%s",
            code,
            error_id,
            exc_info=exc,
        )
        message = default_message
        cause_messages = []

    return build_api_error_detail(
        code=code,
        message=message,
        cause_messages=cause_messages,
        stage=stage,
        run_id=run_id,
        error_id=error_id,
        metadata=metadata,
    )


def api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    cause_messages: list[str] | None = None,
    stage: str | None = None,
    run_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> AppHTTPException:
    """Build a structured HTTP error with an explicit message."""

    return AppHTTPException(
        status_code=status_code,
        detail=build_api_error_detail(
            code=code,
            message=message,
            cause_messages=cause_messages,
            stage=stage,
            run_id=run_id,
            metadata=metadata,
        ),
        headers=headers,
    )


def api_error_from_exception(
    *,
    status_code: int,
    code: str,
    exc: BaseException,
    default_message: str,
    stage: str | None = None,
    run_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AppHTTPException:
    """Translate an exception into the structured app error envelope."""
    return AppHTTPException(
        status_code=status_code,
        detail=build_api_error_detail_from_exception(
            code=code,
            exc=exc,
            default_message=default_message,
            stage=stage,
            run_id=run_id,
            metadata=metadata,
        ),
    )


async def app_http_exception_handler(
    _request: Request,
    exc: AppHTTPException,
) -> JSONResponse:
    """Serialize AppHTTPException with the canonical ApiErrorResponse shape."""

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.app_detail.model_dump(mode="json")},
        headers=exc.headers,
    )
