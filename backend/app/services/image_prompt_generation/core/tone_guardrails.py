"""Tone guardrails for image prompt generation."""

from __future__ import annotations

from models.scene_extraction import SceneExtraction

CULTURE_BOOK_MARKERS: tuple[str, ...] = (
    "consider-phlebas",
    "player-of-games",
    "use-of-weapons",
    "excession",
    "inversions",
    "look-to-windward",
    "matter",
    "surface-detail",
    "hydrogen-sonata",
    "state-of-the-art",
)


class ToneGuardrails:
    """Generate tone guardrails text for prompts."""

    def __init__(
        self,
        *,
        culture_book_markers: tuple[str, ...] = CULTURE_BOOK_MARKERS,
    ) -> None:
        self._culture_book_markers = culture_book_markers

    def get_guardrails_text(self) -> str:
        """Return the standard tone guardrails text block."""
        return (
            "- Avoid verbs and adjectives tied to fear, injury, or desperation (e.g., cowering, engulfed, frantic).\n"
            "- Express intensity through environmental motion, lighting, scale, or symbolic contrast rather than explicit violence.\n"
            "- When children or civilians appear, depict them in celebratory, inquisitive, or protected contexts.\n"
            "- Treat mythical or technological forces as awe-inspiring, mystical, or enigmatic instead of menacing.\n"
            "- Let wonder, serenity, or purposeful dynamism be the prevailing mood even when the scene hints at conflict."
        )

    def get_book_specific_guidance(self, scene: SceneExtraction) -> str | None:
        """Return book-specific guidance if applicable."""
        if self._is_culture_book(scene):
            return (
                " For Iain M. Banks Culture-universe scenes that mention drones, avoid using the word 'drone'. "
                "Describe them as elegant autonomous anti-gravity companions—floating AI assistants, hovering service bots, "
                "sentient metallic orbs, or compact anti-grav craft—instead of the word 'drone'."
            )
        return None

    def _is_culture_book(self, scene: SceneExtraction) -> bool:
        """Heuristic to detect Iain M. Banks Culture books by slug/path markers."""
        slug = (scene.book_slug or "").lower()
        path_hint = (scene.source_book_path or "").lower()
        haystack = f"{slug} {path_hint}"
        return any(marker in haystack for marker in self._culture_book_markers)


__all__ = [
    "CULTURE_BOOK_MARKERS",
    "ToneGuardrails",
]
