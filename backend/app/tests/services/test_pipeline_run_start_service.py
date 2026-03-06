from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.schemas import PipelineRunStartRequest
from app.services.pipeline import (
    DocumentNotFoundError,
    PipelineRunStartService,
    PipelineValidationError,
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
    art_style: SimpleNamespace | None = None,
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
        service._art_style_repo,
        "get",
        lambda _art_style_id: art_style,
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

    assert exc_info.value.detail == "book_slug is required when document_id is not provided"
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


def test_resolve_pipeline_request_applies_default_image_count_and_art_style(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    art_style_id = uuid4()
    art_style = SimpleNamespace(
        id=art_style_id,
        display_name="Painterly Realism",
        is_active=True,
    )
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        default_scenes_per_run=7,
        art_style=art_style,
    )

    resolution = service.resolve_pipeline_request(
        _build_request(
            book_slug="styled-book",
            book_path="documents/styled-book.epub",
            images_for_scenes=None,
            art_style_id=art_style_id,
        )
    )

    assert resolution.args.images_for_scenes == 7
    assert resolution.args.prompt_art_style == art_style.display_name
    assert resolution.config_overrides["resolved_images_for_scenes"] == 7
    assert (
        resolution.config_overrides["resolved_prompt_art_style"]
        == art_style.display_name
    )


def test_resolve_pipeline_request_rejects_unknown_art_style(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        art_style=None,
    )

    with pytest.raises(PipelineValidationError) as exc_info:
        service.resolve_pipeline_request(_build_request(art_style_id=uuid4()))

    assert exc_info.value.detail == "Art style not found"
    assert exc_info.value.status_code == 404


def test_resolve_pipeline_request_rejects_inactive_art_style(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _configure_service(
        db=db,
        monkeypatch=monkeypatch,
        source_path_exists=True,
        art_style=SimpleNamespace(id=uuid4(), display_name="Inactive", is_active=False),
    )

    with pytest.raises(PipelineValidationError) as exc_info:
        service.resolve_pipeline_request(_build_request(art_style_id=uuid4()))

    assert exc_info.value.detail == "Art style is inactive"
    assert exc_info.value.status_code == 400
