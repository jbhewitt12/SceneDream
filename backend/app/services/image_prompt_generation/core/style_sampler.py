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
    "knolling",
    "papercraft",
    "miniature diorama",
    "wood burned artwork",
    "smudged oil painting",
    "3D voxel art",
    "technical drawing",
    "Neo-Expressionist",
    "electric luminescent low-poly",
    "paper sculpture",
    "3D drawing",
    "neon cubism",
    "watercolor pixel art",
    "smudged charcoal",
    "smudged Chinese ink painting",
    "anime-style watercolor",
    "3D Pixar-style cartoon",
    "neon-line drawing",
    "isometric LEGO",
    "illuminated manuscript",
    "psychedelic art",
)

OTHER_STYLES: tuple[str, ...] = (
    "Abstract art",
    "abstract geometry",
    "Art Deco",
    "Bauhaus",
    "bokeh art",
    "Brutalism",
    "Byzantine art",
    "Celtic art",
    "chiptune visuals",
    "concept art",
    "Constructivism",
    "Cyber Folk",
    "cybernetic art",
    "cyberpunk",
    "Dadaism",
    "data art",
    "digital collage",
    "digital cubism",
    "digital Impressionism",
    "digital painting",
    "double exposure",
    "dreamy fantasy",
    "etching",
    "Expressionism",
    "Fauvism",
    "flat design",
    "fractal art",
    "Futurism",
    "glitch art",
    "Gothic art",
    "Greco-Roman art",
    "ink wash painting",
    "isometric art",
    "lithography",
    "low-poly art",
    "macabre art",
    "Magic Realism",
    "Minimalism",
    "Modernism",
    "mosaic art",
    "neon graffiti",
    "neon noir",
    "origami art",
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
    "sci-fi fantasy art",
    "scratchboard art",
    "steampunk",
    "stippling",
    "Surrealism",
    "Symbolism",
    "trompe-l'oeil",
    "Vaporwave",
    "vector art",
    "watercolor painting",
    "Zen doodle",
    "graffiti art",
    "manga style",
    "comic book style",
    "cartoon style",
    "black-and-white",
    "sepia tone",
    "vintage style",
)

BLOCKED_STYLE_TERMS: tuple[str, ...] = (
    "photorealism",
    "photorealistic",
    "hyper-realistic",
    "hyper realistic",
    "live-action",
    "live action",
    "cinematic realism",
    "realistic render",
)


class StyleSampler:
    """Sample styles for prompt generation, filtering banned terms."""

    def __init__(
        self,
        *,
        recommended_styles: Sequence[str] = RECOMMENDED_STYLES,
        other_styles: Sequence[str] = OTHER_STYLES,
        blocked_terms: Sequence[str] = BLOCKED_STYLE_TERMS,
    ) -> None:
        self._recommended_styles = tuple(recommended_styles)
        self._other_styles = tuple(other_styles)
        self._blocked_terms = tuple(term.lower() for term in blocked_terms)

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

        sampled: list[str] = []
        for style in [*recommended_choices, *other_choices]:
            if any(term in style.lower() for term in self._blocked_terms):
                continue
            sampled.append(style)

        deduped = list(dict.fromkeys(sampled))
        random.shuffle(deduped)
        return deduped


__all__ = [
    "BLOCKED_STYLE_TERMS",
    "OTHER_STYLES",
    "RECOMMENDED_STYLES",
    "StyleSampler",
]
