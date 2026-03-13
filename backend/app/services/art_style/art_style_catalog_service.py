"""Transactional list-sync helpers for art style catalog settings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from sqlmodel import Session

from app.repositories import AppSettingsRepository, ArtStyleRepository
from models.art_style import ArtStyle

_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class ArtStyleCatalogValidationError(ValueError):
    """Raised when an art-style catalog update payload is invalid."""


@dataclass(slots=True, frozen=True)
class ArtStyleListsSnapshot:
    """Current active style lists split by recommended vs other."""

    recommended_styles: list[str]
    other_styles: list[str]
    updated_at: datetime


class ArtStyleCatalogService:
    """Reads and atomically syncs editable art-style list settings."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings_repo = AppSettingsRepository(session)
        self._style_repo = ArtStyleRepository(session)

    def get_style_lists(self) -> ArtStyleListsSnapshot:
        """Return active style lists in deterministic display order."""
        styles = self._style_repo.list_active()
        return self._build_snapshot(styles)

    def replace_style_lists(
        self,
        *,
        recommended_styles: list[str],
        other_styles: list[str],
    ) -> ArtStyleListsSnapshot:
        """Replace active catalog entries from line-oriented settings payloads."""
        normalized_recommended = self._dedupe_styles(recommended_styles)
        normalized_other = self._dedupe_styles(
            other_styles, blocked_slugs={self._slugify(value) for value in normalized_recommended}
        )

        if not normalized_recommended and not normalized_other:
            raise ArtStyleCatalogValidationError(
                "At least one art style is required across recommended and other lists."
            )

        now = datetime.now(timezone.utc)

        try:
            existing_by_slug = {
                style.slug: style for style in self._style_repo.list_all()
            }
            active_slugs: set[str] = set()

            combined_rows: list[tuple[str, bool]] = [
                *[(name, True) for name in normalized_recommended],
                *[(name, False) for name in normalized_other],
            ]

            for sort_order, (display_name, is_recommended) in enumerate(combined_rows):
                slug = self._slugify(display_name)
                active_slugs.add(slug)
                style = existing_by_slug.get(slug)
                if style is None:
                    style = self._style_repo.create(
                        data={
                            "slug": slug,
                            "display_name": display_name,
                            "description": None,
                            "is_recommended": is_recommended,
                            "is_active": True,
                            "sort_order": sort_order,
                        },
                        commit=False,
                        refresh=False,
                    )
                    existing_by_slug[slug] = style
                    continue

                self._style_repo.update(
                    style,
                    data={
                        "display_name": display_name,
                        "is_recommended": is_recommended,
                        "is_active": True,
                        "sort_order": sort_order,
                    },
                    commit=False,
                    refresh=False,
                )

            for style in existing_by_slug.values():
                if style.slug in active_slugs or not style.is_active:
                    continue
                self._style_repo.update(
                    style,
                    data={"is_active": False},
                    commit=False,
                    refresh=False,
                )

            active_styles = self._style_repo.list_active()
            self._session.commit()
            return self._build_snapshot(active_styles, fallback_updated_at=now)
        except Exception:
            self._session.rollback()
            raise

    def _build_snapshot(
        self,
        styles: list[ArtStyle],
        *,
        fallback_updated_at: datetime | None = None,
    ) -> ArtStyleListsSnapshot:
        recommended = [style.display_name for style in styles if style.is_recommended]
        other = [style.display_name for style in styles if not style.is_recommended]
        if styles:
            updated_at = max(style.updated_at for style in styles)
        elif fallback_updated_at is not None:
            updated_at = fallback_updated_at
        else:
            updated_at = self._settings_repo.get_or_create_global(
                commit=False, refresh=True
            ).updated_at
        return ArtStyleListsSnapshot(
            recommended_styles=recommended,
            other_styles=other,
            updated_at=updated_at,
        )

    def _dedupe_styles(
        self,
        values: list[str],
        *,
        blocked_slugs: set[str] | None = None,
    ) -> list[str]:
        seen = set(blocked_slugs or set())
        normalized: list[str] = []
        for raw in values:
            candidate = raw.strip()
            if not candidate:
                continue
            slug = self._slugify(candidate)
            if slug in seen:
                continue
            seen.add(slug)
            normalized.append(candidate)
        return normalized

    def _slugify(self, value: str) -> str:
        slug = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
        return slug or "style"
