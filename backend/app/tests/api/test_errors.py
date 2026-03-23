from __future__ import annotations

from app.api.errors import (
    build_api_error_detail_from_exception,
    extract_exception_chain,
)


def test_extract_exception_chain_preserves_causes() -> None:
    try:
        try:
            raise RuntimeError("provider failed")
        except RuntimeError as exc:
            raise ValueError("metadata generation failed after 2 attempts") from exc
    except ValueError as exc:
        messages = extract_exception_chain(exc)

    assert messages == [
        "metadata generation failed after 2 attempts",
        "provider failed",
    ]


def test_build_api_error_detail_from_exception_prefers_specific_cause() -> None:
    try:
        try:
            raise RuntimeError("provider failed")
        except RuntimeError as exc:
            raise ValueError("metadata generation failed after 2 attempts") from exc
    except ValueError as exc:
        detail = build_api_error_detail_from_exception(
            code="metadata_generation_failed",
            exc=exc,
            default_message="Failed to generate metadata variants",
        )

    assert detail.code == "metadata_generation_failed"
    assert detail.message == "provider failed"
    assert detail.cause_messages == [
        "metadata generation failed after 2 attempts",
        "provider failed",
    ]
    assert detail.error_id is None


def test_build_api_error_detail_from_exception_redacts_unsafe_message() -> None:
    exc = RuntimeError(
        "Database connection failed for postgresql://user:secret@localhost/app"
    )

    detail = build_api_error_detail_from_exception(
        code="pipeline_run_start_failed",
        exc=exc,
        default_message="Failed to start pipeline run",
    )

    assert detail.message == "Failed to start pipeline run"
    assert detail.cause_messages == []
    assert detail.error_id is not None
