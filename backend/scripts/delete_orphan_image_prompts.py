"""Delete image prompts that have no generated images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

# Ensure repository root modules can be imported when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from app.core.db import engine
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt


def _find_orphan_prompts(session: Session) -> list[ImagePrompt]:
    """Return all prompts that have zero generated images attached."""
    stmt = (
        select(ImagePrompt)
        .outerjoin(
            GeneratedImage,
            GeneratedImage.image_prompt_id == ImagePrompt.id,
        )
        .where(GeneratedImage.id.is_(None))
    )
    return list(session.exec(stmt).all())


def _print_prompt_summary(prompts: Iterable[ImagePrompt]) -> None:
    """Pretty-print a terse summary for visibility."""
    for prompt in prompts:
        print(
            f" - prompt_id={prompt.id} | scene_id={prompt.scene_extraction_id} | "
            f"model={prompt.model_name} | version={prompt.prompt_version} | "
            f"variant={prompt.variant_index}"
        )


def delete_orphan_prompts(session: Session, *, dry_run: bool) -> int:
    """Delete prompts without generated images, optionally as a dry run."""
    orphans = _find_orphan_prompts(session)

    if not orphans:
        print("✓ No orphan image prompts found.")
        return 0

    print(f"Found {len(orphans)} orphan image prompts:")
    _print_prompt_summary(orphans)

    # Double-check before deleting to avoid races if new images appeared mid-run.
    confirmed_orphans: list[ImagePrompt] = []
    for prompt in orphans:
        has_images = session.exec(
            select(GeneratedImage.id)
            .where(GeneratedImage.image_prompt_id == prompt.id)
            .limit(1)
        ).first()
        if has_images is None:
            confirmed_orphans.append(prompt)
        else:
            print(
                f" ! Skipping prompt {prompt.id} because a generated image was found "
                "during verification."
            )

    if not confirmed_orphans:
        print("✓ Nothing to delete after verification.")
        return 0

    print(f"Deleting {len(confirmed_orphans)} prompts after verification.")

    if dry_run:
        print("Dry run requested; no database changes will be committed.")
        return len(confirmed_orphans)

    for prompt in confirmed_orphans:
        session.delete(prompt)

    session.commit()
    print("✓ Deletion commit complete.")
    return len(confirmed_orphans)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete image prompts without matching generated images."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List prompts that would be deleted without committing the transaction.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        delete_orphan_prompts(session, dry_run=args.dry_run)

    if args.dry_run:
        print("Re-run without --dry-run to perform the deletion.")


if __name__ == "__main__":
    main()
