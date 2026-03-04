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


class DocumentDashboardStages(BaseModel):
    """Boolean completion flags for document pipeline stages."""

    extracted: bool = False
    ranked: bool = False
    prompts_generated: bool = False
    images_generated: bool = False


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
