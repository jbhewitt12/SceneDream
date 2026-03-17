from __future__ import annotations

import pytest

from app.services.image_gen_cli import _build_parser


def test_prompts_command_not_exposed() -> None:
    """The legacy prompts command has been removed."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["prompts", "--book-slug", "test-book"])


def test_images_command_not_exposed() -> None:
    """The legacy images command has been removed."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["images", "--book-slug", "test-book", "--top-scenes", "5"])


def test_refresh_command_not_exposed() -> None:
    """The legacy refresh command has been removed."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["refresh", "--book-slug", "test-book", "--top-scenes", "3"])


def test_backfill_command_not_exposed() -> None:
    """The legacy backfill command has been removed."""
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["backfill", "--top-scenes", "5"])


def test_run_command_is_exposed() -> None:
    args = _build_parser().parse_args(
        ["run", "--book-slug", "test-book", "--skip-extraction"]
    )
    assert args.command == "run"


def test_extract_command_is_exposed() -> None:
    args = _build_parser().parse_args(
        ["extract", "--book-slug", "test-book", "--book-path", "/tmp/book.epub"]
    )
    assert args.command == "extract"


def test_rank_command_is_exposed() -> None:
    args = _build_parser().parse_args(["rank", "--book-slug", "test-book"])
    assert args.command == "rank"
