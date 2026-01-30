"""X (Twitter) posting implementation for social media posting service."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import tweepy

from app.core.config import settings
from app.services.social_posting.exceptions import RateLimitError

if TYPE_CHECKING:
    from models.generated_image import GeneratedImage
    from models.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)

# HTTP status codes and error messages that indicate rate limiting
RATE_LIMIT_STATUS_CODES = {429, 402}  # 429 = Too Many Requests, 402 = Payment Required (credits exhausted)
RATE_LIMIT_ERROR_KEYWORDS = ["rate limit", "too many requests", "credits"]


class XPoster:
    """Handles posting images to X (Twitter) with AI-content compliance."""

    def __init__(self) -> None:
        self._client: tweepy.Client | None = None
        self._api: tweepy.API | None = None

    def _get_client(self) -> tweepy.Client:
        """Lazy initialization of tweepy v2 Client."""
        if self._client is None:
            if not all(
                [
                    settings.X_CONSUMER_KEY,
                    settings.X_CONSUMER_SECRET,
                    settings.X_ACCESS_TOKEN,
                    settings.X_ACCESS_TOKEN_SECRET,
                ]
            ):
                raise ValueError("X API credentials not configured")
            self._client = tweepy.Client(
                consumer_key=settings.X_CONSUMER_KEY,
                consumer_secret=settings.X_CONSUMER_SECRET,
                access_token=settings.X_ACCESS_TOKEN,
                access_token_secret=settings.X_ACCESS_TOKEN_SECRET,
            )
        return self._client

    def _get_api(self) -> tweepy.API:
        """Lazy initialization of tweepy v1.1 API for media upload."""
        if self._api is None:
            if not all(
                [
                    settings.X_CONSUMER_KEY,
                    settings.X_CONSUMER_SECRET,
                    settings.X_ACCESS_TOKEN,
                    settings.X_ACCESS_TOKEN_SECRET,
                ]
            ):
                raise ValueError("X API credentials not configured")
            auth = tweepy.OAuth1UserHandler(
                settings.X_CONSUMER_KEY,
                settings.X_CONSUMER_SECRET,
                settings.X_ACCESS_TOKEN,
                settings.X_ACCESS_TOKEN_SECRET,
            )
            self._api = tweepy.API(auth)
        return self._api

    def _upload_and_post(self, image_path: Path, title: str) -> tuple[str, str]:
        """
        Synchronous method to upload media and create tweet.

        Args:
            image_path: Path to the image file
            title: The image title for tweet text and alt text

        Returns:
            Tuple of (tweet_id, tweet_url)

        Raises:
            RateLimitError: If the API returns a rate limit error
        """
        api = self._get_api()
        client = self._get_client()

        try:
            # Upload media using v1.1 API
            media = api.media_upload(filename=str(image_path))

            # Set alt text for accessibility
            api.create_media_metadata(
                media_id=media.media_id_string,
                alt_text={"text": title[:1000]},  # Alt text limit is 1000 chars
            )

            # Create tweet text with AI disclosure hashtags
            tweet_text = f"{title} #AIgenerated #AIart"
            if len(tweet_text) > 280:
                # Truncate title if needed, keeping hashtags
                max_title_len = 280 - len(" #AIgenerated #AIart") - 3  # 3 for "..."
                tweet_text = f"{title[:max_title_len]}... #AIgenerated #AIart"

            # Create tweet using v2 API
            response = client.create_tweet(
                text=tweet_text,
                media_ids=[media.media_id_string],
                user_auth=True,
            )

            tweet_id = str(response.data["id"])
            tweet_url = f"https://x.com/i/status/{tweet_id}"

            return tweet_id, tweet_url

        except tweepy.errors.TooManyRequests as e:
            raise RateLimitError(f"X API rate limit exceeded: {e}") from e
        except tweepy.errors.HTTPException as e:
            # Check for rate limit indicators in the response
            error_str = str(e).lower()
            if (
                getattr(e, "response", None)
                and getattr(e.response, "status_code", None) in RATE_LIMIT_STATUS_CODES
            ) or any(keyword in error_str for keyword in RATE_LIMIT_ERROR_KEYWORDS):
                raise RateLimitError(f"X API rate limit or credits exhausted: {e}") from e
            raise

    async def post(self, image: GeneratedImage, prompt: ImagePrompt) -> tuple[str, str]:
        """
        Post an image to X (Twitter).

        Args:
            image: The GeneratedImage record with storage_path
            prompt: The ImagePrompt record with title

        Returns:
            Tuple of (tweet_id, tweet_url)

        Raises:
            FileNotFoundError: If the image file doesn't exist
            RuntimeError: If the upload fails
        """
        # Determine the full path to the image
        project_root = Path(__file__).parents[4]
        image_path = project_root / image.storage_path / image.file_name

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        title = prompt.title or "Untitled"

        logger.info(f"Uploading image to X: {title}")

        # Run the synchronous upload in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        tweet_id, tweet_url = await loop.run_in_executor(
            None,
            lambda: self._upload_and_post(image_path, title),
        )

        logger.info(f"Successfully posted to X: {tweet_url}")

        return tweet_id, tweet_url
