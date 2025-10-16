"""Delete book entries from the database."""

import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from app.core.db import engine
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking


def delete_book_data(session: Session, book_slug: str) -> None:
    """Delete all data for a specified book slug."""
    print(f"\nDeleting data for: {book_slug}")

    # Get all scene extractions for this book
    scene_extractions = session.exec(
        select(SceneExtraction).where(SceneExtraction.book_slug == book_slug)
    ).all()

    if not scene_extractions:
        print(f"  No scene extractions found for {book_slug}")
        return

    scene_ids = [se.id for se in scene_extractions]
    print(f"  Found {len(scene_extractions)} scene extractions")

    # Delete generated images
    generated_images = session.exec(
        select(GeneratedImage).where(
            GeneratedImage.scene_extraction_id.in_(scene_ids)
        )
    ).all()
    for img in generated_images:
        session.delete(img)
    print(f"  Deleted {len(generated_images)} generated images")

    # Delete image prompts
    image_prompts = session.exec(
        select(ImagePrompt).where(ImagePrompt.scene_extraction_id.in_(scene_ids))
    ).all()
    for prompt in image_prompts:
        session.delete(prompt)
    print(f"  Deleted {len(image_prompts)} image prompts")

    # Delete scene rankings
    scene_rankings = session.exec(
        select(SceneRanking).where(SceneRanking.scene_extraction_id.in_(scene_ids))
    ).all()
    for ranking in scene_rankings:
        session.delete(ranking)
    print(f"  Deleted {len(scene_rankings)} scene rankings")

    # Delete scene extractions
    for scene in scene_extractions:
        session.delete(scene)
    print(f"  Deleted {len(scene_extractions)} scene extractions")

    session.commit()
    print(f"  ✓ All data for {book_slug} deleted successfully")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python delete_book_data.py <book_slug>")
        print("Example: python delete_book_data.py the-name-of-the-wind-patrick-rothfuss")
        sys.exit(1)

    book_slug = sys.argv[1]

    with Session(engine) as session:
        delete_book_data(session, book_slug)

    print("\n✓ Deletion complete!")
