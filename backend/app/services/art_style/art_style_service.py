"""Service helpers for art style business rules."""

from __future__ import annotations

from sqlmodel import Session

from app.repositories.art_style import ArtStyleRepository


class ArtStyleService:
    """Provides business logic around art style selection."""

    def __init__(self, session: Session) -> None:
        self._art_style_repo = ArtStyleRepository(session)

    def get_sampling_distribution(self) -> tuple[list[str], list[str]]:
        """Return active styles split into recommended and other display names."""
        styles = self._art_style_repo.list_active()
        recommended = [style.display_name for style in styles if style.is_recommended]
        other = [style.display_name for style in styles if not style.is_recommended]
        return recommended, other
