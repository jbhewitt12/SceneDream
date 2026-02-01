"""Live integration test for GptImageProvider.

Run manually with:
    cd backend && uv run pytest app/tests/services/test_gpt_image_api_live.py -v
"""

import os

import pytest

from app.services.image_generation.gpt_image_api import GptImageProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.anyio("asyncio"),
]


@pytest.fixture
def api_key() -> str:
    """Get API key from environment or skip."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


class TestGptImageProviderLive:
    """Live integration tests that hit the OpenAI API."""

    async def test_generate_image_real(self, api_key: str) -> None:
        """Test actual image generation with GPT Image model."""
        provider = GptImageProvider()

        result = await provider.generate_image(
            "A simple red circle on a white background",
            model="gpt-image-1",
            size="1024x1024",
            quality="low",
            output_format="png",
            api_key=api_key,
        )

        assert result.error is None, f"Error: {result.error}"
        assert result.image_data is not None
        assert len(result.image_data) > 0

        # Verify it's a valid PNG (starts with PNG magic bytes)
        assert result.image_data[:8] == b"\x89PNG\r\n\x1a\n"

        # Save for manual inspection
        test_output = "/tmp/gpt_image_test.png"
        with open(test_output, "wb") as f:
            f.write(result.image_data)
        print(f"Image saved to {test_output}")
