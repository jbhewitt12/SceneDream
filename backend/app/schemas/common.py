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


def coerce_api_error_detail(value: Any) -> ApiErrorDetail | None:
    if isinstance(value, ApiErrorDetail):
        return value
    if isinstance(value, dict):
        try:
            return ApiErrorDetail.model_validate(value)
        except Exception:
            return None
    return None


def hydrate_pipeline_failure_detail(
    *,
    error: Any,
    usage_summary: dict[str, Any] | None,
    error_message: str | None,
    run_id: UUID | None,
) -> ApiErrorDetail | None:
    failure = coerce_api_error_detail(error)
    usage_summary = usage_summary or {}

    if failure is None:
        failure = coerce_api_error_detail(usage_summary.get("failure"))

    if failure is None:
        diagnostics = usage_summary.get("diagnostics")
        if isinstance(diagnostics, dict):
            failure = coerce_api_error_detail(diagnostics.get("error"))

    if failure is None and error_message:
        errors_block = usage_summary.get("errors")
        error_code = None
        if isinstance(errors_block, dict):
            raw_code = errors_block.get("code")
            if isinstance(raw_code, str) and raw_code.strip():
                error_code = raw_code.strip()
        failure = ApiErrorDetail(
            code=error_code or "pipeline_exception",
            message=error_message,
            cause_messages=[error_message],
        )

    if failure is not None and failure.run_id is None and run_id is not None:
        failure = failure.model_copy(update={"run_id": run_id})

    return failure
