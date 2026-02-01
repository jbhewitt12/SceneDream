"""Registry for prompt generation strategies."""

from __future__ import annotations

from .base import PromptStrategy


class PromptStrategyNotFoundError(KeyError):
    """Raised when a requested strategy is not registered."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        available = PromptStrategyRegistry.list_strategies()
        available_str = ", ".join(available) if available else "none"
        super().__init__(
            f"No prompt strategy registered for provider '{provider_name}'. "
            f"Available strategies: {available_str}"
        )


class PromptStrategyRegistry:
    """Registry for discovering and selecting prompt generation strategies."""

    _strategies: dict[str, PromptStrategy] = {}

    @classmethod
    def register(cls, strategy: PromptStrategy) -> None:
        """
        Register a prompt generation strategy.

        Args:
            strategy: The strategy instance to register
        """
        cls._strategies[strategy.provider_name] = strategy

    @classmethod
    def get(cls, provider_name: str) -> PromptStrategy:
        """
        Get a registered strategy by provider name.

        Args:
            provider_name: The provider name (e.g., 'openai', 'gpt-image')

        Returns:
            The strategy instance

        Raises:
            PromptStrategyNotFoundError: If no strategy is registered for the provider
        """
        strategy = cls._strategies.get(provider_name)
        if strategy is None:
            raise PromptStrategyNotFoundError(provider_name)
        return strategy

    @classmethod
    def list_strategies(cls) -> list[str]:
        """
        List all registered strategy provider names.

        Returns:
            List of registered provider names
        """
        return list(cls._strategies.keys())

    @classmethod
    def has_strategy(cls, provider_name: str) -> bool:
        """
        Check if a strategy is registered for the given provider.

        Args:
            provider_name: The provider name to check

        Returns:
            True if a strategy is registered, False otherwise
        """
        return provider_name in cls._strategies


__all__ = ["PromptStrategyNotFoundError", "PromptStrategyRegistry"]
