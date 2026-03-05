"""Document dashboard aggregation service."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.schemas.document import (
    DocumentDashboardCounts,
    DocumentDashboardEntry,
    DocumentDashboardRunSummary,
    DocumentDashboardStages,
)
from app.services.books.book_content_service import BookContentService
from models.document import Document
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking


SUPPORTED_SOURCE_EXTENSIONS = {
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".txt",
    ".md",
    ".docx",
}


def _default_project_root_from_path(source_file: Path) -> Path:
    """Resolve the repository root across local and containerized layouts."""
    try:
        candidate = source_file.resolve().parents[3]
    except IndexError:
        return source_file.resolve().parent

    # In container images files live at /app/app/..., where parents[3] is /.
    if candidate == Path("/"):
        try:
            return source_file.resolve().parents[2]
        except IndexError:
            return source_file.resolve().parent
    return candidate


@dataclass(slots=True)
class _EntryBuilder:
    document_id: UUID | None
    slug: str
    display_name: str
    source_path: str
    source_type: str
    file_exists: bool
    ingestion_state: str | None = None
    ingestion_error: str | None = None


class DocumentDashboardService:
    """Builds merged filesystem + DB dashboard rows for source documents."""

    def __init__(self, session: Session, *, project_root: Path | None = None) -> None:
        self._session = session
        self._project_root = project_root or _default_project_root_from_path(
            Path(__file__)
        )
        self._book_service = BookContentService(project_root=self._project_root)

    def list_entries(self) -> list[DocumentDashboardEntry]:
        rows = self._build_entry_rows()
        extracted_doc, extracted_slug = self._count_extracted()
        ranked_doc, ranked_slug = self._count_ranked()
        prompted_doc, prompted_slug = self._count_prompted()
        imaged_doc, imaged_slug = self._count_imaged()
        latest_run_by_document, latest_legacy_run_by_slug = self._latest_runs()

        entries: list[DocumentDashboardEntry] = []
        for row in rows:
            counts = DocumentDashboardCounts(
                extracted=self._count_for_entry(
                    row=row,
                    by_document_id=extracted_doc,
                    by_legacy_slug=extracted_slug,
                ),
                ranked=self._count_for_entry(
                    row=row,
                    by_document_id=ranked_doc,
                    by_legacy_slug=ranked_slug,
                ),
                prompts_generated=self._count_for_entry(
                    row=row,
                    by_document_id=prompted_doc,
                    by_legacy_slug=prompted_slug,
                ),
                images_generated=self._count_for_entry(
                    row=row,
                    by_document_id=imaged_doc,
                    by_legacy_slug=imaged_slug,
                ),
            )
            stages = DocumentDashboardStages(
                extracted=counts.extracted > 0,
                ranked=counts.ranked > 0,
                prompts_generated=counts.prompts_generated > 0,
                images_generated=counts.images_generated > 0,
            )
            latest_run = self._resolve_latest_run(
                row=row,
                latest_run_by_document=latest_run_by_document,
                latest_legacy_run_by_slug=latest_legacy_run_by_slug,
            )

            entries.append(
                DocumentDashboardEntry(
                    document_id=row.document_id,
                    slug=row.slug,
                    display_name=row.display_name,
                    source_path=row.source_path,
                    source_type=row.source_type,
                    file_exists=row.file_exists,
                    ingestion_state=row.ingestion_state,
                    ingestion_error=row.ingestion_error,
                    counts=counts,
                    stages=stages,
                    last_run=latest_run,
                )
            )

        entries.sort(key=lambda entry: entry.source_path.lower())
        return entries

    def _build_entry_rows(self) -> list[_EntryBuilder]:
        rows_by_key = self._scan_documents_directory()
        statement = select(Document).order_by(Document.created_at.desc())
        for document in self._session.exec(statement):
            normalized_source_path = self._book_service.normalize_source_path(
                document.source_path
            )
            row_key = normalized_source_path
            existing = rows_by_key.get(row_key)
            if existing is None:
                existing = _EntryBuilder(
                    document_id=None,
                    slug=document.slug,
                    display_name=self._derive_display_name(
                        normalized_source_path,
                        fallback=document.slug,
                    ),
                    source_path=normalized_source_path,
                    source_type=document.source_type,
                    file_exists=self._path_exists(normalized_source_path),
                )
            existing.document_id = document.id
            existing.slug = document.slug
            existing.display_name = document.display_name or existing.display_name
            existing.source_path = normalized_source_path
            existing.source_type = document.source_type
            existing.file_exists = self._path_exists(normalized_source_path)
            existing.ingestion_state = document.ingestion_state
            existing.ingestion_error = document.ingestion_error
            rows_by_key[row_key] = existing

        return list(rows_by_key.values())

    def _scan_documents_directory(self) -> dict[str, _EntryBuilder]:
        rows: dict[str, _EntryBuilder] = {}
        documents_dir = self._project_root / "documents"
        if not documents_dir.exists():
            return rows

        for path in sorted(documents_dir.rglob("*")):
            if not path.is_file():
                continue
            extension = path.suffix.lower()
            if extension not in SUPPORTED_SOURCE_EXTENSIONS:
                continue

            source_path = path.relative_to(self._project_root).as_posix()
            rows[source_path] = _EntryBuilder(
                document_id=None,
                slug=self._slug_from_source_path(source_path),
                display_name=self._derive_display_name(source_path),
                source_path=source_path,
                source_type=extension.removeprefix("."),
                file_exists=True,
            )

        return rows

    def _count_extracted(self) -> tuple[dict[UUID, int], dict[str, int]]:
        by_document_id = self._count_by_document_id(
            select(SceneExtraction.document_id, func.count(SceneExtraction.id))
            .where(SceneExtraction.document_id.is_not(None))
            .group_by(SceneExtraction.document_id)
        )
        by_legacy_slug = self._count_by_legacy_slug(
            select(SceneExtraction.book_slug, func.count(SceneExtraction.id))
            .where(SceneExtraction.document_id.is_(None))
            .group_by(SceneExtraction.book_slug)
        )
        return by_document_id, by_legacy_slug

    def _count_ranked(self) -> tuple[dict[UUID, int], dict[str, int]]:
        by_document_id = self._count_by_document_id(
            select(SceneExtraction.document_id, func.count(SceneRanking.id))
            .select_from(SceneRanking)
            .join(
                SceneExtraction,
                SceneRanking.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_not(None))
            .group_by(SceneExtraction.document_id)
        )
        by_legacy_slug = self._count_by_legacy_slug(
            select(SceneExtraction.book_slug, func.count(SceneRanking.id))
            .select_from(SceneRanking)
            .join(
                SceneExtraction,
                SceneRanking.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_(None))
            .group_by(SceneExtraction.book_slug)
        )
        return by_document_id, by_legacy_slug

    def _count_prompted(self) -> tuple[dict[UUID, int], dict[str, int]]:
        by_document_id = self._count_by_document_id(
            select(SceneExtraction.document_id, func.count(ImagePrompt.id))
            .select_from(ImagePrompt)
            .join(
                SceneExtraction,
                ImagePrompt.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_not(None))
            .group_by(SceneExtraction.document_id)
        )
        by_legacy_slug = self._count_by_legacy_slug(
            select(SceneExtraction.book_slug, func.count(ImagePrompt.id))
            .select_from(ImagePrompt)
            .join(
                SceneExtraction,
                ImagePrompt.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_(None))
            .group_by(SceneExtraction.book_slug)
        )
        return by_document_id, by_legacy_slug

    def _count_imaged(self) -> tuple[dict[UUID, int], dict[str, int]]:
        by_document_id = self._count_by_document_id(
            select(SceneExtraction.document_id, func.count(GeneratedImage.id))
            .select_from(GeneratedImage)
            .join(
                SceneExtraction,
                GeneratedImage.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_not(None))
            .group_by(SceneExtraction.document_id)
        )
        by_legacy_slug = self._count_by_legacy_slug(
            select(SceneExtraction.book_slug, func.count(GeneratedImage.id))
            .select_from(GeneratedImage)
            .join(
                SceneExtraction,
                GeneratedImage.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.document_id.is_(None))
            .group_by(SceneExtraction.book_slug)
        )
        return by_document_id, by_legacy_slug

    def _count_by_document_id(self, statement: object) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        for document_id, count in self._session.exec(statement):
            if document_id is None:
                continue
            counts[document_id] = int(count or 0)
        return counts

    def _count_by_legacy_slug(self, statement: object) -> dict[str, int]:
        counts: dict[str, int] = {}
        for slug, count in self._session.exec(statement):
            if slug is None:
                continue
            counts[slug] = int(count or 0)
        return counts

    def _count_for_entry(
        self,
        *,
        row: _EntryBuilder,
        by_document_id: dict[UUID, int],
        by_legacy_slug: dict[str, int],
    ) -> int:
        if row.document_id is not None:
            return int(by_document_id.get(row.document_id, 0))
        return int(by_legacy_slug.get(row.slug, 0))

    def _latest_runs(
        self,
    ) -> tuple[dict[UUID, PipelineRun], dict[str, PipelineRun]]:
        statement = select(PipelineRun).order_by(PipelineRun.created_at.desc())
        latest_by_document: dict[UUID, PipelineRun] = {}
        latest_by_legacy_slug: dict[str, PipelineRun] = {}

        for run in self._session.exec(statement):
            if run.document_id is not None and run.document_id not in latest_by_document:
                latest_by_document[run.document_id] = run
                continue
            if run.document_id is None and run.book_slug:
                if run.book_slug not in latest_by_legacy_slug:
                    latest_by_legacy_slug[run.book_slug] = run

        return latest_by_document, latest_by_legacy_slug

    def _resolve_latest_run(
        self,
        *,
        row: _EntryBuilder,
        latest_run_by_document: dict[UUID, PipelineRun],
        latest_legacy_run_by_slug: dict[str, PipelineRun],
    ) -> DocumentDashboardRunSummary | None:
        run_by_document = (
            latest_run_by_document.get(row.document_id)
            if row.document_id is not None
            else None
        )
        run_by_slug = latest_legacy_run_by_slug.get(row.slug)
        selected = self._newest_run(run_by_document, run_by_slug)
        if selected is None:
            return None
        return DocumentDashboardRunSummary(
            id=selected.id,
            status=selected.status,
            current_stage=selected.current_stage,
            error_message=selected.error_message,
            usage_summary=selected.usage_summary or {},
            started_at=selected.started_at,
            completed_at=selected.completed_at,
            created_at=selected.created_at,
            updated_at=selected.updated_at,
        )

    @staticmethod
    def _newest_run(
        first: PipelineRun | None, second: PipelineRun | None
    ) -> PipelineRun | None:
        if first is None:
            return second
        if second is None:
            return first
        if first.created_at >= second.created_at:
            return first
        return second

    def _path_exists(self, source_path: str) -> bool:
        raw = Path(source_path).expanduser()
        if raw.is_absolute():
            return raw.exists()
        return (self._project_root / raw).exists()

    @staticmethod
    def _derive_display_name(source_path: str, *, fallback: str | None = None) -> str:
        name = Path(source_path).stem.strip()
        if name:
            return name
        return fallback or source_path

    @staticmethod
    def _slug_from_source_path(source_path: str) -> str:
        path = Path(source_path)
        base = path.stem or path.name
        return DocumentDashboardService._slugify(base)

    @staticmethod
    def _slugify(text: str) -> str:
        normalized = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        lowered = normalized.lower()
        tokens = lowered.split()
        if not tokens:
            tokens = ["scene"]
        candidate = "-".join(tokens[:6])
        candidate = re.sub(r"[^a-z0-9-]", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate or "scene"
