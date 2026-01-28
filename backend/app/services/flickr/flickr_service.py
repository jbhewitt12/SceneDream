# flickr_service.py
#
# Service for uploading images to Flickr using the flickrapi library.
# Handles OAuth 1.0a authentication with persistent token storage.
#
# Requirements:
#   - FLICKR_API_KEY and FLICKR_API_SECRET environment variables
#   - flickrapi library (pip install flickrapi)
#
# Usage:
#   from app.services.flickr import FlickrService
#   from app.core.config import settings
#
#   service = FlickrService(settings.FLICKR_API_KEY, settings.FLICKR_API_SECRET)
#   photo_id = service.upload("/path/to/image.jpg", title="My Photo")

from pathlib import Path
from typing import Any

import flickrapi  # type: ignore[import-untyped]
from flickrapi.auth import FlickrAccessToken  # type: ignore[import-untyped]


class FlickrService:
    """Service for uploading images to Flickr."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        token_file: str | Path | None = None,
    ) -> None:
        """
        Initialize the Flickr service.

        Args:
            api_key: Flickr API key
            api_secret: Flickr API secret
            token_file: Path to store the OAuth token for persistence.
                       Defaults to ~/.flickr_token in the user's home directory.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.token_file = (
            Path(token_file) if token_file else Path.home() / ".flickr_token"
        )
        self.flickr = flickrapi.FlickrAPI(
            self.api_key,
            self.api_secret,
            format="parsed-json",
        )
        self._load_or_authenticate()

    def _load_or_authenticate(self) -> None:
        """Load saved token or perform OAuth authentication."""
        if self.token_file.exists():
            try:
                lines = self.token_file.read_text().strip().split("\n")
                if len(lines) >= 4:
                    token, token_secret, fullname, username = lines[:4]
                    self.flickr.token_cache.token = FlickrAccessToken(
                        token, token_secret, "write", fullname, username
                    )
                    # Verify the token is still valid
                    try:
                        self.flickr.auth.oauth.checkToken()
                        print("Loaded saved Flickr access token.")
                        return
                    except flickrapi.FlickrError:
                        print("Saved token is invalid, re-authenticating...")
            except Exception as e:
                print(f"Failed to load token: {e}")

        self._authenticate()

    def _authenticate(self) -> None:
        """Perform OAuth authentication flow."""
        print("Starting Flickr OAuth authentication (one-time process)...")

        # Use out-of-band authentication
        self.flickr.get_request_token(oauth_callback="oob")

        authorize_url = self.flickr.auth_url(perms="write")
        print(
            f"\nPlease open this URL in your browser and authorize the app:\n{authorize_url}\n"
        )

        verifier = input("Enter the verifier code provided by Flickr: ").strip()

        self.flickr.get_access_token(verifier)

        # Save the token for future use
        token = self.flickr.token_cache.token
        if token:
            self.token_file.write_text(
                f"{token.token}\n{token.token_secret}\n{token.fullname}\n{token.username}"
            )
            print("Authentication successful! Access token saved.")
        else:
            raise RuntimeError("Failed to obtain access token")

    def upload(
        self,
        file_path: str | Path,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | str | None = None,
        is_public: bool = True,
        is_friend: bool = False,
        is_family: bool = False,
        safety_level: int = 1,
        content_type: int = 3,
        hidden: int = 2,
        add_ai_tags: bool = True,
    ) -> str:
        """
        Upload an image to Flickr. Defaults optimized for AI-generated content.

        Args:
            file_path: Path to the image file
            title: Title of the photo
            description: Description of the photo
            tags: List of tags or space-separated string
            is_public: If True, photo is public (default True)
            is_friend: If True, visible to friends
            is_family: If True, visible to family
            safety_level: 1=Safe, 2=Moderate, 3=Restricted
            content_type: 1=Photo, 2=Screenshot, 3=Art/Illustration (default 3 for AI)
            hidden: 1=show in global search, 2=hide
            add_ai_tags: Automatically append AI-related tags (default True)

        Returns:
            The new photo ID

        Raises:
            FileNotFoundError: If the file does not exist
            flickrapi.FlickrError: If the upload fails
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        kwargs: dict[str, Any] = {
            "filename": str(file_path),
            "is_public": "1" if is_public else "0",
            "is_friend": "1" if is_friend else "0",
            "is_family": "1" if is_family else "0",
            "safety_level": str(safety_level),
            "content_type": str(content_type),
            "hidden": str(hidden),
        }

        if title:
            kwargs["title"] = title
        if description:
            kwargs["description"] = description

        # Build final tag list
        final_tags: list[str] = []
        if tags:
            if isinstance(tags, list):
                final_tags.extend(tags)
            else:
                final_tags.extend(tags.split())

        if add_ai_tags:
            ai_indicators = ["AI-generated", "AI art", "generative AI"]
            final_tags.extend(ai_indicators)

        if final_tags:
            # Quote multi-word tags
            formatted_tags = " ".join(
                f'"{tag}"' if " " in tag else tag for tag in final_tags
            )
            kwargs["tags"] = formatted_tags

        response = self.flickr.upload(**kwargs)

        if response.get("stat") != "ok":
            raise flickrapi.FlickrError(f"Upload failed: {response}")

        photo_id = response["photoid"]["_content"]
        print(f"Upload successful! Photo ID: {photo_id}")
        print(f"View at: https://www.flickr.com/photos/{photo_id}")
        return str(photo_id)

    def get_photo_url(self, photo_id: str, size: str = "b") -> str | None:
        """
        Get the URL for a photo.

        Args:
            photo_id: The Flickr photo ID
            size: Size suffix (s=small, m=medium, b=large, o=original)

        Returns:
            The photo URL or None if not found
        """
        try:
            response = self.flickr.photos.getSizes(photo_id=photo_id)
            if response.get("stat") == "ok":
                sizes = response.get("sizes", {}).get("size", [])
                size_map = {"s": "Small", "m": "Medium", "b": "Large", "o": "Original"}
                target_label = size_map.get(size, "Large")
                for s in sizes:
                    if s.get("label") == target_label:
                        source: str | None = s.get("source")
                        return source
                # Fallback to largest available
                if sizes:
                    source = sizes[-1].get("source")
                    return source
        except flickrapi.FlickrError as e:
            print(f"Error getting photo URL: {e}")
        return None

    def delete_photo(self, photo_id: str) -> bool:
        """
        Delete a photo from Flickr.

        Args:
            photo_id: The Flickr photo ID

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            response = self.flickr.photos.delete(photo_id=photo_id)
            return bool(response.get("stat") == "ok")
        except flickrapi.FlickrError as e:
            print(f"Error deleting photo: {e}")
            return False

    def set_photo_meta(
        self, photo_id: str, title: str | None = None, description: str | None = None
    ) -> bool:
        """
        Update a photo's title and/or description.

        Args:
            photo_id: The Flickr photo ID
            title: New title (optional)
            description: New description (optional)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            kwargs: dict[str, str] = {"photo_id": photo_id}
            if title is not None:
                kwargs["title"] = title
            if description is not None:
                kwargs["description"] = description
            response = self.flickr.photos.setMeta(**kwargs)
            return bool(response.get("stat") == "ok")
        except flickrapi.FlickrError as e:
            print(f"Error setting photo meta: {e}")
            return False

    def add_tags(self, photo_id: str, tags: list[str] | str) -> bool:
        """
        Add tags to a photo.

        Args:
            photo_id: The Flickr photo ID
            tags: List of tags or space-separated string

        Returns:
            True if tags added successfully, False otherwise
        """
        try:
            if isinstance(tags, list):
                tags_str = " ".join(f'"{tag}"' if " " in tag else tag for tag in tags)
            else:
                tags_str = tags
            response = self.flickr.photos.addTags(photo_id=photo_id, tags=tags_str)
            return bool(response.get("stat") == "ok")
        except flickrapi.FlickrError as e:
            print(f"Error adding tags: {e}")
            return False
