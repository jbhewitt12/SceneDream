from __future__ import annotations

import argparse
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.image_gen_cli import _build_parser, _run_full_pipeline
from app.services.pipeline.orchestrator_config import (
    DocumentTarget,
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineExecutionContext,
    PipelineExecutionResult,
    PipelineStagePlan,
    PipelineStats,
    PreparedPipelineExecution,
    PromptExecutionOptions,
)


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


# ---------------------------------------------------------------------------
# CLI delegation to orchestrator
# ---------------------------------------------------------------------------


def _make_prepared(book_slug: str = "test-book") -> PreparedPipelineExecution:
    return PreparedPipelineExecution(
        run_id=uuid4(),
        config=PipelineExecutionConfig(
            target=DocumentTarget(book_slug=book_slug),
            stages=PipelineStagePlan(
                run_extraction=True,
                run_ranking=True,
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(),
            image_options=ImageExecutionOptions(),
        ),
        config_overrides={},
        context=PipelineExecutionContext(book_slug=book_slug),
    )


def _make_run_args(**kwargs: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "book_slug": "test-book",
        "book_path": None,
        "dry_run": False,
        "skip_extraction": False,
        "skip_ranking": False,
        "skip_prompts": False,
        "images_for_scenes": None,
        "prompts_per_scene": None,
        "ignore_ranking_recommendations": False,
        "prompts_for_scenes": None,
        "prompt_art_style_mode": None,
        "prompt_art_style_text": None,
        "quality": "standard",
        "style": None,
        "aspect_ratio": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestRunCommandDelegation:
    def test_run_delegates_to_prepare_execution_and_orchestrator(self) -> None:
        """The run command calls prepare_execution() then PipelineOrchestrator.execute()."""
        prepared = _make_prepared()
        execute_result = PipelineExecutionResult(
            run_id=prepared.run_id,
            status="completed",
            stats=PipelineStats(),
        )
        mock_service = MagicMock()
        mock_service.prepare_execution.return_value = prepared
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.pipeline.PipelineRunStartService",
                return_value=mock_service,
            ),
            patch(
                "app.services.pipeline.PipelineOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch("app.services.image_gen_cli.Session"),
        ):
            args = _make_run_args()
            stats = asyncio.run(_run_full_pipeline(args))

        mock_service.prepare_execution.assert_called_once()
        mock_orchestrator.execute.assert_called_once_with(prepared)
        assert isinstance(stats, PipelineStats)

    def test_run_passes_skip_flags_to_stage_plan(self) -> None:
        """Skip flags from CLI args are reflected in the stage plan passed to prepare_execution."""
        prepared = _make_prepared()
        mock_service = MagicMock()
        mock_service.prepare_execution.return_value = prepared
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute = AsyncMock(
            return_value=PipelineExecutionResult(
                run_id=prepared.run_id,
                status="completed",
                stats=PipelineStats(),
            )
        )

        with (
            patch(
                "app.services.pipeline.PipelineRunStartService",
                return_value=mock_service,
            ),
            patch(
                "app.services.pipeline.PipelineOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch("app.services.image_gen_cli.Session"),
        ):
            args = _make_run_args(skip_extraction=True, skip_ranking=True)
            asyncio.run(_run_full_pipeline(args))

        config_arg: PipelineExecutionConfig = mock_service.prepare_execution.call_args[
            0
        ][0]
        assert config_arg.stages.run_extraction is False
        assert config_arg.stages.run_ranking is False

    def test_run_dry_run_returns_stats_without_calling_orchestrator(self) -> None:
        """Dry-run mode returns empty stats without calling prepare_execution or the orchestrator."""
        mock_service = MagicMock()
        mock_orchestrator = MagicMock()

        with (
            patch(
                "app.services.pipeline.PipelineRunStartService",
                return_value=mock_service,
            ),
            patch(
                "app.services.pipeline.PipelineOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch("app.services.image_gen_cli.Session"),
        ):
            args = _make_run_args(dry_run=True)
            stats = asyncio.run(_run_full_pipeline(args))

        mock_service.prepare_execution.assert_not_called()
        mock_orchestrator.execute.assert_not_called()
        assert isinstance(stats, PipelineStats)

    def test_run_returns_stats_from_orchestrator_result(self) -> None:
        """The run command returns the stats object from the orchestrator result."""
        prepared = _make_prepared()
        expected_stats = PipelineStats()
        expected_stats.scenes_extracted = 10
        execute_result = PipelineExecutionResult(
            run_id=prepared.run_id,
            status="completed",
            stats=expected_stats,
        )
        mock_service = MagicMock()
        mock_service.prepare_execution.return_value = prepared
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute = AsyncMock(return_value=execute_result)

        with (
            patch(
                "app.services.pipeline.PipelineRunStartService",
                return_value=mock_service,
            ),
            patch(
                "app.services.pipeline.PipelineOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch("app.services.image_gen_cli.Session"),
        ):
            args = _make_run_args()
            stats = asyncio.run(_run_full_pipeline(args))

        assert stats.scenes_extracted == 10

    def test_run_builds_document_target_from_args(self) -> None:
        """The run command builds a DocumentTarget with book_slug and book_path from args."""
        prepared = _make_prepared()
        mock_service = MagicMock()
        mock_service.prepare_execution.return_value = prepared
        mock_orchestrator = MagicMock()
        mock_orchestrator.execute = AsyncMock(
            return_value=PipelineExecutionResult(
                run_id=prepared.run_id,
                status="completed",
                stats=PipelineStats(),
            )
        )

        with (
            patch(
                "app.services.pipeline.PipelineRunStartService",
                return_value=mock_service,
            ),
            patch(
                "app.services.pipeline.PipelineOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch("app.services.image_gen_cli.Session"),
        ):
            args = _make_run_args(
                book_slug="my-book",
                book_path="/tmp/my-book.epub",
            )
            asyncio.run(_run_full_pipeline(args))

        config_arg: PipelineExecutionConfig = mock_service.prepare_execution.call_args[
            0
        ][0]
        assert isinstance(config_arg.target, DocumentTarget)
        assert config_arg.target.book_slug == "my-book"
        assert config_arg.target.book_path == "/tmp/my-book.epub"
