# dalle_image_api.py
#
# This Python module provides the DALL-E image generation provider and utility functions.
#
# Requirements:
#   - An OpenAI API key (obtain from https://platform.openai.com/account/api-keys)
#   - Python 3.8 or higher
#
# Note: DALL-E 3 has specific limitations:
#   - n=1 (only one image per request)
#   - Prompt length up to 4000 characters
#   - Sizes: '1024x1024', '1024x1792', '1792x1024'
#   - Quality: 'standard' (default, faster/cheaper) or 'hd' (higher quality, slower/more expensive)
#   - Style: 'vivid' (hyper-real, dramatic) or 'natural' (more natural-looking)
#   - Response format: 'url' (returns expiring URLs, typically valid for 1 hour) or 'b64_json' (returns base64-encoded image data)

from __future__ import annotations

import asyncio
import base64
import os

import requests
from openai import OpenAI

from app.services.image_generation.base_provider import (
    GeneratedImageResult,
    ImageGenerationProvider,
)
from app.services.image_generation.provider_registry import ProviderRegistry


class DalleProvider(ImageGenerationProvider):
    """OpenAI DALL-E image generation provider."""

    DALLE3_SIZES = ["1024x1024", "1024x1792", "1792x1024"]
    DALLE2_SIZES = ["256x256", "512x512", "1024x1024"]

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> list[str]:
        return ["dall-e-3", "dall-e-2"]

    def get_supported_sizes(self, model: str) -> list[str]:
        if model == "dall-e-3":
            return self.DALLE3_SIZES
        elif model == "dall-e-2":
            return self.DALLE2_SIZES
        return self.DALLE3_SIZES

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
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        response_format: str = "b64_json",
        api_key: str | None = None,
    ) -> GeneratedImageResult:
        """
        Generate an image using OpenAI's DALL-E model.

        Args:
            prompt: Text description of the desired image
            model: Model to use ('dall-e-3' or 'dall-e-2')
            size: Image size
            quality: Image quality ('standard' or 'hd')
            style: Image style ('vivid' or 'natural')
            response_format: Response format ('b64_json' or 'url')
            api_key: OpenAI API key

        Returns:
            GeneratedImageResult with image data or error
        """
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")

        is_valid, error = self.validate_config(api_key)
        if not is_valid:
            return GeneratedImageResult(error=error)

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
                    style=style,
                    response_format=response_format,
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
        style: str,
        response_format: str,
    ) -> GeneratedImageResult:
        """Synchronous image generation."""
        client = OpenAI(api_key=api_key)

        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality if model == "dall-e-3" else None,
                style=style if model == "dall-e-3" else None,
                n=1,
                response_format=response_format,
            )

            data = response.data[0]
            revised_prompt = getattr(data, "revised_prompt", None)

            if response_format == "url":
                return GeneratedImageResult(
                    image_url=data.url,
                    revised_prompt=revised_prompt,
                )
            else:  # b64_json
                image_bytes = base64.b64decode(data.b64_json) if data.b64_json else None
                return GeneratedImageResult(
                    image_data=image_bytes,
                    revised_prompt=revised_prompt,
                )

        except Exception as e:
            return GeneratedImageResult(error=f"Error generating image: {e}")


# Register the provider
ProviderRegistry.register(DalleProvider())


# Keep module-level helper functions for backwards compatibility
def generate_images(
    prompt: str,
    api_key: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    n: int = 1,
    response_format: str = "url",
) -> list[str | bytes]:
    """
    Generates images using OpenAI's DALL-E model based on the provided text prompt.

    Parameters:
    - prompt (str): A text description of the desired image. Maximum length is 4000 characters for DALL-E 3.
    - api_key (str): Your OpenAI API key for authentication.
    - model (str, optional): The model to use for generation. Defaults to "dall-e-3".
    - size (str, optional): The size of the generated images. Defaults to "1024x1024".
    - quality (str, optional): The quality of the generated image. Defaults to "standard".
    - style (str, optional): The style of the generated image. Defaults to "vivid".
    - n (int, optional): The number of images to generate. Defaults to 1.
    - response_format (str, optional): The format of the response data. Defaults to "url".

    Returns:
    - List[Union[str, bytes]]: A list containing either image URLs (str) or base64-encoded image data (str).
    """
    client = OpenAI(api_key=api_key)

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality if model == "dall-e-3" else None,
            style=style if model == "dall-e-3" else None,
            n=n,
            response_format=response_format,
        )

        if response_format == "url":
            return [data.url for data in response.data]
        elif response_format == "b64_json":
            return [data.b64_json for data in response.data]
        else:
            return []

    except Exception as e:
        print(f"Error generating images: {e}")
        return []


def save_image_from_url(url: str, filename: str) -> bool:
    """
    Downloads and saves an image from a URL to a local file.

    Parameters:
    - url (str): The URL of the image to download.
    - filename (str): The path and name of the file to save (e.g., "image.png").

    Returns:
    - bool: True if the image was saved successfully, False otherwise.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"Error saving image from URL: {e}")
        return False


def save_image_from_b64(b64_data: str, filename: str) -> bool:
    """
    Decodes and saves a base64-encoded image string to a local file.

    Parameters:
    - b64_data (str): The base64-encoded image data.
    - filename (str): The path and name of the file to save (e.g., "image.png").

    Returns:
    - bool: True if the image was saved successfully, False otherwise.
    """
    try:
        image_data = base64.b64decode(b64_data)
        with open(filename, "wb") as f:
            f.write(image_data)
        return True
    except Exception as e:
        print(f"Error saving image from base64: {e}")
        return False
