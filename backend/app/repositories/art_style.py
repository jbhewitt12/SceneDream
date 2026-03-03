"""Repository helpers for art style catalog persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from models.art_style import ArtStyle


class ArtStyleRepository:
    """Provides queries and mutations for art style catalog entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, art_style_id: UUID) -> ArtStyle | None:
        return self._session.get(ArtStyle, art_style_id)

    def get_by_slug(self, slug: str) -> ArtStyle | None:
        statement = select(ArtStyle).where(ArtStyle.slug == slug)
        return self._session.exec(statement).first()

    def list_active(self) -> list[ArtStyle]:
        statement = (
            select(ArtStyle)
            .where(ArtStyle.is_active.is_(True))
            .order_by(
                ArtStyle.is_recommended.desc(),
                ArtStyle.sort_order.asc(),
                ArtStyle.display_name.asc(),
            )
        )
        return list(self._session.exec(statement))

    def list_for_sampling(self) -> tuple[list[str], list[str]]:
        styles = self.list_active()
        recommended = [style.display_name for style in styles if style.is_recommended]
        other = [style.display_name for style in styles if not style.is_recommended]
        return recommended, other

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> ArtStyle:
        style = ArtStyle(**data)
        self._session.add(style)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(style)
        return style

    def update(
        self,
        style: ArtStyle,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> ArtStyle:
        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(style, key):
                setattr(style, key, value)
        style.updated_at = datetime.now(timezone.utc)
        self._session.add(style)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(style)
        return style
