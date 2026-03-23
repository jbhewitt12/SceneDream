"""Style sampling logic for image prompt generation."""

from __future__ import annotations

import random
from collections.abc import Sequence

RECOMMENDED_STYLES: tuple[str, ...] = (
    "90's anime",
    "Ukiyo-e woodblock",
    "stained glass mosaic",
    "Art Nouveau",
    "Impressionism",
    "3D drawing",
    "watercolor",
    "smudged charcoal",
    "smudged Chinese ink painting",
    "anime-style watercolor",
    "3D Pixar-style cartoon",
    "illuminated manuscript",
    "psychedelic art",
    "double exposure",
    "fractal art",
    "gouache painting",
    "Nihonga",
    "impasto",
    "neon noir",
    "mosaic art",
)

OTHER_STYLES: tuple[str, ...] = (
    "3D voxel art",
    "neon-line drawing",
    "miniature diorama",
    "sci-fi fantasy art",
    "isometric LEGO",
    "Abstract art",
    "bokeh art",
    "Celtic art",
    "chiaroscuro",
    "concept art",
    "cyberpunk",
    "digital Impressionism",
    "digital painting",
    "dreamy fantasy",
    "flat design",
    "Futurism",
    "Greco-Roman art",
    "ink wash painting",
    "isometric art",
    "low-poly art",
    "neon graffiti",
    "technical drawing",
    "origami art",
    "paper sculpture",
    "papercraft",
    "pastel drawing",
    "pixel art",
    "Pop Art",
    "Renaissance painting",
    "stippling",
    "Vaporwave",
    "vector art",
    "watercolor painting",
    "wood burned artwork",
    "Zen doodle",
    "graffiti art",
    "manga style",
    "comic book style",
    "Tibetan thangka",
    "visionary art",
    "mandala art",
)


class StyleSampler:
    """Sample styles for prompt generation."""

    def __init__(
        self,
        *,
        recommended_styles: Sequence[str] = RECOMMENDED_STYLES,
        other_styles: Sequence[str] = OTHER_STYLES,
    ) -> None:
        self._recommended_styles = tuple(recommended_styles)
        self._other_styles = tuple(other_styles)

    def sample(self, variants_count: int) -> list[str]:
        """Sample styles for the given number of variants."""
        recommended_count = min(
            max(2, variants_count + 2),
            len(self._recommended_styles),
        )
        other_count = min(
            max(1, variants_count // 2),
            len(self._other_styles),
        )
        recommended_choices = random.sample(self._recommended_styles, recommended_count)
        other_choices = random.sample(self._other_styles, other_count)

        deduped = list(dict.fromkeys([*recommended_choices, *other_choices]))
        random.shuffle(deduped)
        return deduped


__all__ = [
    "OTHER_STYLES",
    "RECOMMENDED_STYLES",
    "StyleSampler",
]
