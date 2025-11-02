#!/usr/bin/env python3
"""
Test metadata generation on random image prompts.

To run test: 
```
uv run python app/services/prompt_metadata/check_metadata_generation.py 5
```
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

# Add backend root directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.db import engine
from models.image_prompt import ImagePrompt

# Import from same directory
from prompt_metadata_service import (
    PromptMetadataConfig,
    PromptMetadataGenerationService,
)


def print_separator(char: str = "=", length: int = 80) -> None:
    """Print a separator line."""
    print(char * length)


def print_prompt_details(
    prompt: ImagePrompt,
    metadata: dict[str, str] | None,
    index: int,
    total: int,
) -> None:
    """Print a single prompt with its metadata in a readable format."""
    print_separator()
    print(f"PROMPT {index}/{total}")
    print_separator()
    print()

    # Prompt text
    prompt_text = prompt.prompt_text.strip()
    print(prompt_text)
    print()

    # Generated metadata
    if metadata:
        print_separator("-")
        title = metadata.get("title", "(no title generated)")
        flavour = metadata.get("flavour_text", "(no flavour text generated)")

        print(f"TITLE: {title}")
        print()
        print(f"FLAVOUR TEXT: {flavour}")
        print()
    else:
        print_separator("-")
        print("❌ GENERATION FAILED")
        print()

    print()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test metadata generation on random image prompts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python app/services/prompt_metadata/check_metadata_generation.py 5
  uv run python app/services/prompt_metadata/check_metadata_generation.py 10 --model gemini-2.5-flash
  uv run python app/services/prompt_metadata/check_metadata_generation.py 3 --temperature 0.9
        """,
    )
    parser.add_argument(
        "count",
        type=int,
        help="Number of random prompts to test",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-pro",
        help="Model to use for generation (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.85,
        help="Temperature for generation (default: 0.85)",
    )

    args = parser.parse_args()

    if args.count < 1:
        print("Error: count must be at least 1", file=sys.stderr)
        return 1

    print_separator("=")
    print("🔍 METADATA GENERATION TEST (READ-ONLY)")
    print_separator("=")
    print()
    print("⚠️  This script will generate fresh metadata but NEVER modify the database")
    print()
    print(f"📊 Testing on {args.count} random prompt(s)")
    print(f"🤖 Model: {args.model}")
    print(f"🌡️  Temperature: {args.temperature}")
    print()

    return asyncio.run(_run_prompt_checks(args))


async def _run_prompt_checks(args: argparse.Namespace) -> int:
    """Execute the metadata generation checks asynchronously."""
    with Session(engine) as session:
        # Select random prompts
        statement = (
            select(ImagePrompt)
            .order_by(func.random())
            .limit(args.count)
        )
        prompts = session.exec(statement).all()

        if not prompts:
            print("❌ No prompts found in database")
            return 1

        actual_count = len(prompts)
        if actual_count < args.count:
            print(f"⚠️  Only found {actual_count} prompt(s) in database")
            print()

        # Configure service
        # - dry_run=True: Never save to database
        # - overwrite_existing=True: Always generate fresh metadata (don't skip)
        config = PromptMetadataConfig(
            model_name=args.model,
            temperature=args.temperature,
            overwrite_existing=True,  # Always generate, don't skip existing
            dry_run=True,  # Never save to database
            fail_on_error=False,
        )
        service = PromptMetadataGenerationService(session, config=config)

        # Generate metadata for each prompt
        for i, prompt in enumerate(prompts, 1):
            # Always generate fresh metadata (overwrite=True) but never save (dry_run=True)
            metadata = await service.generate_metadata_for_prompt(
                prompt,
                dry_run=True,  # Never save to database
                overwrite=True,  # Always generate, don't return cached metadata
            )

            # Convert to dict if needed
            if isinstance(metadata, ImagePrompt):
                metadata_dict = {
                    "title": metadata.title,
                    "flavour_text": metadata.flavour_text,
                    "skipped": False,
                }
            elif isinstance(metadata, dict):
                metadata_dict = metadata
            else:
                metadata_dict = None

            print_prompt_details(prompt, metadata_dict, i, actual_count)

        print_separator("=")
        print("✅ TESTING COMPLETE")
        print_separator("=")

    return 0


if __name__ == "__main__":
    sys.exit(main())
