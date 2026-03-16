from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from app.schemas import PipelineRunStartRequest
from app.services.pipeline import (
    CustomRemixTarget,
    DocumentNotFoundError,
    DocumentTarget,
    PipelineExecutionConfig,
    PipelineRunStartService,
    PipelineStagePlan,
    PipelineValidationError,
    PromptExecutionOptions,
    RemixTarget,
    SceneTarget,
    SourceDocumentMissingError,
)


def _build_request(**overrides: object) -> PipelineRunStartRequest:
    payload: dict[str, object] = {
        "book_slug": "test-book",
        "book_path": "documents/test-book.epub",
        "images_for_scenes": 1,
    }
    payload.update(overrides)
    return PipelineRunStartRequest.model_validate(payload)


def _configure_service(
    *,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    source_path_exists: bool,
    existing_extractions: list[object] | None = None,
    default_scenes_per_run: int = 5,
    document_by_id: SimpleNamespace | None = None,
    document_by_slug: SimpleNamespace | None = None,
    settings: SimpleNamespace | None = None,
    sync_document_hook: Callable[..., object] | None = None,
) -> tuple[PipelineRunStartService, dict[str, Any]]:
    service = PipelineRunStartService(db)
    captured: dict[str, Any] = {}

    scenes = existing_extractions or []
    monkeypatch.setattr(service._scene_repo, "list_for_book", lambda _slug: scenes)
    monkeypatch.setattr(
        service._document_repo,
        "get",
        lambda _document_id: document_by_id,
    )
    monkeypatch.setattr(
        service._document_repo,
        "get_by_slug",
        lambda _book_slug: document_by_slug,
    )
    monkeypatch.setattr(
        service._settings_repo,
        "get_global",
        lambda: settings,
    )
    monkeypatch.setattr(
        service,
        "_source_path_exists",
        lambda _source_path: source_path_exists,
    )
    monkeypatch.setattr(
        service,
        "_resolve_default_scenes_per_run",
        lambda: default_scenes_per_run,
    )

    def _noop_sync_document(
        *,
        document: object,
        preserve_failed_stages: set[str] | None = None,
    ) -> object:
        del preserve_failed_stages
        return document

    monkeypatch.setattr(
        service._document_stage_status_service,
        "sync_document",
        sync_document_hook or _noop_sync_document,
    )

    def _capture_run_create(
        *,
        data: dict[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SimpleNamespace:
        captured["data"] = dict(data)
        captured["commit"] = commit
        captured["refresh"] = refresh
        return SimpleNamespace(id=uuid4(), **data)

    monkeypatch.setattr(service._run_repo, "create", _capture_run_create)
    return service, captured


def test_resolve_pipeline_request_uses_document_id_defaults(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        slug="doc-id-book",
        source_path="documents/doc-id-book.epub",
        extraction_status="pending",
        ranking_status="pending",
    )
    service, captured = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        document_by_id=document,
    )

    request = _build_request(document_id=document_id, book_slug=None, book_path=None)
    resolution = service.resolve_pipeline_request(request)

    assert resolution.args.book_slug == document.slug
    assert resolution.args.book_path == document.source_path
    assert resolution.args.skip_extraction is False
    assert captured["data"]["document_id"] == document_id
    assert captured["data"]["book_slug"] == document.slug
    assert resolution.config_overrides["resolved_book_slug"] == document.slug
    assert resolution.config_overrides["resolved_book_path"] == document.source_path


def test_resolve_pipeline_request_raises_when_document_not_found(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        document_by_id=None,
    )

    with pytest.raises(DocumentNotFoundError, match="Document not found"):
        service.resolve_pipeline_request(
            _build_request(document_id=uuid4(), book_slug=None, book_path=None)
        )


def test_resolve_pipeline_request_resolves_document_by_slug(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = SimpleNamespace(
        id=uuid4(),
        slug="slug-only-book",
        source_path="documents/slug-only-book.epub",
        extraction_status="pending",
        ranking_status="pending",
    )
    service, captured = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        document_by_slug=document,
    )

    resolution = service.resolve_pipeline_request(
        _build_request(
            book_slug=document.slug,
            book_path="documents/override-path.epub",
        )
    )

    assert resolution.args.book_slug == document.slug
    assert resolution.args.book_path == "documents/override-path.epub"
    assert captured["data"]["document_id"] == document.id


def test_resolve_pipeline_request_requires_book_slug_without_document_id(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
    )

    with pytest.raises(PipelineValidationError) as exc_info:
        service.resolve_pipeline_request(
            _build_request(book_slug=None, book_path=None, images_for_scenes=1)
        )

    assert (
        exc_info.value.detail
        == "book_slug is required when document_id is not provided"
    )
    assert exc_info.value.status_code == 400


def test_resolve_pipeline_request_allows_resume_when_source_missing(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=False,
        existing_extractions=[object()],
    )

    resolution = service.resolve_pipeline_request(
        _build_request(book_slug="resume-book", book_path="documents/missing.epub")
    )

    assert resolution.args.skip_extraction is True
    assert resolution.args.book_path is None
    assert resolution.config_overrides["skip_extraction"] is True
    assert "resolved_book_path" not in resolution.config_overrides


def test_resolve_pipeline_request_syncs_document_before_skip_resolution(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        slug="synced-book",
        source_path="documents/synced-book.epub",
        extraction_status="pending",
        ranking_status="pending",
    )

    def _sync_document(
        *,
        document: SimpleNamespace,
        preserve_failed_stages: set[str] | None = None,
    ) -> SimpleNamespace:
        del preserve_failed_stages
        document.extraction_status = "completed"
        document.ranking_status = "completed"
        return document

    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        document_by_id=document,
        sync_document_hook=_sync_document,
    )

    resolution = service.resolve_pipeline_request(
        _build_request(document_id=document_id, book_slug=None, book_path=None)
    )

    assert resolution.args.skip_extraction is True
    assert resolution.args.skip_ranking is True
    assert resolution.config_overrides["skip_extraction"] is True
    assert resolution.config_overrides["skip_ranking"] is True


