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
    "Cubism",
    "smudged oil painting",
    "3D voxel art",
    "Neo-Expressionist",
    "electric luminescent low-poly",
    "3D drawing",
    "neon cubism",
    "watercolor pixel art",
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
)

OTHER_STYLES: tuple[str, ...] = (
    "neon-line drawing",
    "miniature diorama",
    "sci-fi fantasy art",
    "isometric LEGO",
    "knolling",
    "Abstract art",
    "abstract geometry",
    "Art Deco",
    "bokeh art",
    "Brutalism",
    "Byzantine art",
    "Celtic art",
    "chiaroscuro",
    "chiptune visuals",
    "concept art",
    "Constructivism",
    "Cyber Folk",
    "cybernetic art",
    "cyberpunk",
    "digital collage",
    "digital cubism",
    "digital Impressionism",
    "digital painting",
    "dreamy fantasy",
    "etching",
    "Expressionism",
    "Fauvism",
    "flat design",
    "Futurism",
    "glitch art",
    "Gothic art",
    "Greco-Roman art",
    "ink wash painting",
    "isometric art",
    "lithography",
    "low-poly art",
    "Magic Realism",
    "Minimalism",
    "Modernism",
    "mosaic art",
    "neon graffiti",
    "technical drawing",
    "origami art",
    "paper sculpture",
    "papercraft",
    "parallax art",
    "pastel drawing",
    "pixel art",
    "pointillism",
    "polyart",
    "Pop Art",
    "Renaissance painting",
    "Baroque painting",
    "Retro Wave",
    "Romanticism",
    "steampunk",
    "stippling",
    "Surrealism",
    "Symbolism",
    "trompe-l'oeil",
    "Vaporwave",
    "vector art",
    "watercolor painting",
    "wood burned artwork",
    "Zen doodle",
    "graffiti art",
    "manga style",
    "comic book style",
    "cartoon style",
    "black-and-white",
    "sepia tone",
    "vintage style",
    "Dutch Golden Age",
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
