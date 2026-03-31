"""Delete all database and image-file artifacts for one source document."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, delete, select

from app.services.books.book_content_service import BookContentService
from models.document import Document
from models.generated_asset import GeneratedAsset
from models.generated_image import GeneratedImage
from models.image_generation_batch import ImageGenerationBatch
from models.image_prompt import ImagePrompt
from models.pipeline_run import PipelineRun
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking
from models.social_media_post import SocialMediaPost


def _default_project_root_from_path(source_file: Path) -> Path:
    """Resolve the repository root across local and containerized layouts."""
    try:
        candidate = source_file.resolve().parents[3]
    except IndexError:
        return source_file.resolve().parent

    if candidate == Path("/"):
        try:
            return source_file.resolve().parents[2]
        except IndexError:
            return source_file.resolve().parent
    return candidate


@dataclass(slots=True)
class SourceDocumentCleanupScope:
    """All DB rows and files associated with one normalized source path."""

    normalized_source_path: str
    book_slugs: tuple[str, ...]
    documents: tuple[Document, ...]
    scenes: tuple[SceneExtraction, ...]
    scene_rankings: tuple[SceneRanking, ...]
    image_prompts: tuple[ImagePrompt, ...]
    generated_images: tuple[GeneratedImage, ...]
    social_media_posts: tuple[SocialMediaPost, ...]
    generated_assets: tuple[GeneratedAsset, ...]
    pipeline_runs: tuple[PipelineRun, ...]
    image_batches: tuple[ImageGenerationBatch, ...]
    file_paths: tuple[Path, ...]
    existing_file_count: int
    missing_file_count: int


@dataclass(slots=True)
class SourceDocumentCleanupReport:
    """Summary of the matched scope and cleanup results."""

    normalized_source_path: str
    book_slugs: tuple[str, ...]
    document_count: int
    scene_count: int
    scene_ranking_count: int
    image_prompt_count: int
    generated_image_count: int
    social_post_count: int
    generated_asset_count: int
    pipeline_run_count: int
    image_generation_batch_count: int
    targeted_file_count: int
    existing_file_count: int
    missing_file_count: int
    dry_run: bool
    files_deleted: int = 0
    directories_removed: int = 0


class SourceDocumentCleanupService:
    """Remove all persisted artifacts that belong to one source document."""

    def __init__(self, session: Session, *, project_root: Path | None = None) -> None:
        self._session = session
        self._project_root = (
            project_root or _default_project_root_from_path(Path(__file__))
        ).resolve()
        self._generated_images_root = (self._project_root / "img" / "generated").resolve()
        self._book_service = BookContentService(project_root=self._project_root)

    def cleanup_source_document(
        self,
        source_path: str | Path,
        *,
        dry_run: bool = False,
    ) -> SourceDocumentCleanupReport:
        """Delete all DB rows and image files tied to one source path."""

        normalized_source_path = self._book_service.normalize_source_path(source_path)
        scope = self._build_scope(normalized_source_path)

        files_deleted = 0
        directories_removed = 0
        if not dry_run:
            try:
                self._delete_database_rows(scope)
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise

            files_deleted, directories_removed = self._delete_files(scope.file_paths)

        return SourceDocumentCleanupReport(
            normalized_source_path=scope.normalized_source_path,
            book_slugs=scope.book_slugs,
            document_count=len(scope.documents),
            scene_count=len(scope.scenes),
            scene_ranking_count=len(scope.scene_rankings),
            image_prompt_count=len(scope.image_prompts),
            generated_image_count=len(scope.generated_images),
            social_post_count=len(scope.social_media_posts),
            generated_asset_count=len(scope.generated_assets),
            pipeline_run_count=len(scope.pipeline_runs),
            image_generation_batch_count=len(scope.image_batches),
            targeted_file_count=len(scope.file_paths),
            existing_file_count=scope.existing_file_count,
            missing_file_count=scope.missing_file_count,
            dry_run=dry_run,
            files_deleted=files_deleted,
            directories_removed=directories_removed,
        )

    def _build_scope(self, normalized_source_path: str) -> SourceDocumentCleanupScope:
        documents = tuple(
            document
            for document in self._session.exec(select(Document)).all()
            if self._normalize_path(document.source_path) == normalized_source_path
        )
        document_ids = {document.id for document in documents}

        scenes = tuple(
            scene
            for scene in self._session.exec(select(SceneExtraction)).all()
            if self._normalize_path(scene.source_book_path) == normalized_source_path
        )
        scene_ids = {scene.id for scene in scenes}
        book_slugs = tuple(sorted({scene.book_slug for scene in scenes if scene.book_slug}))

        scene_rankings = (
            tuple(
                self._session.exec(
                    select(SceneRanking).where(
                        SceneRanking.scene_extraction_id.in_(scene_ids)
                    )
                ).all()
            )
            if scene_ids
            else ()
        )
        image_prompts = (
            tuple(
                self._session.exec(
                    select(ImagePrompt).where(
                        ImagePrompt.scene_extraction_id.in_(scene_ids)
                    )
                ).all()
            )
            if scene_ids
            else ()
        )
        prompt_ids = {prompt.id for prompt in image_prompts}

        generated_images = (
            tuple(
                self._session.exec(
                    select(GeneratedImage).where(
                        GeneratedImage.scene_extraction_id.in_(scene_ids)
                    )
                ).all()
            )
            if scene_ids
            else ()
        )
        image_ids = {image.id for image in generated_images}

        social_media_posts = (
            tuple(
                self._session.exec(
                    select(SocialMediaPost).where(
                        SocialMediaPost.generated_image_id.in_(image_ids)
                    )
                ).all()
            )
            if image_ids
            else ()
        )

        referenced_pipeline_run_ids = {
            pipeline_run_id
            for pipeline_run_id in (
                *(ranking.pipeline_run_id for ranking in scene_rankings),
                *(prompt.pipeline_run_id for prompt in image_prompts),
                *(image.pipeline_run_id for image in generated_images),
            )
            if pipeline_run_id is not None
        }

        all_pipeline_runs = tuple(self._session.exec(select(PipelineRun)).all())
        pipeline_runs = tuple(
            run
            for run in all_pipeline_runs
            if self._pipeline_run_matches(
                run=run,
                normalized_source_path=normalized_source_path,
                document_ids=document_ids,
                scene_ids=scene_ids,
                prompt_ids=prompt_ids,
                image_ids=image_ids,
                referenced_pipeline_run_ids=referenced_pipeline_run_ids,
            )
        )
        pipeline_run_ids = {run.id for run in pipeline_runs}

        generated_assets = self._collect_generated_assets(
            document_ids=document_ids,
            scene_ids=scene_ids,
            prompt_ids=prompt_ids,
            pipeline_run_ids=pipeline_run_ids,
        )

        expanded_pipeline_run_ids = pipeline_run_ids | {
            asset.pipeline_run_id
            for asset in generated_assets
            if asset.pipeline_run_id is not None
        }
        if expanded_pipeline_run_ids != pipeline_run_ids:
            pipeline_runs = tuple(
                run
                for run in all_pipeline_runs
                if run.id in expanded_pipeline_run_ids
                or self._pipeline_run_matches(
                    run=run,
                    normalized_source_path=normalized_source_path,
                    document_ids=document_ids,
                    scene_ids=scene_ids,
                    prompt_ids=prompt_ids,
                    image_ids=image_ids,
                    referenced_pipeline_run_ids=referenced_pipeline_run_ids,
                )
            )
            pipeline_run_ids = {run.id for run in pipeline_runs}
            generated_assets = self._collect_generated_assets(
                document_ids=document_ids,
                scene_ids=scene_ids,
                prompt_ids=prompt_ids,
                pipeline_run_ids=pipeline_run_ids,
            )

        image_batches = tuple(
            batch
            for batch in self._session.exec(select(ImageGenerationBatch)).all()
            if self._batch_matches(
                batch=batch,
                scene_ids=scene_ids,
                prompt_ids=prompt_ids,
            )
        )

        file_paths = self._collect_file_paths(
            generated_images=generated_images,
            generated_assets=generated_assets,
            image_batches=image_batches,
            scene_ids=scene_ids,
            prompt_ids=prompt_ids,
        )
        existing_file_count = sum(
            1 for file_path in file_paths if file_path.exists() and file_path.is_file()
        )
        missing_file_count = len(file_paths) - existing_file_count

        return SourceDocumentCleanupScope(
            normalized_source_path=normalized_source_path,
            book_slugs=book_slugs,
            documents=documents,
            scenes=scenes,
            scene_rankings=scene_rankings,
            image_prompts=image_prompts,
            generated_images=generated_images,
            social_media_posts=social_media_posts,
            generated_assets=generated_assets,
            pipeline_runs=pipeline_runs,
            image_batches=image_batches,
            file_paths=file_paths,
            existing_file_count=existing_file_count,
            missing_file_count=missing_file_count,
        )

    def _collect_generated_assets(
        self,
        *,
        document_ids: set[UUID],
        scene_ids: set[UUID],
        prompt_ids: set[UUID],
        pipeline_run_ids: set[UUID],
    ) -> tuple[GeneratedAsset, ...]:
        return tuple(
            asset
            for asset in self._session.exec(select(GeneratedAsset)).all()
            if (
                (asset.document_id in document_ids if asset.document_id else False)
                or (
                    asset.scene_extraction_id in scene_ids
                    if asset.scene_extraction_id
                    else False
                )
                or (asset.image_prompt_id in prompt_ids if asset.image_prompt_id else False)
                or (asset.pipeline_run_id in pipeline_run_ids if asset.pipeline_run_id else False)
            )
        )

    def _pipeline_run_matches(
        self,
        *,
        run: PipelineRun,
        normalized_source_path: str,
        document_ids: set[UUID],
        scene_ids: set[UUID],
        prompt_ids: set[UUID],
        image_ids: set[UUID],
        referenced_pipeline_run_ids: set[UUID],
    ) -> bool:
        if run.id in referenced_pipeline_run_ids:
            return True
        if run.document_id is not None and run.document_id in document_ids:
            return True

        resolved_book_path = self._normalized_run_book_path(run)
        if resolved_book_path == normalized_source_path:
            return True

        if self._uuid_list_has_match(run.config_overrides.get("scene_ids"), scene_ids):
            return True

        source_image_id = self._coerce_uuid(run.config_overrides.get("source_image_id"))
        if source_image_id is not None and source_image_id in image_ids:
            return True

        source_prompt_id = self._coerce_uuid(
            run.config_overrides.get("source_prompt_id")
        )
        if source_prompt_id is not None and source_prompt_id in prompt_ids:
            return True

        return False

    def _batch_matches(
        self,
        *,
        batch: ImageGenerationBatch,
        scene_ids: set[UUID],
        prompt_ids: set[UUID],
    ) -> bool:
        for mapping in batch.task_mapping:
            scene_id = self._coerce_uuid(mapping.get("scene_extraction_id"))
            if scene_id is not None and scene_id in scene_ids:
                return True

            prompt_id = self._coerce_uuid(mapping.get("image_prompt_id"))
            if prompt_id is not None and prompt_id in prompt_ids:
                return True

        return False

    def _collect_file_paths(
        self,
        *,
        generated_images: tuple[GeneratedImage, ...],
        generated_assets: tuple[GeneratedAsset, ...],
        image_batches: tuple[ImageGenerationBatch, ...],
        scene_ids: set[UUID],
        prompt_ids: set[UUID],
    ) -> tuple[Path, ...]:
        file_paths: set[Path] = set()

        for image in generated_images:
            file_path = self._resolve_file_path(image.storage_path, image.file_name)
            if file_path is not None:
                file_paths.add(file_path)

        for asset in generated_assets:
            if asset.asset_type != "image":
                continue
            file_path = self._resolve_file_path(asset.storage_path, asset.file_name)
            if file_path is not None:
                file_paths.add(file_path)

        for batch in image_batches:
            for mapping in batch.task_mapping:
                scene_id = self._coerce_uuid(mapping.get("scene_extraction_id"))
                prompt_id = self._coerce_uuid(mapping.get("image_prompt_id"))
                if scene_id not in scene_ids and prompt_id not in prompt_ids:
                    continue
                file_path = self._resolve_file_path(
                    mapping.get("storage_path"),
                    mapping.get("file_name"),
                )
                if file_path is not None:
                    file_paths.add(file_path)

        return tuple(sorted(file_paths))

    def _delete_database_rows(self, scope: SourceDocumentCleanupScope) -> None:
        social_post_ids = [post.id for post in scope.social_media_posts]
        generated_image_ids = [image.id for image in scope.generated_images]
        generated_asset_ids = [asset.id for asset in scope.generated_assets]
        image_prompt_ids = [prompt.id for prompt in scope.image_prompts]
        scene_ranking_ids = [ranking.id for ranking in scope.scene_rankings]
        image_batch_ids = [batch.id for batch in scope.image_batches]
        pipeline_run_ids = [run.id for run in scope.pipeline_runs]
        scene_ids = [scene.id for scene in scope.scenes]
        document_ids = [document.id for document in scope.documents]

        if social_post_ids:
            self._session.execute(
                delete(SocialMediaPost).where(SocialMediaPost.id.in_(social_post_ids))
            )
        if generated_image_ids:
            self._session.execute(
                delete(GeneratedImage).where(GeneratedImage.id.in_(generated_image_ids))
            )
        if generated_asset_ids:
            self._session.execute(
                delete(GeneratedAsset).where(GeneratedAsset.id.in_(generated_asset_ids))
            )
        if image_prompt_ids:
            self._session.execute(
                delete(ImagePrompt).where(ImagePrompt.id.in_(image_prompt_ids))
            )
        if scene_ranking_ids:
            self._session.execute(
                delete(SceneRanking).where(SceneRanking.id.in_(scene_ranking_ids))
            )
        if image_batch_ids:
            self._session.execute(
                delete(ImageGenerationBatch).where(
                    ImageGenerationBatch.id.in_(image_batch_ids)
                )
            )
        if pipeline_run_ids:
            self._session.execute(
                delete(PipelineRun).where(PipelineRun.id.in_(pipeline_run_ids))
            )
        if scene_ids:
            self._session.execute(
                delete(SceneExtraction).where(SceneExtraction.id.in_(scene_ids))
            )
        if document_ids:
            self._session.execute(delete(Document).where(Document.id.in_(document_ids)))

    def _delete_files(self, file_paths: tuple[Path, ...]) -> tuple[int, int]:
        files_deleted = 0
        directories_removed = 0

        for file_path in file_paths:
            if not file_path.exists() or not file_path.is_file():
                continue
            file_path.unlink()
            files_deleted += 1
            directories_removed += self._remove_empty_parent_directories(file_path.parent)

        return files_deleted, directories_removed

    def _remove_empty_parent_directories(self, start_dir: Path) -> int:
        removed = 0
        current = start_dir

        while current != self._generated_images_root:
            try:
                current.relative_to(self._generated_images_root)
            except ValueError:
                break

            try:
                current.rmdir()
            except OSError:
                break

            removed += 1
            current = current.parent

        return removed

    def _normalized_run_book_path(self, run: PipelineRun) -> str | None:
        raw_path = run.config_overrides.get("resolved_book_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        return self._normalize_path(raw_path)

    def _normalize_path(self, source_path: str | Path) -> str:
        return self._book_service.normalize_source_path(source_path)

    @staticmethod
    def _coerce_uuid(value: object) -> UUID | None:
        if isinstance(value, UUID):
            return value
        if not isinstance(value, str) or not value:
            return None
        try:
            return UUID(value)
        except ValueError:
            return None

    def _uuid_list_has_match(self, value: object, candidates: set[UUID]) -> bool:
        if not isinstance(value, list):
            return False

        for item in value:
            uuid_value = self._coerce_uuid(item)
            if uuid_value is not None and uuid_value in candidates:
                return True

        return False

    def _resolve_file_path(self, storage_path: object, file_name: object) -> Path | None:
        if not isinstance(storage_path, str) or not storage_path.strip():
            return None
        if not isinstance(file_name, str) or not file_name.strip():
            return None

        candidate = (self._project_root / storage_path.strip("/") / file_name).resolve()
        try:
            candidate.relative_to(self._project_root)
        except ValueError:
            return None

        return candidate
