"""Repository helpers for PipelineRun persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from models.pipeline_run import PipelineRun


class PipelineRunRepository:
    """Provides common queries and mutations for pipeline runs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, run_id: UUID) -> PipelineRun | None:
        return self._session.get(PipelineRun, run_id)

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> PipelineRun:
        run = PipelineRun(**data)
        self._session.add(run)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(run)
        return run

    def list_recent(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[PipelineRun]:
        statement = select(PipelineRun)
        if status:
            statement = statement.where(PipelineRun.status == status)
        statement = statement.order_by(PipelineRun.created_at.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def list_for_document(
        self,
        *,
        document_id: UUID,
        limit: int | None = None,
    ) -> list[PipelineRun]:
        statement = (
            select(PipelineRun)
            .where(PipelineRun.document_id == document_id)
            .order_by(PipelineRun.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def update(
        self,
        run: PipelineRun,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> PipelineRun:
        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(run, key):
                setattr(run, key, value)
        run.updated_at = datetime.now(timezone.utc)
        self._session.add(run)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(run)
        return run

    def update_status(
        self,
        run_id: UUID,
        *,
        status: str,
        current_stage: str | None = None,
        error_message: str | None = None,
        usage_summary: dict[str, Any] | None = None,
        completed: bool = False,
        commit: bool = False,
        refresh: bool = True,
    ) -> PipelineRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.status = status
        run.current_stage = current_stage
        run.error_message = error_message
        if usage_summary is not None:
            run.usage_summary = usage_summary
        if run.started_at is None:
            run.started_at = datetime.now(timezone.utc)
        if completed:
            run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        self._session.add(run)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(run)
        return run
