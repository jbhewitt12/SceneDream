"""Reset the shortest example story fixture for end-to-end testing.

This script targets:
    example_docs/O_Wilde-The_Selfish_Giant.md

Run from backend/:
    uv run python scripts/reset_short_story_fixture.py --dry-run
    uv run python scripts/reset_short_story_fixture.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session

from app.core.db import engine
from app.services.source_document_cleanup_service import SourceDocumentCleanupService

TARGET_STORY_LABEL = "The Selfish Giant"
TARGET_SOURCE_PATH = "example_docs/O_Wilde-The_Selfish_Giant.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete all database records and generated image files for the "
            "shortest example story fixture."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the cleanup scope without deleting anything.",
    )
    return parser


def _print_report(*, dry_run: bool, report: object) -> None:
    mode = "DRY RUN" if dry_run else "COMPLETE"
    print(f"\n{TARGET_STORY_LABEL}")
    print(f"  Source path: {TARGET_SOURCE_PATH}")
    print(f"  Matched book slugs: {', '.join(report.book_slugs) if report.book_slugs else 'none'}")
    print(f"  Documents: {report.document_count}")
    print(f"  Scenes: {report.scene_count}")
    print(f"  Rankings: {report.scene_ranking_count}")
    print(f"  Prompts: {report.image_prompt_count}")
    print(f"  Images: {report.generated_image_count}")
    print(f"  Social posts: {report.social_post_count}")
    print(f"  Generated assets: {report.generated_asset_count}")
    print(f"  Pipeline runs: {report.pipeline_run_count}")
    print(f"  Image batches: {report.image_generation_batch_count}")
    print(f"  Targeted files: {report.targeted_file_count}")
    print(f"  Existing files: {report.existing_file_count}")
    print(f"  Missing files: {report.missing_file_count}")

    if not dry_run:
        print(f"  Files deleted: {report.files_deleted}")
        print(f"  Empty directories removed: {report.directories_removed}")

    print(f"\n{mode}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    with Session(engine) as session:
        service = SourceDocumentCleanupService(session)
        report = service.cleanup_source_document(
            TARGET_SOURCE_PATH,
            dry_run=args.dry_run,
        )

    _print_report(dry_run=args.dry_run, report=report)


if __name__ == "__main__":
    main()
