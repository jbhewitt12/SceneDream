"""Image cleanup CLI - delete files for non-approved generated images.

Usage examples (run from backend/ directory):
    # Preview what would be deleted (all books)
    uv run python -m app.services.image_cleanup.main --all --dry-run

    # Delete non-approved image files for all books
    uv run python -m app.services.image_cleanup.main --all

    # Delete non-approved image files for a specific book
    uv run python -m app.services.image_cleanup.main --book excession-iain-m-banks

    # Preview for a specific book
    uv run python -m app.services.image_cleanup.main --book excession-iain-m-banks --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session

from app.core.db import engine
from app.repositories import GeneratedImageRepository

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if not (_PROJECT_ROOT / "img").is_dir():
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete image files for non-approved generated images. "
        "Database records are kept; only the on-disk files are removed."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Process all books.",
    )
    group.add_argument(
        "--book",
        "--book-slug",
        type=str,
        dest="book_slug",
        help="Only process a specific book slug.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would be deleted without making changes.",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    book_slug: str | None = args.book_slug if not args.all else None
    dry_run: bool = args.dry_run

    with Session(engine) as session:
        repo = GeneratedImageRepository(session)
        images = repo.list_non_approved_with_files(book_slug=book_slug)

        if not images:
            print("No non-approved images with files found.")
            return

        files_deleted = 0
        bytes_freed = 0
        ids_to_mark: list[UUID] = []

        for image in images:
            relative_dir = Path(image.storage_path.strip("/"))
            file_path = (_PROJECT_ROOT / relative_dir / image.file_name).resolve()

            exists = file_path.exists() and file_path.is_file()
            size = file_path.stat().st_size if exists else 0

            label = "WOULD DELETE" if dry_run else "DELETING"
            status = "" if exists else " (file missing)"
            print(
                f"  {label}: {file_path.relative_to(_PROJECT_ROOT)}"
                f"  [{size:,} bytes]{status}"
            )

            if exists and not dry_run:
                file_path.unlink()

            if exists:
                files_deleted += 1
                bytes_freed += size

            ids_to_mark.append(image.id)

        if not dry_run and ids_to_mark:
            repo.bulk_mark_files_deleted(ids_to_mark, commit=True)

        mb_freed = bytes_freed / (1024 * 1024)
        mode = "DRY RUN" if dry_run else "COMPLETE"
        print(f"\n--- {mode} ---")
        print(f"  Records processed: {len(ids_to_mark)}")
        print(f"  Files {'to delete' if dry_run else 'deleted'}: {files_deleted}")
        print(f"  Space {'to free' if dry_run else 'freed'}: {mb_freed:,.1f} MB")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
