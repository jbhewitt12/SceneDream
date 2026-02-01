"""Registry for image generation providers."""

from app.services.image_generation.base_provider import ImageGenerationProvider


class ProviderRegistry:
    """Registry for discovering and selecting image generation providers."""

    _providers: dict[str, ImageGenerationProvider] = {}

    @classmethod
    def register(cls, provider: ImageGenerationProvider) -> None:
        """
        Register an image generation provider.

        Args:
            provider: The provider instance to register
        """
        cls._providers[provider.provider_name] = provider

    @classmethod
    def get(cls, name: str) -> ImageGenerationProvider | None:
        """
        Get a registered provider by name.

        Args:
            name: The provider name (e.g., 'openai')

        Returns:
            The provider instance, or None if not found
        """
        return cls._providers.get(name)

    @classmethod
    def list_providers(cls) -> list[str]:
        """
        List all registered provider names.

        Returns:
            List of registered provider names
        """
        return list(cls._providers.keys())


__all__ = ["ProviderRegistry"]
