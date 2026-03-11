"""Critical constraints for image prompt generation."""

from __future__ import annotations

from collections.abc import Sequence


class CriticalConstraints:
    """Generate critical constraint text blocks for prompts."""

    def __init__(
        self,
        *,
        allowed_aspect_ratios: Sequence[str],
    ) -> None:
        self._allowed_aspect_ratios = tuple(allowed_aspect_ratios)

    @property
    def allowed_aspect_ratios(self) -> tuple[str, ...]:
        """Return the allowed aspect ratios."""
        return self._allowed_aspect_ratios

    @property
    def aspect_ratio_display(self) -> str:
        """Return comma-separated display string of allowed aspect ratios."""
        return ", ".join(self._allowed_aspect_ratios)

    def get_constraints_text(self) -> str:
        """Return the critical constraints text block."""
        return (
            "- Select clear, intentional visual treatments that match the excerpt's tone and setting.\n"
            f"- Attributes.aspect_ratio must be exactly one of: {self.aspect_ratio_display}.\n"
            "- Ensure style_tags include the chosen medium or technique.\n"
            "- CRITICAL: Never include character names, proper nouns, or invented terminology from the source material in prompt_text. "
            "The image model has no knowledge of the book and cannot interpret names like 'Navani' or fantasy terms like 'gloryspren'. "
            "Instead, describe characters by their visual appearance (e.g., 'a regal woman crowned in gold', 'a young warrior in blue plate armor') "
            "and translate invented concepts into their visual manifestations (e.g., 'rotating golden luminescent rings' instead of 'gloryspren', "
            "'smoky blue ethereal halos' instead of 'awspren'). The prompt must be fully interpretable by someone who has never read the book."
        )


__all__ = [
    "CriticalConstraints",
]
