"""API routes for document dashboard lifecycle visibility."""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.core.db import engine
from app.schemas import DocumentDashboardResponse, DocumentStageSyncResponse
from app.services.document_dashboard_service import DocumentDashboardService
from app.services.pipeline import DocumentStageStatusService

router = APIRouter(prefix="/documents", tags=["documents"])


def _load_dashboard_response() -> DocumentDashboardResponse:
    with Session(engine) as session:
        service = DocumentDashboardService(session)
        entries = service.list_entries()
    return DocumentDashboardResponse(data=entries, total=len(entries))


def _sync_document_stage_statuses() -> DocumentStageSyncResponse:
    with Session(engine) as session:
        synced = DocumentStageStatusService(session).sync_all_documents()
    return DocumentStageSyncResponse(synced=synced)


@router.get("/dashboard", response_model=DocumentDashboardResponse)
async def get_documents_dashboard() -> DocumentDashboardResponse:
    """Return dashboard status rows for source documents."""

    return await run_in_threadpool(_load_dashboard_response)


@router.post("/sync-stages", response_model=DocumentStageSyncResponse)
async def sync_document_stages() -> DocumentStageSyncResponse:
    """Synchronize extraction/ranking statuses for all documents."""

    return await run_in_threadpool(_sync_document_stage_statuses)
