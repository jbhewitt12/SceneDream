from uuid import uuid4

from sqlmodel import Session

from app.repositories import AppSettingsRepository, ArtStyleRepository


def test_app_settings_repository_updates_global_defaults(db: Session) -> None:
    repository = AppSettingsRepository(db)
    settings = repository.get_or_create_global(commit=True, refresh=True)

    original_scenes = settings.default_scenes_per_run
    original_mode = settings.default_prompt_art_style_mode
    original_text = settings.default_prompt_art_style_text
    original_social_posting_enabled = settings.social_posting_enabled

    assert isinstance(settings.social_posting_enabled, bool)

    updated = repository.update(
        settings,
        data={
            "default_scenes_per_run": 7,
            "default_prompt_art_style_mode": "single_style",
            "default_prompt_art_style_text": "Ink wash painting",
            "social_posting_enabled": True,
        },
        commit=True,
        refresh=True,
    )
    assert updated.default_scenes_per_run == 7
    assert updated.default_prompt_art_style_mode == "single_style"
    assert updated.default_prompt_art_style_text == "Ink wash painting"
    assert updated.social_posting_enabled is True

    restored = repository.update(
        settings,
        data={
            "default_scenes_per_run": original_scenes,
            "default_prompt_art_style_mode": original_mode,
            "default_prompt_art_style_text": original_text,
            "social_posting_enabled": original_social_posting_enabled,
        },
        commit=True,
        refresh=True,
    )
    assert restored.default_scenes_per_run == original_scenes
    assert restored.default_prompt_art_style_mode == original_mode
    assert restored.default_prompt_art_style_text == original_text
    assert restored.social_posting_enabled == original_social_posting_enabled


def test_art_style_repository_list_active_filters_inactive_rows(db: Session) -> None:
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

    active_styles = repository.list_active()
    active_display_names = {style.display_name for style in active_styles}

    assert recommended.display_name in active_display_names
    assert other.display_name in active_display_names
    assert inactive.display_name not in active_display_names

    db.delete(inactive)
    db.delete(other)
    db.delete(recommended)
    db.commit()
