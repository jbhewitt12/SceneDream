from uuid import uuid4

from sqlmodel import Session

from app.repositories import AppSettingsRepository, ArtStyleRepository


def test_app_settings_repository_updates_global_defaults(db: Session) -> None:
    repository = AppSettingsRepository(db)
    settings = repository.get_or_create_global(commit=True, refresh=True)

    original_scenes = settings.default_scenes_per_run
    original_style_id = settings.default_art_style_id

    updated = repository.update(
        settings,
        data={"default_scenes_per_run": 7},
        commit=True,
        refresh=True,
    )
    assert updated.default_scenes_per_run == 7

    restored = repository.update(
        settings,
        data={
            "default_scenes_per_run": original_scenes,
            "default_art_style_id": original_style_id,
        },
        commit=True,
        refresh=True,
    )
    assert restored.default_scenes_per_run == original_scenes
    assert restored.default_art_style_id == original_style_id


def test_art_style_repository_sampling_filters_inactive_rows(db: Session) -> None:
    repository = ArtStyleRepository(db)
    suffix = uuid4().hex[:8]

    recommended = repository.create(
        data={
            "slug": f"test-style-recommended-{suffix}",
            "display_name": f"Test Recommended {suffix}",
            "is_recommended": True,
            "is_active": True,
            "sort_order": 99990,
        },
        commit=True,
        refresh=True,
    )
    other = repository.create(
        data={
            "slug": f"test-style-other-{suffix}",
            "display_name": f"Test Other {suffix}",
            "is_recommended": False,
            "is_active": True,
            "sort_order": 99991,
        },
        commit=True,
        refresh=True,
    )
    inactive = repository.create(
        data={
            "slug": f"test-style-inactive-{suffix}",
            "display_name": f"Test Inactive {suffix}",
            "is_recommended": True,
            "is_active": False,
            "sort_order": 99992,
        },
        commit=True,
        refresh=True,
    )

    recommended_styles, other_styles = repository.list_for_sampling()
    assert recommended.display_name in recommended_styles
    assert other.display_name in other_styles
    assert inactive.display_name not in recommended_styles
    assert inactive.display_name not in other_styles

    db.delete(inactive)
    db.delete(other)
    db.delete(recommended)
    db.commit()
