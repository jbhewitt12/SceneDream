# gpt_image_api.py
#
# This Python module provides a provider for OpenAI's GPT Image models
# (gpt-image-1.5 and related variants), which power high-fidelity
# image generation in the OpenAI API.
#
# Key differences from DALL-E 3:
# - Models: gpt-image-1.5 (best quality), gpt-image-1, gpt-image-1-mini
# - Always returns base64-encoded image data (no expiring URLs)
# - Supports n up to 10 images per request
# - New size options including 'auto' and 1536 resolutions
# - Quality: 'high' (recommended for fidelity), 'medium', 'low', 'auto'
# - No 'style' parameter (vivid/natural)
# - Additional options like output_format (png/jpeg/webp)
# - Much longer prompt limit (~32k characters)
#
# Requirements: Same as your existing DalleProvider (OpenAI API key, Python 3.8+)

from __future__ import annotations

import asyncio
import base64
import os

from openai import OpenAI

from app.services.image_generation.base_provider import (
    GeneratedImageResult,
    ImageGenerationProvider,
)
from app.services.image_generation.provider_registry import ProviderRegistry


class GptImageProvider(ImageGenerationProvider):
    """OpenAI GPT Image (1.5 family) image generation provider."""

    SIZES = ["1024x1024", "1024x1536", "1536x1024", "auto"]
    QUALITIES = ["auto", "high", "medium", "low"]
    OUTPUT_FORMATS = ["png", "jpeg", "webp"]

    @property
    def provider_name(self) -> str:
        return "openai_gpt_image"

    @property
    def supported_models(self) -> list[str]:
        return ["gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"]

    def get_supported_sizes(self, model: str) -> list[str]:
        return self.SIZES

    def validate_config(self, api_key: str | None) -> tuple[bool, str | None]:
        if not api_key:
            return False, "OpenAI API key is required"
        if not api_key.startswith("sk-"):
            return False, "Invalid OpenAI API key format"
        return True, None

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str = "gpt-image-1.5",
        size: str = "1024x1024",
        quality: str = "high",
        style: str = "vivid",  # Ignored for GPT Image models
        response_format: str = "b64_json",  # Ignored - always returns base64
        output_format: str = "png",
        api_key: str | None = None,
    ) -> GeneratedImageResult:
        """
        Generate an image using OpenAI's GPT Image models.

        Args:
            prompt: Text description of the desired image
            model: Model to use (gpt-image-1.5, gpt-image-1, gpt-image-1-mini)
            size: Image size (1024x1024, 1024x1536, 1536x1024, auto)
            quality: Image quality (high, medium, low, auto)
            style: Ignored for GPT Image models (no style support)
            response_format: Ignored - GPT Image always returns base64
            output_format: Output format (png, jpeg, webp)
            api_key: OpenAI API key

        Returns:
            GeneratedImageResult with image data or error
        """
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")

        is_valid, error = self.validate_config(api_key)
        if not is_valid:
            return GeneratedImageResult(error=error)

        if model not in self.supported_models:
            return GeneratedImageResult(
                error=f"Unsupported model: {model}. Choose from {self.supported_models}"
            )

        if size not in self.SIZES:
            return GeneratedImageResult(
                error=f"Invalid size '{size}'. Supported: {self.SIZES}"
            )

        if quality not in self.QUALITIES:
            return GeneratedImageResult(
                error=f"Invalid quality '{quality}'. Supported: {self.QUALITIES}"
            )

        if output_format not in self.OUTPUT_FORMATS:
            return GeneratedImageResult(
                error=f"Invalid output_format '{output_format}'. Supported: {self.OUTPUT_FORMATS}"
            )

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._generate_sync(
                    prompt=prompt,
                    api_key=api_key,  # type: ignore[arg-type]
                    model=model,
                    size=size,
                    quality=quality,
                    output_format=output_format,
                ),
            )
            return result
        except Exception as e:
            return GeneratedImageResult(error=f"Error generating image: {e}")

    def _generate_sync(
        self,
        prompt: str,
        api_key: str,
        model: str,
        size: str,
        quality: str,
        output_format: str,
    ) -> GeneratedImageResult:
        """Synchronous image generation."""
        client = OpenAI(api_key=api_key)

        try:
            # The OpenAI SDK type stubs don't include all gpt-image models yet
            response = client.images.generate(  # type: ignore[call-overload]
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                output_format=output_format,
                n=1,
            )

            data = response.data[0]
            image_bytes = base64.b64decode(data.b64_json) if data.b64_json else None
            revised_prompt = getattr(data, "revised_prompt", None)

            return GeneratedImageResult(
                image_data=image_bytes,
                revised_prompt=revised_prompt,
            )

        except Exception as e:
            return GeneratedImageResult(error=f"Error generating image: {e}")


# Register the provider
ProviderRegistry.register(GptImageProvider())
