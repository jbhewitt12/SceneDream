"""Domain exceptions for pipeline run startup orchestration."""

from __future__ import annotations


class PipelineValidationError(RuntimeError):
    """Raised when a pipeline launch request fails domain validation."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class DocumentNotFoundError(PipelineValidationError):
    """Raised when a document_id does not resolve to a stored document."""

    def __init__(self, detail: str = "Document not found") -> None:
        super().__init__(detail, status_code=404)


class SourceDocumentMissingError(PipelineValidationError):
    """Raised when extraction is requested but source content cannot be resolved."""