def test_resolve_pipeline_request_syncs_completed_extraction_without_skipping_ranking(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        slug="synced-extraction-only-book",
        source_path="documents/synced-extraction-only-book.epub",
        extraction_status="pending",
        ranking_status="pending",
    )

    def _sync_document(
        *,
        document: SimpleNamespace,
        preserve_failed_stages: set[str] | None = None,
    ) -> SimpleNamespace:
        del preserve_failed_stages
        document.extraction_status = "completed"
        return document

    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        document_by_id=document,
        sync_document_hook=_sync_document,
    )

    resolution = service.resolve_pipeline_request(
        _build_request(document_id=document_id, book_slug=None, book_path=None)
    )

    assert resolution.args.skip_extraction is True
    assert resolution.args.skip_ranking is False
    assert resolution.config_overrides["skip_extraction"] is True
    assert resolution.config_overrides["skip_ranking"] is False


def test_resolve_pipeline_request_rejects_missing_source_without_resume_data(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=False,
        existing_extractions=[],
    )

    with pytest.raises(SourceDocumentMissingError) as exc_info:
        service.resolve_pipeline_request(
            _build_request(book_slug="missing-book", book_path="documents/missing.epub")
        )

    assert (
        exc_info.value.detail
        == "book_path does not exist and no extracted scenes are available to resume"
    )


def test_resolve_pipeline_request_requires_book_path_when_extraction_enabled(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=False,
        existing_extractions=[],
    )

    with pytest.raises(SourceDocumentMissingError) as exc_info:
        service.resolve_pipeline_request(_build_request(book_path=None))

    assert exc_info.value.detail == "book_path is required when extraction is enabled"
    assert exc_info.value.status_code == 400


def test_resolve_pipeline_request_preserves_explicit_skip_extraction(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=False,
        existing_extractions=[],
    )

    resolution = service.resolve_pipeline_request(
        _build_request(book_path=None, skip_extraction=True)
    )

    assert resolution.args.skip_extraction is True
    assert resolution.args.book_path is None
    assert resolution.config_overrides["skip_extraction"] is True


