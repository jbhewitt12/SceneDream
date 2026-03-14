"""Synchronize canonical document extraction/ranking stage statuses."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sqlmodel import Session, select

from app.repositories import DocumentRepository, SceneRankingRepository
from app.services.scene_extraction.scene_extraction import (
    SceneExtractionConfig,
    SceneExtractor,
)
from models.document import Document
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction

DocumentStageName = Literal["extraction", "ranking"]

STAGE_STATUS_PENDING = "pending"
STAGE_STATUS_RUNNING = "running"
STAGE_STATUS_COMPLETED = "completed"
STAGE_STATUS_FAILED = "failed"
STAGE_STATUS_STALE = "stale"


class DocumentStageStatusService:
    """Computes and persists document stage statuses from source-of-truth records."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._document_repo = DocumentRepository(session)

    @staticmethod
    def to_document_stage_name(pipeline_stage: str | None) -> DocumentStageName | None:
        """Map runtime pipeline stage names to document-level stage names."""

        if not pipeline_stage:
            return None
        normalized = pipeline_stage.strip().lower()
        if normalized == "ranking":
            return "ranking"
        if normalized in {"extracting", "extraction"}:
            return "extraction"
        return None

    def mark_stage_running(
        self,
        *,
        document: Document,
        stage: DocumentStageName,
    ) -> Document:
        """Mark one stage as running unless the document already reached completion."""

        payload: dict[str, object] = {}
        if stage == "extraction":
            if self._is_sticky_completed(
                status=document.extraction_status,
                completed_at=document.extraction_completed_at,
            ):
                return document
            payload.update(
                {
                    "extraction_status": STAGE_STATUS_RUNNING,
                    "extraction_completed_at": None,
                    "extraction_error": None,
                }
            )
        else:
            if self._is_sticky_completed(
                status=document.ranking_status,
                completed_at=document.ranking_completed_at,
            ):
                return document
            payload.update(
                {
                    "ranking_status": STAGE_STATUS_RUNNING,
                    "ranking_completed_at": None,
                    "ranking_error": None,
                }
            )

        return self._document_repo.update(
            document,
            data=payload,
            commit=False,
            refresh=False,
        )

    def mark_stage_failed(
        self,
        *,
        document: Document,
        stage: DocumentStageName,
        error_message: str | None,
    ) -> Document:
        """Mark one stage as failed unless the document already reached completion."""

        bounded_error = (error_message or "")[:2000] or None
        payload: dict[str, object] = {}
        if stage == "extraction":
            if self._is_sticky_completed(
                status=document.extraction_status,
                completed_at=document.extraction_completed_at,
            ):
                return document
            payload.update(
                {
                    "extraction_status": STAGE_STATUS_FAILED,
                    "extraction_completed_at": None,
                    "extraction_error": bounded_error,
                }
            )
        else:
            if self._is_sticky_completed(
                status=document.ranking_status,
                completed_at=document.ranking_completed_at,
            ):
                return document
            payload.update(
                {
                    "ranking_status": STAGE_STATUS_FAILED,
                    "ranking_completed_at": None,
                    "ranking_error": bounded_error,
                }
            )

        return self._document_repo.update(
            document,
            data=payload,
            commit=False,
            refresh=False,
        )

    def sync_document(
        self,
        *,
        document: Document,
        preserve_failed_stages: set[str] | None = None,
    ) -> Document:
        """Recompute and persist extraction/ranking statuses for one document."""

        preserved = preserve_failed_stages or set()
        scenes = self._list_document_scenes(document.id)
        extraction_status = self._compute_extraction_status(
            document=document, scenes=scenes
        )
        ranking_status = self._compute_ranking_status(scenes=scenes)
        now = datetime.now(timezone.utc)

        next_extraction_status, next_extraction_completed_at, next_extraction_error = (
            self._resolve_stage_values(
                current_status=document.extraction_status,
                current_completed_at=document.extraction_completed_at,
                current_error=document.extraction_error,
                target_status=extraction_status,
                preserve_failed="extraction" in preserved,
                now=now,
            )
        )
        next_ranking_status, next_ranking_completed_at, next_ranking_error = (
            self._resolve_stage_values(
                current_status=document.ranking_status,
                current_completed_at=document.ranking_completed_at,
                current_error=document.ranking_error,
                target_status=ranking_status,
                preserve_failed="ranking" in preserved,
                now=now,
            )
        )

        payload: dict[str, object] = {
            "extraction_status": next_extraction_status,
            "extraction_completed_at": next_extraction_completed_at,
            "extraction_error": next_extraction_error,
            "ranking_status": next_ranking_status,
            "ranking_completed_at": next_ranking_completed_at,
            "ranking_error": next_ranking_error,
        }

        return self._document_repo.update(
            document,
            data=payload,
            commit=False,
            refresh=False,
        )

    def sync_all_documents(self) -> int:
        """Recompute extraction/ranking statuses for every document."""

        statement = select(Document).order_by(Document.created_at.asc())
        documents = list(self._session.exec(statement))
        for document in documents:
            self.sync_document(document=document)
        self._session.commit()
        return len(documents)

    def _list_document_scenes(self, document_id: object) -> list[SceneExtraction]:
        statement = select(SceneExtraction).where(
            SceneExtraction.document_id == document_id
        )
        return list(self._session.exec(statement))

    def _compute_extraction_status(
        self,
        *,
        document: Document,
        scenes: list[SceneExtraction],
    ) -> str:
        if self._has_completed_extraction_run(document=document):
            return STAGE_STATUS_COMPLETED
        if not scenes:
            return STAGE_STATUS_PENDING
        # Any extracted scenes are sufficient to unlock image-generation mode.
        return STAGE_STATUS_COMPLETED

    def _has_completed_extraction_run(self, *, document: Document) -> bool:
        statement = (
            select(PipelineRun)
            .where(
                (
                    (PipelineRun.document_id == document.id)
                    | (PipelineRun.book_slug == document.slug)
                )
                & (PipelineRun.status == STAGE_STATUS_COMPLETED)
            )
            .order_by(
                PipelineRun.completed_at.desc(),
                PipelineRun.created_at.desc(),
            )
        )
        for run in self._session.exec(statement):
            requested = run.usage_summary.get("requested", {})
            skip_extraction = requested.get("skip_extraction")
            if skip_extraction is None:
                skip_extraction = run.config_overrides.get("skip_extraction")
            if skip_extraction is False:
                return True
        return False

    def _compute_ranking_status(self, *, scenes: list[SceneExtraction]) -> str:
        if not scenes:
            return STAGE_STATUS_PENDING

        rankable_scenes = [
            scene for scene in scenes if not self._is_discarded_scene(scene)
        ]
        if not rankable_scenes:
            # Ranking is effectively complete when refinement discarded everything.
            return STAGE_STATUS_COMPLETED

        ranked_scene_count = self._count_ranked_scenes(rankable_scenes)
        if ranked_scene_count == 0:
            return STAGE_STATUS_PENDING
        return STAGE_STATUS_COMPLETED

    def _count_ranked_scenes(self, scenes: list[SceneExtraction]) -> int:
        ranking_repo = SceneRankingRepository(self._session)
        ranked = 0
        for scene in scenes:
            if ranking_repo.get_latest_for_scene(scene.id) is not None:
                ranked += 1
        return ranked

    def _is_extraction_complete(
        self,
        *,
        document: Document,
        scenes: list[SceneExtraction],
    ) -> bool:
        if not scenes:
            return False
        if not document.source_path:
            return True

        extractor = SceneExtractor(
            session=self._session,
            config=SceneExtractionConfig(book_slug=document.slug),
        )

        try:
            resolved_path = extractor._resolve_book_path(Path(document.source_path))
            chapters = extractor._load_chapters(resolved_path)
        except Exception:
            # When source content is unavailable, treat existing extracted scenes as a
            # completed baseline so dashboard controls remain actionable.
            return True

        chunk_indexes_by_chapter: dict[int, set[int]] = defaultdict(set)
        for scene in scenes:
            chunk_indexes_by_chapter[int(scene.chapter_number)].add(
                int(scene.chunk_index)
            )

        for chapter in chapters:
            expected_indexes = {
                chunk.index for chunk in extractor._chunk_chapter(chapter)
            }
            if not expected_indexes:
                continue
            existing_indexes = chunk_indexes_by_chapter.get(chapter.number, set())
            if not expected_indexes.issubset(existing_indexes):
                return False
        return True

    @staticmethod
    def _is_discarded_scene(scene: SceneExtraction) -> bool:
        decision = (scene.refinement_decision or "").strip().lower()
        return decision == "discard"

    @staticmethod
    def _resolve_stage_values(
        *,
        current_status: str,
        current_completed_at: datetime | None,
        current_error: str | None,
        target_status: str,
        preserve_failed: bool,
        now: datetime,
    ) -> tuple[str, datetime | None, str | None]:
        if DocumentStageStatusService._is_sticky_completed(
            status=current_status,
            completed_at=current_completed_at,
        ):
            return STAGE_STATUS_COMPLETED, current_completed_at or now, None

        if preserve_failed and current_status == STAGE_STATUS_FAILED:
            return current_status, current_completed_at, current_error

        if target_status == STAGE_STATUS_COMPLETED:
            return (
                target_status,
                current_completed_at or now,
                None,
            )
        if target_status == STAGE_STATUS_STALE:
            return (
                target_status,
                current_completed_at,
                None,
            )
        return target_status, None, None

    @staticmethod
    def _is_sticky_completed(
        *,
        status: str | None,
        completed_at: datetime | None,
    ) -> bool:
        return status == STAGE_STATUS_COMPLETED or completed_at is not None
