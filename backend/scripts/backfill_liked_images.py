#!/usr/bin/env python3
"""Backfill script to copy all existing liked images to the liked_images directory."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from sqlmodel import Session, select

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import engine
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIKED_IMAGES_DIR = PROJECT_ROOT / "liked_images"


def format_title_for_filename(title: str | None) -> str:
    """Format prompt title for use in filename."""
    if not title:
        return "untitled"

    # Convert to lowercase, replace spaces with dashes
    safe_title = title.lower().strip()
    # Replace spaces and underscores with single dash
    safe_title = re.sub(r"[\s_]+", "-", safe_title)
    # Remove any characters that aren't alphanumeric, dash, or dot
    safe_title = re.sub(r"[^a-z0-9\-.]", "", safe_title)
    # Remove leading/trailing dashes
    safe_title = safe_title.strip("-")

    return safe_title or "untitled"


def resolve_image_path(storage_path: str, file_name: str) -> Path:
    """Resolve the full path to a generated image."""
    return PROJECT_ROOT / storage_path / file_name


def copy_liked_image(
    image: GeneratedImage,
    prompt: ImagePrompt | None,
) -> tuple[bool, str]:
    """
    Copy a liked image to the liked_images directory.

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Get source file
    source_file = resolve_image_path(image.storage_path, image.file_name)

    if not source_file.exists():
        return False, f"Source file not found: {source_file}"

    # Format destination filename
    safe_title = format_title_for_filename(prompt.title if prompt else None)
    extension = source_file.suffix
    dest_filename = f"{safe_title}-{image.id}{extension}"
    dest_path = LIKED_IMAGES_DIR / dest_filename

    # Skip if already exists
    if dest_path.exists():
        return True, f"Already exists: {dest_filename}"

    # Copy the file
    try:
        shutil.copy2(source_file, dest_path)
        return True, f"Copied: {dest_filename}"
    except Exception as exc:
        return False, f"Failed to copy: {exc}"


def main() -> int:
    """Main backfill logic."""
    # Ensure liked_images directory exists
    LIKED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Liked images directory: {LIKED_IMAGES_DIR}")
    print()

    with Session(engine) as session:
        # Find all approved images
        statement = (
            select(GeneratedImage)
            .where(GeneratedImage.user_approved == True)  # noqa: E712
            .order_by(GeneratedImage.created_at)
        )
        liked_images = session.exec(statement).all()

        if not liked_images:
            print("No liked images found in database.")
            return 0

        print(f"Found {len(liked_images)} liked image(s) to backfill")
        print()

        # Load all prompts for efficiency
        prompt_ids = [img.image_prompt_id for img in liked_images]
        prompts_statement = select(ImagePrompt).where(ImagePrompt.id.in_(prompt_ids))
        prompts = {p.id: p for p in session.exec(prompts_statement).all()}

        # Process each liked image
        success_count = 0
        skip_count = 0
        error_count = 0

        for i, image in enumerate(liked_images, 1):
            prompt = prompts.get(image.image_prompt_id)
            print(f"[{i}/{len(liked_images)}] Processing image {image.id}")
            print(f"  Book: {image.book_slug}, Chapter: {image.chapter_number}")
            print(f"  Prompt: {prompt.title if prompt else 'N/A'}")

            success, message = copy_liked_image(image, prompt)
            print(f"  {message}")

            if success:
                if "Already exists" in message:
                    skip_count += 1
                else:
                    success_count += 1
            else:
                error_count += 1

            print()

    # Print summary
    print("=" * 60)
    print("Backfill Summary:")
    print(f"  Total liked images: {len(liked_images)}")
    print(f"  Successfully copied: {success_count}")
    print(f"  Already existed: {skip_count}")
    print(f"  Errors: {error_count}")
    print("=" * 60)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