def test_resolve_pipeline_request_aligns_skip_extraction_with_skip_ranking(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        existing_extractions=[object()],
    )

    resolution = service.resolve_pipeline_request(
        _build_request(skip_extraction=False, skip_ranking=True)
    )

    assert resolution.args.skip_extraction is True
    assert resolution.args.skip_ranking is True
    assert resolution.config_overrides["skip_extraction"] is True


def test_resolve_pipeline_request_applies_default_image_count_and_prompt_art_style(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        default_scenes_per_run=7,
        settings=SimpleNamespace(
            default_prompt_art_style_mode="single_style",
            default_prompt_art_style_text="Painterly Realism",
        ),
    )

    resolution = service.resolve_pipeline_request(
        _build_request(
            book_slug="styled-book",
            book_path="documents/styled-book.epub",
            images_for_scenes=None,
        )
    )

    assert resolution.args.images_for_scenes == 7
    assert resolution.args.prompt_art_style_mode == "single_style"
    assert resolution.args.prompt_art_style_text == "Painterly Realism"
    assert resolution.config_overrides["resolved_images_for_scenes"] == 7
    assert resolution.config_overrides["resolved_prompt_art_style_mode"] == (
        "single_style"
    )
    assert (
        resolution.config_overrides["resolved_prompt_art_style_text"]
        == "Painterly Realism"
    )


def test_resolve_pipeline_request_accepts_random_mix_override(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        settings=SimpleNamespace(
            default_prompt_art_style_mode="single_style",
            default_prompt_art_style_text="Settings Style",
        ),
    )

    resolution = service.resolve_pipeline_request(
        _build_request(
            prompt_art_style_mode="random_mix",
            prompt_art_style_text="Ignored override",
        )
    )

    assert resolution.args.prompt_art_style_mode == "random_mix"
    assert resolution.args.prompt_art_style_text is None
    assert resolution.config_overrides["resolved_prompt_art_style_mode"] == "random_mix"
    assert resolution.config_overrides["resolved_prompt_art_style_text"] is None


def test_resolve_pipeline_request_falls_back_to_random_mix_without_settings(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        settings=None,
    )

    resolution = service.resolve_pipeline_request(_build_request())

    assert resolution.args.prompt_art_style_mode == "random_mix"
    assert resolution.args.prompt_art_style_text is None
    assert resolution.config_overrides["resolved_prompt_art_style_mode"] == "random_mix"
    assert resolution.config_overrides["resolved_prompt_art_style_text"] is None


def test_resolve_pipeline_request_rejects_missing_single_style_text_after_resolution(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        settings=SimpleNamespace(
            default_prompt_art_style_mode="single_style",
            default_prompt_art_style_text=None,
        ),
    )

    with pytest.raises(PipelineValidationError) as exc_info:
        service.resolve_pipeline_request(_build_request())

    assert (
        exc_info.value.detail
        == "prompt_art_style_text is required when prompt_art_style_mode is single_style"
    )
    assert exc_info.value.status_code == 422


# ======================================================================
# prepare_execution() tests
# ======================================================================


