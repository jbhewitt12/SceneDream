"""Schemas for canonical documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Schema for creating a canonical document."""

    slug: str
    display_name: str | None = None
    source_path: str
    source_type: str
    ingestion_state: str = "pending"
    ingestion_error: str | None = None
    extraction_status: str = "pending"
    extraction_completed_at: datetime | None = None
    extraction_error: str | None = None
    ranking_status: str = "pending"
    ranking_completed_at: datetime | None = None
    ranking_error: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    """Detailed representation of a canonical document."""

    id: UUID
    slug: str
    display_name: str | None
    source_path: str
    source_type: str
    ingestion_state: str
    ingestion_error: str | None
    extraction_status: str
    extraction_completed_at: datetime | None
    extraction_error: str | None
    ranking_status: str
    ranking_completed_at: datetime | None
    ranking_error: str | None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Collection response for documents."""

    data: list[DocumentRead]
    total: int


class DocumentDashboardCounts(BaseModel):
    """Per-document counts for each pipeline output stage."""

    extracted: int = 0
    ranked: int = 0
    prompts_generated: int = 0
    images_generated: int = 0


class DocumentDashboardStageStatus(BaseModel):
    """Explicit status payload for one pipeline stage."""

    status: str = "pending"
    completed_at: datetime | None = None
    error: str | None = None


class DocumentDashboardStages(BaseModel):
    """Per-stage status metadata used by the dashboard."""

    extraction: DocumentDashboardStageStatus = Field(
        default_factory=DocumentDashboardStageStatus
    )
    ranking: DocumentDashboardStageStatus = Field(
        default_factory=DocumentDashboardStageStatus
    )
    prompts_generated: DocumentDashboardStageStatus = Field(
        default_factory=DocumentDashboardStageStatus
    )
    images_generated: DocumentDashboardStageStatus = Field(
        default_factory=DocumentDashboardStageStatus
    )


class DocumentDashboardRunSummary(BaseModel):
    """Latest pipeline-run summary for a document."""

    id: UUID
    status: str
    current_stage: str | None
    error_message: str | None
    usage_summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentDashboardEntry(BaseModel):
    """Dashboard row for one source document/file."""

    document_id: UUID | None = None
    slug: str
    display_name: str
    source_path: str
    source_type: str
    file_exists: bool
    ingestion_state: str | None = None
    ingestion_error: str | None = None
    counts: DocumentDashboardCounts = Field(default_factory=DocumentDashboardCounts)
    stages: DocumentDashboardStages = Field(default_factory=DocumentDashboardStages)
    last_run: DocumentDashboardRunSummary | None = None


class DocumentDashboardResponse(BaseModel):
    """Collection response for document dashboard rows."""

    data: list[DocumentDashboardEntry]
    total: int


class DocumentStageSyncResponse(BaseModel):
    """Response payload for bulk document stage synchronization."""

    synced: int
