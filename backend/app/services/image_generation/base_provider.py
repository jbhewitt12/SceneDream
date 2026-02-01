"""Abstract base class for image generation providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GeneratedImageResult:
    """Result of an image generation request."""

    image_data: bytes | None = None
    image_url: str | None = None
    revised_prompt: str | None = None
    error: str | None = None


class ImageGenerationProvider(ABC):
    """Abstract base class that all image generation providers must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique name of this provider (e.g., 'openai')."""
        ...

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        """Return list of model identifiers supported by this provider."""
        ...

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        *,
        model: str,
        size: str,
        quality: str,
        style: str,
        response_format: str = "b64_json",
    ) -> GeneratedImageResult:
        """
        Generate an image from a text prompt.

        Args:
            prompt: The text description of the image to generate
            model: The model to use for generation
            size: Image size (e.g., '1024x1024')
            quality: Image quality (e.g., 'standard', 'hd')
            style: Image style (e.g., 'vivid', 'natural')
            response_format: Response format ('b64_json' or 'url')

        Returns:
            GeneratedImageResult with image data or error
        """
        ...

    @abstractmethod
    def get_supported_sizes(self, model: str) -> list[str]:
        """
        Return list of supported image sizes for a given model.

        Args:
            model: The model identifier

        Returns:
            List of size strings (e.g., ['1024x1024', '1024x1792', '1792x1024'])
        """
        ...

    @abstractmethod
    def validate_config(self, api_key: str | None) -> tuple[bool, str | None]:
        """
        Validate provider configuration.

        Args:
            api_key: The API key to validate (if required)

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is None.
        """
        ...


__all__ = ["ImageGenerationProvider", "GeneratedImageResult"]
