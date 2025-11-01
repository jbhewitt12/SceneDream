#!/usr/bin/env python3
"""Delete database entries for test books matching 'test-book-*' pattern."""

import argparse
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, create_engine, select

from app.core.config import settings
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking


def delete_test_books(dry_run: bool = True) -> None:
    """
    Delete all database entries for books with slugs matching 'test-book-*'.

    Args:
        dry_run: If True, only print what would be deleted without actually deleting.
    """
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

    with Session(engine) as session:
        # Find all SceneExtraction records for test books
        statement = select(SceneExtraction).where(
            SceneExtraction.book_slug.like("test-book-%")  # type: ignore
        )
        test_scene_extractions = session.exec(statement).all()

        if not test_scene_extractions:
            print("✓ No test book entries found in the database.")
            return

        # Collect statistics
        extraction_ids = [se.id for se in test_scene_extractions]
        book_slugs = sorted(set(se.book_slug for se in test_scene_extractions))

        # Count related records
        generated_images = session.exec(
            select(GeneratedImage).where(
                GeneratedImage.scene_extraction_id.in_(extraction_ids)  # type: ignore
            )
        ).all()

        image_prompts = session.exec(
            select(ImagePrompt).where(
                ImagePrompt.scene_extraction_id.in_(extraction_ids)  # type: ignore
            )
        ).all()

        scene_rankings = session.exec(
            select(SceneRanking).where(
                SceneRanking.scene_extraction_id.in_(extraction_ids)  # type: ignore
            )
        ).all()

        # Print summary
        print("\n" + "=" * 70)
        print("TEST BOOK DELETION SUMMARY")
        print("=" * 70)
        print(f"\nFound {len(book_slugs)} test book(s):")
        for slug in book_slugs:
            print(f"  - {slug}")

        print(f"\nRecords to be deleted:")
        print(f"  - {len(test_scene_extractions)} scene extractions")
        print(f"  - {len(scene_rankings)} scene rankings")
        print(f"  - {len(image_prompts)} image prompts")
        print(f"  - {len(generated_images)} generated images")
        print(f"  - TOTAL: {len(test_scene_extractions) + len(scene_rankings) + len(image_prompts) + len(generated_images)} records")
        print("=" * 70 + "\n")

        if dry_run:
            print("DRY RUN: No records were deleted.")
            print("Run with --execute to actually delete these records.")
            return

        # Perform deletion in correct order (respecting foreign keys)
        print("Deleting records...")

        # 1. Delete GeneratedImage records first (they have FKs to both SceneExtraction and ImagePrompt)
        for img in generated_images:
            session.delete(img)
        print(f"✓ Deleted {len(generated_images)} generated images")

        # 2. Delete ImagePrompt records (they have FK to SceneExtraction)
        for prompt in image_prompts:
            session.delete(prompt)
        print(f"✓ Deleted {len(image_prompts)} image prompts")

        # 3. Delete SceneRanking records (they have FK to SceneExtraction)
        for ranking in scene_rankings:
            session.delete(ranking)
        print(f"✓ Deleted {len(scene_rankings)} scene rankings")

        # 4. Delete SceneExtraction records (parent records)
        for extraction in test_scene_extractions:
            session.delete(extraction)
        print(f"✓ Deleted {len(test_scene_extractions)} scene extractions")

        # Commit the transaction
        session.commit()
        print("\n✓ All test book entries have been successfully deleted.")


def main() -> None:
    """Parse CLI arguments and run deletion."""
    parser = argparse.ArgumentParser(
        description="Delete database entries for test books matching 'test-book-*' pattern."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the records (default is dry-run mode)",
    )

    args = parser.parse_args()

    try:
        delete_test_books(dry_run=not args.execute)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
