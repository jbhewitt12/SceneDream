"""Abstract base class for prompt generation strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromptStrategy(ABC):
    """Abstract base class that all prompt generation strategies must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique name of the target provider (e.g., 'openai', 'gpt-image')."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system instruction for the LLM."""
        ...

    @abstractmethod
    def get_creative_guidance(self) -> str:
        """Return creative guidance text for prompt generation."""
        ...

    @abstractmethod
    def get_cheatsheet_path(self) -> str | None:
        """Return path to the prompting cheatsheet, or None if not used."""
        ...

    @abstractmethod
    def get_quality_objectives(
        self, variants_count: int, aspect_ratio_display: str
    ) -> str:
        """
        Return quality objectives text for the given configuration.

        Args:
            variants_count: Number of variants being generated
            aspect_ratio_display: Comma-separated display of allowed aspect ratios
        """
        ...

    @abstractmethod
    def get_style_strategy(self) -> str:
        """Return the style variation strategy text."""
        ...

    @abstractmethod
    def get_model_constraints(self) -> str:
        """Return model-specific constraints text."""
        ...

    @abstractmethod
    def get_supported_aspect_ratios(self) -> list[str]:
        """Return list of aspect ratios supported by this provider."""
        ...


__all__ = ["PromptStrategy"]
