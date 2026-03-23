from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str


class ApiErrorDetail(BaseModel):
    """Structured app error payload used for migrated non-validation responses."""

    code: str
    message: str
    cause_messages: list[str] = Field(default_factory=list)
    stage: str | None = None
    run_id: UUID | None = None
    error_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    """Canonical app error response envelope.

    FastAPI validation errors still use the framework's default `detail` array shape.
    Untouched legacy routes may continue to return string `detail` values during rollout.
    """

    detail: ApiErrorDetail
