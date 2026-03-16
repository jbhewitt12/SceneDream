"""Repository helpers for global application settings."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from sqlmodel import Session, select

from models.app_settings import AppSettings

GLOBAL_SETTINGS_KEY = "global"


class AppSettingsRepository:
    """Provides singleton app settings read/write operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get_global(self) -> AppSettings | None:
        statement = select(AppSettings).where(
            AppSettings.singleton_key == GLOBAL_SETTINGS_KEY
        )
        return self._session.exec(statement).first()

    def get_or_create_global(
        self,
        *,
        commit: bool = False,
        refresh: bool = True,
    ) -> AppSettings:
        settings = self.get_global()
        if settings is not None:
            return settings

        settings = AppSettings(singleton_key=GLOBAL_SETTINGS_KEY)
        self._session.add(settings)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(settings)
        return settings

    def update(
        self,
        settings: AppSettings,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> AppSettings:
        for key, value in data.items():
            if key in {"id", "singleton_key"}:
                continue
            if hasattr(settings, key):
                setattr(settings, key, value)
        settings.updated_at = datetime.now(timezone.utc)
        self._session.add(settings)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(settings)
        return settings

    def default_scenes_per_run(self) -> int:
        settings = self.get_or_create_global(commit=True, refresh=True)
        value = settings.default_scenes_per_run
        return value if value > 0 else 5

    def social_posting_enabled(self) -> bool:
        settings = self.get_or_create_global(commit=True, refresh=True)
        return bool(settings.social_posting_enabled)
