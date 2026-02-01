"""Tests for GptImageProvider."""

import os

import pytest

from app.services.image_generation.gpt_image_api import GptImageProvider
from app.services.image_generation.provider_registry import ProviderRegistry

pytestmark = pytest.mark.anyio("asyncio")


class TestGptImageProvider:
    """Tests for GptImageProvider class."""

    def test_provider_name(self) -> None:
        """Test provider_name returns correct value."""
        provider = GptImageProvider()
        assert provider.provider_name == "openai_gpt_image"

    def test_supported_models(self) -> None:
        """Test supported_models returns correct list."""
        provider = GptImageProvider()
        models = provider.supported_models
        assert "gpt-image-1.5" in models
        assert "gpt-image-1" in models
        assert "gpt-image-1-mini" in models
        assert len(models) == 3

    def test_get_supported_sizes(self) -> None:
        """Test get_supported_sizes returns valid sizes."""
        provider = GptImageProvider()
        sizes = provider.get_supported_sizes("gpt-image-1.5")
        assert "1024x1024" in sizes
        assert "1024x1536" in sizes
        assert "1536x1024" in sizes
        assert "auto" in sizes

    def test_validate_config_valid(self) -> None:
        """Test validate_config with valid API key."""
        provider = GptImageProvider()
        is_valid, error = provider.validate_config("sk-test-key-12345")
        assert is_valid is True
        assert error is None

    def test_validate_config_missing_key(self) -> None:
        """Test validate_config with missing API key."""
        provider = GptImageProvider()
        is_valid, error = provider.validate_config(None)
        assert is_valid is False
        assert error == "OpenAI API key is required"

    def test_validate_config_invalid_format(self) -> None:
        """Test validate_config with invalid API key format."""
        provider = GptImageProvider()
        is_valid, error = provider.validate_config("invalid-key")
        assert is_valid is False
        assert error == "Invalid OpenAI API key format"

    def test_provider_registered(self) -> None:
        """Test that the provider is registered in the registry."""
        provider = ProviderRegistry.get("openai_gpt_image")
        assert provider is not None
        assert isinstance(provider, GptImageProvider)

    async def test_generate_image_invalid_model(self) -> None:
        """Test generate_image with invalid model returns error."""
        provider = GptImageProvider()
        result = await provider.generate_image(
            "test prompt",
            model="invalid-model",
            api_key="sk-test-key",
        )
        assert result.error is not None
        assert "Unsupported model" in result.error

    async def test_generate_image_invalid_size(self) -> None:
        """Test generate_image with invalid size returns error."""
        provider = GptImageProvider()
        result = await provider.generate_image(
            "test prompt",
            model="gpt-image-1.5",
            size="invalid-size",
            api_key="sk-test-key",
        )
        assert result.error is not None
        assert "Invalid size" in result.error

    async def test_generate_image_invalid_quality(self) -> None:
        """Test generate_image with invalid quality returns error."""
        provider = GptImageProvider()
        result = await provider.generate_image(
            "test prompt",
            model="gpt-image-1.5",
            quality="invalid-quality",
            api_key="sk-test-key",
        )
        assert result.error is not None
        assert "Invalid quality" in result.error

    async def test_generate_image_invalid_output_format(self) -> None:
        """Test generate_image with invalid output_format returns error."""
        provider = GptImageProvider()
        result = await provider.generate_image(
            "test prompt",
            model="gpt-image-1.5",
            output_format="gif",
            api_key="sk-test-key",
        )
        assert result.error is not None
        assert "Invalid output_format" in result.error

    async def test_generate_image_missing_api_key(self) -> None:
        """Test generate_image with missing API key returns error."""
        # Temporarily remove environment variable if set
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            provider = GptImageProvider()
            result = await provider.generate_image(
                "test prompt",
                model="gpt-image-1.5",
            )
            assert result.error is not None
            assert "API key is required" in result.error
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
