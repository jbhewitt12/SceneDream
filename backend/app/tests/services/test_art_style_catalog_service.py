import re
from uuid import UUID

import pytest
from sqlmodel import Session

from app.repositories import AppSettingsRepository, ArtStyleRepository
from app.services.art_style import (
    ArtStyleCatalogService,
    ArtStyleCatalogValidationError,
)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return slug or "style"


def _snapshot_state(db: Session) -> tuple[dict[str, list[str]], UUID | None]:
    service = ArtStyleCatalogService(db)
    lists = service.get_style_lists()
    settings = AppSettingsRepository(db).get_or_create_global(commit=True, refresh=True)
    return (
        {
            "recommended_styles": list(lists.recommended_styles),
            "other_styles": list(lists.other_styles),
        },
        settings.default_art_style_id,
    )


def _restore_state(
    db: Session,
    *,
    recommended_styles: list[str],
    other_styles: list[str],
    default_art_style_id: UUID | None,
) -> None:
    service = ArtStyleCatalogService(db)
    service.replace_style_lists(
        recommended_styles=recommended_styles,
        other_styles=other_styles,
    )
    settings_repo = AppSettingsRepository(db)
    settings = settings_repo.get_or_create_global(commit=False, refresh=True)
    settings_repo.update(
        settings,
        data={"default_art_style_id": default_art_style_id},
        commit=True,
        refresh=True,
    )


def test_replace_style_lists_dedupes_reorders_and_deactivates_rows(db: Session) -> None:
    snapshot, original_default = _snapshot_state(db)
    target_to_deactivate = (
        snapshot["recommended_styles"][0]
        if snapshot["recommended_styles"]
        else snapshot["other_styles"][0]
    )

    service = ArtStyleCatalogService(db)
    style_repo = ArtStyleRepository(db)

    try:
        result = service.replace_style_lists(
            recommended_styles=[
                "  Alpha Sketch  ",
                "Beta Vision",
                "Alpha Sketch",
                "Shared Palette",
            ],
            other_styles=[
                "shared palette",
                "Gamma Ink",
                "",
                "Beta Vision",
                "Delta Etching",
            ],
        )

        assert result.recommended_styles == [
            "Alpha Sketch",
            "Beta Vision",
            "Shared Palette",
        ]
        assert result.other_styles == ["Gamma Ink", "Delta Etching"]

        active_styles = style_repo.list_active()
        assert [style.display_name for style in active_styles] == [
            "Alpha Sketch",
            "Beta Vision",
            "Shared Palette",
            "Gamma Ink",
            "Delta Etching",
        ]

        inactivated_style = style_repo.get_by_slug(_slugify(target_to_deactivate))
        assert inactivated_style is not None
        assert inactivated_style.is_active is False

        again = service.replace_style_lists(
            recommended_styles=[
                "Alpha Sketch",
                "Beta Vision",
                "Shared Palette",
            ],
            other_styles=["Gamma Ink", "Delta Etching"],
        )
        assert again.recommended_styles == result.recommended_styles
        assert again.other_styles == result.other_styles
        assert len(style_repo.list_active()) == 5
    finally:
        _restore_state(
            db,
            recommended_styles=snapshot["recommended_styles"],
            other_styles=snapshot["other_styles"],
            default_art_style_id=original_default,
        )


def test_replace_style_lists_resets_invalid_default_to_first_recommended(
    db: Session,
) -> None:
    snapshot, original_default = _snapshot_state(db)
    settings_repo = AppSettingsRepository(db)
    service = ArtStyleCatalogService(db)
    style_repo = ArtStyleRepository(db)

    try:
        result = service.replace_style_lists(
            recommended_styles=["Fresh Default", "Second Choice"],
            other_styles=["Auxiliary Style"],
        )

        settings = settings_repo.get_or_create_global(commit=False, refresh=True)
        assert settings.default_art_style_id is not None
        default_style = style_repo.get(settings.default_art_style_id)
        assert default_style is not None
        assert default_style.display_name == "Fresh Default"
        assert result.recommended_styles[0] == "Fresh Default"
    finally:
        _restore_state(
            db,
            recommended_styles=snapshot["recommended_styles"],
            other_styles=snapshot["other_styles"],
            default_art_style_id=original_default,
        )


def test_replace_style_lists_rejects_empty_catalog(db: Session) -> None:
    service = ArtStyleCatalogService(db)

    with pytest.raises(ArtStyleCatalogValidationError):
        service.replace_style_lists(
            recommended_styles=["  "],
            other_styles=[],
        )