def _configure_prepare_service(
    *,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    source_path_exists: bool = True,
    existing_extractions: list[object] | None = None,
    default_scenes_per_run: int = 5,
    document_by_id: SimpleNamespace | None = None,
    document_by_slug: SimpleNamespace | None = None,
    settings: SimpleNamespace | None = None,
    sync_document_hook: Callable[..., object] | None = None,
    scene_by_id: dict[UUID, SimpleNamespace] | None = None,
    image_by_id: dict[UUID, SimpleNamespace] | None = None,
    prompt_by_id: dict[UUID, SimpleNamespace] | None = None,
    ranking_resume: tuple[list[UUID] | None, UUID | None] | None = None,
) -> tuple[PipelineRunStartService, dict[str, Any]]:
    """Set up PipelineRunStartService with mocks for prepare_execution tests."""
    service = PipelineRunStartService(db)
    captured: dict[str, Any] = {}

    scenes = existing_extractions or []
    monkeypatch.setattr(service._scene_repo, "list_for_book", lambda _slug: scenes)

    # Scene-by-id lookup
    _scene_lookup = scene_by_id or {}
    monkeypatch.setattr(
        service._scene_repo,
        "get",
        lambda sid: _scene_lookup.get(sid),
    )

    monkeypatch.setattr(
        service._document_repo,
        "get",
        lambda _document_id: document_by_id,
    )
    monkeypatch.setattr(
        service._document_repo,
        "get_by_slug",
        lambda _book_slug: document_by_slug,
    )
    monkeypatch.setattr(
        service._settings_repo,
        "get_global",
        lambda: settings,
    )
    monkeypatch.setattr(
        service,
        "_source_path_exists",
        lambda _source_path: source_path_exists,
    )
    monkeypatch.setattr(
        service,
        "_resolve_default_scenes_per_run",
        lambda: default_scenes_per_run,
    )

    # Mock image and prompt repos for remix/custom-remix targets
    _image_lookup = image_by_id or {}
    _prompt_lookup = prompt_by_id or {}

    from app.repositories import GeneratedImageRepository, ImagePromptRepository

    monkeypatch.setattr(
        GeneratedImageRepository,
        "get",
        lambda _self, iid: _image_lookup.get(iid),
    )
    monkeypatch.setattr(
        ImagePromptRepository,
        "get",
        lambda _self, pid: _prompt_lookup.get(pid),
    )

    def _noop_sync_document(
        *,
        document: object,
        preserve_failed_stages: set[str] | None = None,
    ) -> object:
        del preserve_failed_stages
        return document

    monkeypatch.setattr(
        service._document_stage_status_service,
        "sync_document",
        sync_document_hook or _noop_sync_document,
    )

    # Mock ranking resume
    if ranking_resume is not None:
        monkeypatch.setattr(
            service,
            "_resolve_ranking_resume",
            lambda _slug: ranking_resume,
        )
    else:
        monkeypatch.setattr(
            service,
            "_resolve_ranking_resume",
            lambda _slug: (None, None),
        )

    def _capture_run_create(
        *,
        data: dict[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SimpleNamespace:
        captured["data"] = dict(data)
        captured["commit"] = commit
        captured["refresh"] = refresh
        return SimpleNamespace(id=uuid4(), **data)

    monkeypatch.setattr(service._run_repo, "create", _capture_run_create)
    return service, captured


def _full_pipeline_config(**overrides: Any) -> PipelineExecutionConfig:
    """Build a document-target config with all stages enabled."""
    defaults: dict[str, Any] = {
        "target": DocumentTarget(
            book_slug="test-book",
            book_path="documents/test-book.epub",
        ),
        "stages": PipelineStagePlan(
            run_extraction=True,
            run_ranking=True,
            run_prompt_generation=True,
            run_image_generation=True,
        ),
        "prompt_options": PromptExecutionOptions(images_for_scenes=5),
    }
    defaults.update(overrides)
    return PipelineExecutionConfig(**defaults)


class TestPrepareDocumentTarget:
    """Tests for prepare_execution with DocumentTarget."""

    def test_creates_pending_run(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
        )

        result = service.prepare_execution(_full_pipeline_config())

        assert result.run_id is not None
        assert captured["data"]["status"] == "pending"
        assert captured["data"]["current_stage"] == "pending"
        assert captured["commit"] is True

    def test_resolves_document_id_from_target(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="doc-book",
            source_path="documents/doc-book.epub",
            extraction_status="pending",
            ranking_status="pending",
        )
        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        assert result.context.document_id == doc_id
        assert result.context.book_slug == "doc-book"
        assert captured["data"]["document_id"] == doc_id
        assert captured["data"]["book_slug"] == "doc-book"

    def test_raises_when_document_not_found(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=None,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=uuid4()),
        )
        with pytest.raises(DocumentNotFoundError):
            service.prepare_execution(config)

    def test_sticky_skip_extraction_when_completed(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="completed-book",
            source_path="documents/completed-book.epub",
            extraction_status="completed",
            ranking_status="pending",
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_extraction is False
        assert result.config.stages.run_ranking is True
        assert result.config_overrides["skip_extraction"] is True
        assert result.config_overrides["skip_ranking"] is False

    def test_sticky_skip_both_when_completed(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="fully-done-book",
            source_path="documents/fully-done-book.epub",
            extraction_status="completed",
            ranking_status="completed",
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_extraction is False
        assert result.config.stages.run_ranking is False
        assert result.config_overrides["skip_extraction"] is True
        assert result.config_overrides["skip_ranking"] is True

    def test_syncs_document_before_skip_resolution(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Sync changes doc statuses to completed; skips should follow."""
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="synced-book",
            source_path="documents/synced-book.epub",
            extraction_status="pending",
            ranking_status="pending",
        )

        def _sync(
            *,
            document: SimpleNamespace,
            preserve_failed_stages: set[str] | None = None,
        ) -> SimpleNamespace:
            del preserve_failed_stages
            document.extraction_status = "completed"
            document.ranking_status = "completed"
            return document

        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
            sync_document_hook=_sync,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_extraction is False
        assert result.config.stages.run_ranking is False

    def test_resolves_default_images_for_scenes(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            default_scenes_per_run=7,
        )

        config = _full_pipeline_config(
            prompt_options=PromptExecutionOptions(images_for_scenes=None),
        )
        result = service.prepare_execution(config)

        assert result.config.prompt_options.images_for_scenes == 7
        assert result.config_overrides["resolved_images_for_scenes"] == 7

    def test_resolves_art_style_defaults_from_settings(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            settings=SimpleNamespace(
                default_prompt_art_style_mode="single_style",
                default_prompt_art_style_text="Painterly Realism",
            ),
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.config.prompt_options.prompt_art_style_mode == "single_style"
        assert result.config.prompt_options.prompt_art_style_text == "Painterly Realism"
        assert (
            result.config_overrides["resolved_prompt_art_style_mode"] == "single_style"
        )
        assert (
            result.config_overrides["resolved_prompt_art_style_text"]
            == "Painterly Realism"
        )

    def test_falls_back_to_random_mix_without_settings(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            settings=None,
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.config.prompt_options.prompt_art_style_mode == "random_mix"
        assert result.config.prompt_options.prompt_art_style_text is None

    def test_rejects_missing_book_slug_without_document_id(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(book_slug=None, book_path=None),
        )
        with pytest.raises(PipelineValidationError, match="book_slug is required"):
            service.prepare_execution(config)

    def test_source_path_required_when_extraction_enabled(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=False,
            existing_extractions=[],
        )

        config = _full_pipeline_config(
            target=DocumentTarget(book_slug="test-book", book_path=None),
        )
        with pytest.raises(SourceDocumentMissingError):
            service.prepare_execution(config)

    def test_auto_skips_extraction_when_source_missing_but_scenes_exist(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=False,
            existing_extractions=[object()],
        )

        config = _full_pipeline_config(
            target=DocumentTarget(
                book_slug="resume-book",
                book_path="documents/missing.epub",
            ),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_extraction is False
        assert result.context.book_path is None

    def test_effective_stage_plan_is_authoritative(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The prepared config's stage plan should be the single source of truth."""
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="auth-book",
            source_path="documents/auth-book.epub",
            extraction_status="completed",
            ranking_status="pending",
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        # skip_extraction in overrides should mirror the stage plan
        assert result.config.stages.run_extraction is False
        assert result.config_overrides["skip_extraction"] is True
        # ranking was not skipped
        assert result.config.stages.run_ranking is True
        assert result.config_overrides["skip_ranking"] is False


class TestPrepareExtractionResume:
    """Tests for extraction resume metadata in prepare_execution."""

    def test_resolves_resume_from_chapter_and_chunk(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When existing scenes exist, resume state should be populated."""
        scene1 = SimpleNamespace(
            chapter_number=3,
            chunk_index=2,
            scene_number=5,
        )
        scene2 = SimpleNamespace(
            chapter_number=1,
            chunk_index=0,
            scene_number=1,
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            existing_extractions=[scene1, scene2],
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.context.extraction_resume_from_chapter == 3
        assert result.context.extraction_resume_from_chunk == 2

    def test_no_resume_when_no_existing_scenes(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            existing_extractions=[],
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.context.extraction_resume_from_chapter is None
        assert result.context.extraction_resume_from_chunk is None

    def test_no_resume_when_extraction_skipped(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When extraction is skipped, resume state should be None."""
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="skipped-book",
            source_path="documents/skipped-book.epub",
            extraction_status="completed",
            ranking_status="pending",
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        # Extraction was sticky-skipped
        assert result.config.stages.run_extraction is False
        assert result.context.extraction_resume_from_chapter is None
        assert result.context.extraction_resume_from_chunk is None


class TestPrepareRankingResume:
    """Tests for ranking resume metadata in prepare_execution."""

    def test_resolves_remaining_scene_ids(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        remaining_ids = [uuid4(), uuid4()]
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            ranking_resume=(remaining_ids, remaining_ids[0]),
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.context.ranking_scene_ids == remaining_ids
        assert result.context.ranking_resume_scene_id == remaining_ids[0]

    def test_no_ranking_resume_when_ranking_skipped(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        doc_id = uuid4()
        doc = SimpleNamespace(
            id=doc_id,
            slug="ranked-book",
            source_path="documents/ranked-book.epub",
            extraction_status="completed",
            ranking_status="completed",
        )
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            document_by_id=doc,
            ranking_resume=([uuid4()], uuid4()),
        )

        config = _full_pipeline_config(
            target=DocumentTarget(document_id=doc_id),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_ranking is False
        assert result.context.ranking_scene_ids is None
        assert result.context.ranking_resume_scene_id is None

    def test_no_ranking_resume_when_all_scenes_ranked(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            source_path_exists=True,
            ranking_resume=(None, None),
        )

        config = _full_pipeline_config()
        result = service.prepare_execution(config)

        assert result.context.ranking_scene_ids is None
        assert result.context.ranking_resume_scene_id is None


class TestPrepareSceneTarget:
    """Tests for prepare_execution with SceneTarget."""

    def test_creates_pending_run_for_scene(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        scene_id = uuid4()
        scene = SimpleNamespace(
            id=scene_id,
            book_slug="scene-book",
        )
        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            scene_by_id={scene_id: scene},
        )

        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[scene_id]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(scene_variant_count=3),
        )
        result = service.prepare_execution(config)

        assert result.run_id is not None
        assert result.context.book_slug == "scene-book"
        assert result.context.requested_image_count == 3
        assert captured["data"]["book_slug"] == "scene-book"
        assert captured["data"]["status"] == "pending"

    def test_derives_document_id_from_scene_book_slug(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        scene_id = uuid4()
        doc_id = uuid4()
        scene = SimpleNamespace(id=scene_id, book_slug="known-book")
        doc = SimpleNamespace(id=doc_id, slug="known-book")
        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            scene_by_id={scene_id: scene},
            document_by_slug=doc,
        )

        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[scene_id]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(scene_variant_count=1),
        )
        result = service.prepare_execution(config)

        assert result.context.document_id == doc_id
        assert captured["data"]["document_id"] == doc_id

    def test_rejects_missing_scene(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            scene_by_id={},
        )

        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[uuid4()]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(scene_variant_count=1),
        )
        with pytest.raises(PipelineValidationError, match="not found"):
            service.prepare_execution(config)

    def test_scene_target_does_not_run_extraction_or_ranking(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        scene_id = uuid4()
        scene = SimpleNamespace(id=scene_id, book_slug="scene-book")
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            scene_by_id={scene_id: scene},
        )

        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[scene_id]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(scene_variant_count=2),
        )
        result = service.prepare_execution(config)

        assert result.config.stages.run_extraction is False
        assert result.config.stages.run_ranking is False
        assert result.config.stages.run_prompt_generation is True
        assert result.config.stages.run_image_generation is True


class TestPrepareRemixTarget:
    """Tests for prepare_execution with RemixTarget."""

    def test_creates_pending_run_for_remix(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        image_id = uuid4()
        prompt_id = uuid4()
        image = SimpleNamespace(id=image_id, book_slug="remix-book")
        prompt = SimpleNamespace(id=prompt_id)

        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={image_id: image},
            prompt_by_id={prompt_id: prompt},
        )

        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=image_id,
                source_prompt_id=prompt_id,
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        result = service.prepare_execution(config)

        assert result.run_id is not None
        assert result.context.book_slug == "remix-book"
        assert captured["data"]["book_slug"] == "remix-book"
        assert result.config_overrides["source_image_id"] == str(image_id)
        assert result.config_overrides["source_prompt_id"] == str(prompt_id)

    def test_derives_document_id_from_image_book_slug(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        image_id = uuid4()
        prompt_id = uuid4()
        doc_id = uuid4()
        image = SimpleNamespace(id=image_id, book_slug="remix-doc-book")
        prompt = SimpleNamespace(id=prompt_id)
        doc = SimpleNamespace(id=doc_id, slug="remix-doc-book")

        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={image_id: image},
            prompt_by_id={prompt_id: prompt},
            document_by_slug=doc,
        )

        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=image_id,
                source_prompt_id=prompt_id,
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        result = service.prepare_execution(config)

        assert result.context.document_id == doc_id
        assert captured["data"]["document_id"] == doc_id

    def test_rejects_missing_source_image(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prompt_id = uuid4()
        prompt = SimpleNamespace(id=prompt_id)
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={},
            prompt_by_id={prompt_id: prompt},
        )

        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=uuid4(),
                source_prompt_id=prompt_id,
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        with pytest.raises(PipelineValidationError, match="Source image"):
            service.prepare_execution(config)

    def test_rejects_missing_source_prompt(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        image_id = uuid4()
        image = SimpleNamespace(id=image_id, book_slug="remix-book")
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={image_id: image},
            prompt_by_id={},
        )

        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=image_id,
                source_prompt_id=uuid4(),
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        with pytest.raises(PipelineValidationError, match="Source prompt"):
            service.prepare_execution(config)


class TestPrepareCustomRemixTarget:
    """Tests for prepare_execution with CustomRemixTarget."""

    def test_creates_pending_run_for_custom_remix(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        image_id = uuid4()
        prompt_id = uuid4()
        image = SimpleNamespace(id=image_id, book_slug="custom-remix-book")
        prompt = SimpleNamespace(id=prompt_id)

        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={image_id: image},
            prompt_by_id={prompt_id: prompt},
        )

        config = PipelineExecutionConfig(
            target=CustomRemixTarget(
                source_image_id=image_id,
                source_prompt_id=prompt_id,
                custom_prompt_text="My custom text",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        result = service.prepare_execution(config)

        assert result.run_id is not None
        assert result.context.book_slug == "custom-remix-book"
        assert result.config_overrides["custom_prompt_text"] == "My custom text"
        assert captured["data"]["status"] == "pending"

    def test_derives_document_id_for_custom_remix(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        image_id = uuid4()
        prompt_id = uuid4()
        doc_id = uuid4()
        image = SimpleNamespace(id=image_id, book_slug="custom-doc-book")
        prompt = SimpleNamespace(id=prompt_id)
        doc = SimpleNamespace(id=doc_id, slug="custom-doc-book")

        service, captured = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
            image_by_id={image_id: image},
            prompt_by_id={prompt_id: prompt},
            document_by_slug=doc,
        )

        config = PipelineExecutionConfig(
            target=CustomRemixTarget(
                source_image_id=image_id,
                source_prompt_id=prompt_id,
                custom_prompt_text="Custom text",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        result = service.prepare_execution(config)

        assert result.context.document_id == doc_id
        assert captured["data"]["document_id"] == doc_id


class TestPrepareValidation:
    """Tests for config validation in prepare_execution."""

    def test_rejects_invalid_config(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
        )

        config = PipelineExecutionConfig(
            target=DocumentTarget(book_slug="test"),
            stages=PipelineStagePlan(),  # no stages enabled
        )
        with pytest.raises(PipelineValidationError, match="At least one stage"):
            service.prepare_execution(config)

    def test_rejects_extraction_on_scene_target(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        service, _ = _configure_prepare_service(
            db=db,
            monkeypatch=monkeypatch,
        )

        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[uuid4()]),
            stages=PipelineStagePlan(
                run_extraction=True,
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        with pytest.raises(PipelineValidationError, match="Extraction requires"):
            service.prepare_execution(config)
