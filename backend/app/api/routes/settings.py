"""API routes for global app settings and art-style catalog."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.core.prompt_art_style import coerce_prompt_art_style_selection
from app.repositories import AppSettingsRepository, ArtStyleRepository
from app.schemas import (
    AppSettingsBundleResponse,
    AppSettingsRead,
    AppSettingsUpdateRequest,
    ArtStyleListResponse,
    ArtStyleListsRead,
    ArtStyleListsUpdateRequest,
    ArtStyleRead,
)
from app.services.art_style import (
    ArtStyleCatalogService,
    ArtStyleCatalogValidationError,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _build_bundle_response(
    *,
    settings: AppSettingsRead,
    art_styles: list[ArtStyleRead],
) -> AppSettingsBundleResponse:
    return AppSettingsBundleResponse(settings=settings, art_styles=art_styles)


@router.get("", response_model=AppSettingsBundleResponse)
async def get_settings(*, session: SessionDep) -> AppSettingsBundleResponse:
    """Return global defaults and active art-style catalog entries."""

    settings_repo = AppSettingsRepository(session)
    art_style_repo = ArtStyleRepository(session)

    settings = settings_repo.get_or_create_global(commit=True, refresh=True)
    styles = art_style_repo.list_active()

    return _build_bundle_response(
        settings=AppSettingsRead.model_validate(settings),
        art_styles=[ArtStyleRead.model_validate(style) for style in styles],
    )


@router.patch("", response_model=AppSettingsBundleResponse)
async def update_settings(
    *,
    session: SessionDep,
    update: AppSettingsUpdateRequest,
) -> AppSettingsBundleResponse:
    """Update global defaults for scenes-per-run and prompt art style."""

    settings_repo = AppSettingsRepository(session)
    art_style_repo = ArtStyleRepository(session)
    settings = settings_repo.get_or_create_global(commit=True, refresh=True)

    payload: dict[str, object] = {}

    if "default_scenes_per_run" in update.model_fields_set:
        value = update.default_scenes_per_run
        if value is not None:
            payload["default_scenes_per_run"] = value

    style_fields = {
        "default_prompt_art_style_mode",
        "default_prompt_art_style_text",
    }
    if update.model_fields_set & style_fields:
        merged_mode = (
            update.default_prompt_art_style_mode
            if "default_prompt_art_style_mode" in update.model_fields_set
            else settings.default_prompt_art_style_mode
        )
        merged_text = (
            update.default_prompt_art_style_text
            if "default_prompt_art_style_text" in update.model_fields_set
            else settings.default_prompt_art_style_text
        )
        try:
            resolved_mode, resolved_text = coerce_prompt_art_style_selection(
                mode=merged_mode,
                text=merged_text,
                mode_field_name="default_prompt_art_style_mode",
                text_field_name="default_prompt_art_style_text",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload["default_prompt_art_style_mode"] = resolved_mode
        payload["default_prompt_art_style_text"] = resolved_text

    if payload:
        settings = settings_repo.update(
            settings,
            data=payload,
            commit=True,
            refresh=True,
        )

    styles = art_style_repo.list_active()
    return _build_bundle_response(
        settings=AppSettingsRead.model_validate(settings),
        art_styles=[ArtStyleRead.model_validate(style) for style in styles],
    )


@router.get("/art-styles", response_model=ArtStyleListResponse)
async def list_art_styles(*, session: SessionDep) -> ArtStyleListResponse:
    """List active art styles available to users."""

    repository = ArtStyleRepository(session)
    styles = repository.list_active()
    return ArtStyleListResponse(
        data=[ArtStyleRead.model_validate(style) for style in styles]
    )


@router.get("/art-style-lists", response_model=ArtStyleListsRead)
async def get_art_style_lists(*, session: SessionDep) -> ArtStyleListsRead:
    """Return recommended/other style pools as line-oriented settings arrays."""
    service = ArtStyleCatalogService(session)
    snapshot = service.get_style_lists()
    return ArtStyleListsRead(
        recommended_styles=snapshot.recommended_styles,
        other_styles=snapshot.other_styles,
        updated_at=snapshot.updated_at,
    )


@router.put("/art-style-lists", response_model=ArtStyleListsRead)
async def update_art_style_lists(
    *,
    session: SessionDep,
    update: ArtStyleListsUpdateRequest,
) -> ArtStyleListsRead:
    """Replace active recommended/other style pools from full list payloads."""
    service = ArtStyleCatalogService(session)
    try:
        snapshot = service.replace_style_lists(
            recommended_styles=update.recommended_styles,
            other_styles=update.other_styles,
        )
    except ArtStyleCatalogValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return ArtStyleListsRead(
        recommended_styles=snapshot.recommended_styles,
        other_styles=snapshot.other_styles,
        updated_at=snapshot.updated_at,
    )
