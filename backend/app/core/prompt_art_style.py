"""Shared prompt art-style mode helpers."""

from __future__ import annotations

from typing import Literal, TypeAlias

PROMPT_ART_STYLE_MODE_RANDOM_MIX = "random_mix"
PROMPT_ART_STYLE_MODE_SINGLE_STYLE = "single_style"
PROMPT_ART_STYLE_MODES = {
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PROMPT_ART_STYLE_MODE_SINGLE_STYLE,
}

PromptArtStyleMode: TypeAlias = Literal[
    "random_mix",
    "single_style",
]


def normalize_prompt_art_style_text(value: str | None) -> str | None:
    """Trim style text and collapse blanks to ``None``."""

    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def coerce_prompt_art_style_selection(
    *,
    mode: str | None,
    text: str | None,
    mode_field_name: str = "prompt_art_style_mode",
    text_field_name: str = "prompt_art_style_text",
) -> tuple[str, str | None]:
    """Validate and normalize an art-style mode/text pair."""

    resolved_mode = mode or PROMPT_ART_STYLE_MODE_RANDOM_MIX
    normalized_text = normalize_prompt_art_style_text(text)

    if resolved_mode not in PROMPT_ART_STYLE_MODES:
        raise ValueError(
            f"{mode_field_name} must be one of: "
            f"{PROMPT_ART_STYLE_MODE_RANDOM_MIX}, {PROMPT_ART_STYLE_MODE_SINGLE_STYLE}"
        )

    if resolved_mode == PROMPT_ART_STYLE_MODE_RANDOM_MIX:
        return resolved_mode, None

    if normalized_text is None:
        raise ValueError(
            f"{text_field_name} is required when {mode_field_name} is single_style"
        )

    return resolved_mode, normalized_text
