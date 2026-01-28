"""Flickr posting implementation for social media posting service."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.flickr.flickr_service import FlickrService

if TYPE_CHECKING:
    from models.generated_image import GeneratedImage
    from models.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)


class FlickrPoster:
    """Handles posting images to Flickr with AI-content compliance."""

    def __init__(self) -> None:
        self._service: FlickrService | None = None

    def _get_service(self) -> FlickrService:
        """Lazy initialization of FlickrService to avoid auth issues at import time."""
        if self._service is None:
            if not settings.FLICKR_API_KEY or not settings.FLICKR_API_SECRET:
                raise ValueError("Flickr API credentials not configured")
            self._service = FlickrService(
                settings.FLICKR_API_KEY,
                settings.FLICKR_API_SECRET,
            )
        return self._service

    async def post(
        self, image: GeneratedImage, prompt: ImagePrompt
    ) -> tuple[str, str]:
        """
        Post an image to Flickr.

        Args:
            image: The GeneratedImage record with storage_path
            prompt: The ImagePrompt record with title

        Returns:
            Tuple of (photo_id, photo_url)

        Raises:
            FileNotFoundError: If the image file doesn't exist
            RuntimeError: If the upload fails
        """
        service = self._get_service()

        # Determine the full path to the image
        # storage_path is the directory relative to project root (e.g., "img/generated/book/chapter-X")
        # file_name is the actual image file (e.g., "uuid.png")
        project_root = Path(__file__).parents[5]  # Go up from services/social_posting
        image_path = project_root / image.storage_path / image.file_name

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        title = prompt.title or "Untitled"

        logger.info(f"Uploading image to Flickr: {title}")

        # Run the synchronous upload in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        photo_id = await loop.run_in_executor(
            None,
            lambda: service.upload(
                file_path=image_path,
                title=title,
                # FlickrService.upload() already has AI-optimized defaults:
                # - content_type=3 (Art/Illustration)
                # - add_ai_tags=True (adds "AI-generated", "AI art", "generative AI")
            ),
        )

        # Construct the Flickr URL
        # Note: FlickrService outputs user-specific URL but we'll use the simpler format
        photo_url = f"https://www.flickr.com/photos/{photo_id}"

        logger.info(f"Successfully uploaded to Flickr: {photo_url}")

        return photo_id, photo_url
