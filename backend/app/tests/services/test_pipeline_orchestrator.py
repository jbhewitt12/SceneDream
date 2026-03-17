"""Tests for the PipelineOrchestrator lifecycle, diagnostics, and usage summary."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from app.services.pipeline.orchestrator_config import (
    DocumentTarget,
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineExecutionContext,
    PipelineStagePlan,
    PipelineStats,
    PreparedPipelineExecution,
    PromptExecutionOptions,
    SceneTarget,
)
from app.services.pipeline.pipeline_orchestrator import (
    PipelineOrchestrator,
    RunDiagnosticsTracker,
    build_usage_summary,
    classify_pipeline_error_code,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prepared(
    *,
    run_extraction: bool = True,
    run_ranking: bool = True,
    run_prompt_generation: bool = True,
    run_image_generation: bool = True,
    book_slug: str = "test-book",
    book_path: str | None = "documents/test.epub",
    images_for_scenes: int | None = 2,
    prompt_art_style_mode: str = "random_mix",
    prompt_art_style_text: str | None = None,
    quality: str = "standard",
    style: str | None = None,
    aspect_ratio: str | None = None,
    config_overrides: dict[str, Any] | None = None,
    dry_run: bool = False,
    target: Any = None,
) -> PreparedPipelineExecution:
    if target is None:
        target = DocumentTarget(book_slug=book_slug, book_path=book_path)

    return PreparedPipelineExecution(
        run_id=uuid4(),
        config=PipelineExecutionConfig(
            target=target,
            stages=PipelineStagePlan(
                run_extraction=run_extraction,
                run_ranking=run_ranking,
                run_prompt_generation=run_prompt_generation,
                run_image_generation=run_image_generation,
            ),
            prompt_options=PromptExecutionOptions(
                images_for_scenes=images_for_scenes,
                prompt_art_style_mode=prompt_art_style_mode,
                prompt_art_style_text=prompt_art_style_text,
            ),
            image_options=ImageExecutionOptions(
                quality=quality,
                style=style,
                aspect_ratio=aspect_ratio,
            ),
            dry_run=dry_run,
        ),
        config_overrides=config_overrides or {"resolved_images_for_scenes": 2},
        context=PipelineExecutionContext(
            book_slug=book_slug,
            book_path=book_path,
            requested_image_count=images_for_scenes,
        ),
    )


def _noop(**kwargs: Any) -> None:
    """No-op stub for DB helpers."""


class _CapturingCallbacks:
    """Captures calls to orchestrator DB helpers."""

    def __init__(self) -> None:
        self.status_updates: list[dict[str, Any]] = []
        self.stage_running_calls: list[dict[str, Any]] = []
        self.stage_failed_calls: list[dict[str, Any]] = []
        self.sync_calls: list[dict[str, Any]] = []

    def update_run_status(self, **kwargs: Any) -> None:
        self.status_updates.append(kwargs)

    def set_document_stage_running(self, **kwargs: Any) -> None:
        self.stage_running_calls.append(kwargs)

    def set_document_stage_failed(self, **kwargs: Any) -> None:
        self.stage_failed_calls.append(kwargs)

    def sync_document_stage_statuses(self, **kwargs: Any) -> None:
        self.sync_calls.append(kwargs)

    def build_orchestrator(self, *, stub_stages: bool = True) -> PipelineOrchestrator:
        orchestrator = PipelineOrchestrator(
            update_run_status=self.update_run_status,
            set_document_stage_running=self.set_document_stage_running,
            set_document_stage_failed=self.set_document_stage_failed,
            sync_document_stage_statuses=self.sync_document_stage_statuses,
        )
        if stub_stages:
            _stub_stage_methods(orchestrator)
        return orchestrator


async def _noop_stage(
    prepared: PreparedPipelineExecution,  # noqa: ARG001
    stats: PipelineStats,  # noqa: ARG001
) -> None:
    """No-op async stub for stage methods."""


def _stub_stage_methods(orchestrator: PipelineOrchestrator) -> None:
    """Replace all stage methods with no-op stubs for lifecycle tests."""
    orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
    orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
    orchestrator._execute_prompt_generation = _noop_stage  # type: ignore[method-assign]
    orchestrator._execute_image_generation = _noop_stage  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Tests: RunDiagnosticsTracker
# ---------------------------------------------------------------------------


class TestRunDiagnosticsTracker:
    def test_initial_state_has_run_started_event(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        tracker = RunDiagnosticsTracker(run_id=uuid4(), started_at=now)
        assert tracker.current_stage is None
        assert len(tracker.stage_events) == 1
        assert tracker.stage_events[0]["type"] == "run_started"

    def test_start_stage_records_events(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        tracker = RunDiagnosticsTracker(run_id=uuid4(), started_at=now)
        tracker.start_stage(stage="extracting", at=now)
        assert tracker.current_stage == "extracting"
        assert any(
            e["type"] == "stage_started" and e["stage"] == "extracting"
            for e in tracker.stage_events
        )

    def test_start_stage_closes_previous_stage(self) -> None:
        from datetime import datetime, timedelta, timezone

        t0 = datetime.now(timezone.utc)
        tracker = RunDiagnosticsTracker(run_id=uuid4(), started_at=t0)
        tracker.start_stage(stage="extracting", at=t0)
        t1 = t0 + timedelta(seconds=1)
        completed, duration = tracker.start_stage(stage="ranking", at=t1)
        assert completed == "extracting"
        assert duration is not None and duration >= 1000

    def test_finalize_success(self) -> None:
        from datetime import datetime, timedelta, timezone

        t0 = datetime.now(timezone.utc)
        tracker = RunDiagnosticsTracker(run_id=uuid4(), started_at=t0)
        tracker.start_stage(stage="extracting", at=t0)
        t1 = t0 + timedelta(seconds=2)
        result = tracker.finalize(status_value="completed", completed_at=t1)
        assert result["observed_stage"] == "extracting"
        assert "extracting" in result["stage_durations_ms"]
        assert "error" not in result
        event_types = [e["type"] for e in result["stage_events"]]
        assert "run_completed" in event_types

    def test_finalize_failure_includes_error(self) -> None:
        from datetime import datetime, timezone

        t0 = datetime.now(timezone.utc)
        tracker = RunDiagnosticsTracker(run_id=uuid4(), started_at=t0)
        tracker.start_stage(stage="ranking", at=t0)
        result = tracker.finalize(
            status_value="failed",
            completed_at=t0,
            error_code="stage_error",
            error_message="ranking failed",
        )
        assert result["error"]["code"] == "stage_error"
        assert result["error"]["message"] == "ranking failed"
        assert result["error"]["stage"] == "ranking"


# ---------------------------------------------------------------------------
# Tests: classify_pipeline_error_code
# ---------------------------------------------------------------------------


class TestClassifyPipelineErrorCode:
    def test_missing_source_from_message(self) -> None:
        code = classify_pipeline_error_code(
            error_message="book_path is required for extraction"
        )
        assert code == "missing_source"

    def test_missing_source_from_exception(self) -> None:
        code = classify_pipeline_error_code(
            exc=RuntimeError("--book-path does not exist")
        )
        assert code == "missing_source"

    def test_value_error_is_invalid_request(self) -> None:
        code = classify_pipeline_error_code(exc=ValueError("bad input"))
        assert code == "invalid_request"

    def test_stage_error_from_observed_stage(self) -> None:
        code = classify_pipeline_error_code(
            exc=RuntimeError("boom"),
            observed_stage="generating_images",
        )
        assert code == "stage_error"

    def test_generic_exception(self) -> None:
        code = classify_pipeline_error_code(exc=RuntimeError("unknown"))
        assert code == "pipeline_exception"

    def test_no_exception_no_message(self) -> None:
        code = classify_pipeline_error_code()
        assert code == "pipeline_exception"


# ---------------------------------------------------------------------------
# Tests: build_usage_summary
# ---------------------------------------------------------------------------


class TestBuildUsageSummary:
    def test_success_shape(self) -> None:
        from datetime import datetime, timedelta, timezone

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            prompt_art_style_mode="single_style",
            prompt_art_style_text="Watercolor",
            quality="hd",
            style="vivid",
            aspect_ratio="16:9",
        )
        started = datetime.now(timezone.utc)
        completed = started + timedelta(seconds=5)
        stats = PipelineStats()
        stats.prompts_generated = 4
        stats.images_generated = 2

        summary = build_usage_summary(
            prepared=prepared,
            stats=stats,
            status_value="completed",
            started_at=started,
            completed_at=completed,
        )

        assert summary["status"] == "completed"
        assert summary["timing"]["duration_ms"] >= 5000
        assert summary["requested"]["skip_extraction"] is True
        assert summary["requested"]["skip_ranking"] is True
        assert summary["requested"]["skip_prompts"] is False
        assert summary["requested"]["mode"] == "sync"
        assert summary["requested"]["prompt_art_style_mode"] == "single_style"
        assert summary["requested"]["prompt_art_style_text"] == "Watercolor"
        assert summary["requested"]["quality"] == "hd"
        assert summary["requested"]["style"] == "vivid"
        assert summary["requested"]["aspect_ratio"] == "16:9"
        assert summary["outputs"]["prompts_generated"] == 4
        assert summary["outputs"]["images_generated"] == 2
        assert summary["errors"]["code"] is None
        assert summary["effective"]["config_overrides"] == prepared.config_overrides
        assert summary["effective"]["image_generation"]["mode"] == "sync"

    def test_failure_includes_error_info(self) -> None:
        from datetime import datetime, timezone

        prepared = _make_prepared()
        now = datetime.now(timezone.utc)
        summary = build_usage_summary(
            prepared=prepared,
            stats=None,
            status_value="failed",
            started_at=now,
            completed_at=now,
            error_message="extraction blew up",
            error_code="stage_error",
            diagnostics={"observed_stage": "extracting"},
        )

        assert summary["status"] == "failed"
        assert summary["errors"]["count"] >= 1
        assert summary["errors"]["code"] == "stage_error"
        assert summary["diagnostics"]["observed_stage"] == "extracting"

    def test_skip_flags_derived_from_stage_plan(self) -> None:
        """skip_* values come from the negation of the effective stage plan booleans."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        # Full pipeline: nothing skipped
        prepared_full = _make_prepared(
            run_extraction=True,
            run_ranking=True,
            run_prompt_generation=True,
            run_image_generation=True,
        )
        summary_full = build_usage_summary(
            prepared=prepared_full,
            stats=PipelineStats(),
            status_value="completed",
            started_at=now,
            completed_at=now,
        )
        assert summary_full["requested"]["skip_extraction"] is False
        assert summary_full["requested"]["skip_ranking"] is False
        assert summary_full["requested"]["skip_prompts"] is False

        # Prompt+image only: extraction/ranking skipped
        prepared_skip = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
        )
        summary_skip = build_usage_summary(
            prepared=prepared_skip,
            stats=PipelineStats(),
            status_value="completed",
            started_at=now,
            completed_at=now,
        )
        assert summary_skip["requested"]["skip_extraction"] is True
        assert summary_skip["requested"]["skip_ranking"] is True
        assert summary_skip["requested"]["skip_prompts"] is False


# ---------------------------------------------------------------------------
# Tests: PipelineOrchestrator lifecycle
# ---------------------------------------------------------------------------


class TestOrchestratorSuccess:
    def test_execute_success_with_all_stages(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared()

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        assert result.run_id == prepared.run_id
        assert result.error_message is None
        assert result.error_code is None

        # Usage summary is present and well-formed
        assert result.usage_summary["status"] == "completed"
        assert result.usage_summary["requested"]["skip_extraction"] is False
        assert result.usage_summary["requested"]["skip_ranking"] is False
        assert result.usage_summary["requested"]["mode"] == "sync"

        # Diagnostics are present
        assert "stage_durations_ms" in result.diagnostics
        assert "stage_events" in result.diagnostics
        event_types = [e["type"] for e in result.diagnostics["stage_events"]]
        assert "run_started" in event_types
        assert "run_completed" in event_types

        # Final status update was "completed"
        final_update = callbacks.status_updates[-1]
        assert final_update["status_value"] == "completed"
        assert final_update["current_stage"] == "completed"
        assert final_update["completed"] is True
        assert "usage_summary" in final_update

        # Document stage sync was called
        assert len(callbacks.sync_calls) == 1
        assert callbacks.sync_calls[0]["preserve_failed_pipeline_stage"] is None

    def test_execute_success_with_skipped_stages(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
        )

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"

        # Only prompt and image stages should have been transitioned
        stage_values = [
            u["current_stage"]
            for u in callbacks.status_updates
            if u.get("current_stage") not in ("completed",)
        ]
        assert "extracting" not in stage_values
        assert "ranking" not in stage_values
        assert "generating_prompts" in stage_values
        assert "generating_images" in stage_values

    def test_stage_transition_updates_status_and_document(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared(
            run_extraction=True,
            run_ranking=True,
            run_prompt_generation=False,
            run_image_generation=False,
        )

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        # Two stage transitions + final completed update
        stages_entered = [
            u["current_stage"]
            for u in callbacks.status_updates
            if u.get("current_stage") not in ("completed",)
        ]
        assert stages_entered == ["extracting", "ranking"]

        # Document stage running was called for extraction and ranking
        running_stages = [c["pipeline_stage"] for c in callbacks.stage_running_calls]
        assert "extracting" in running_stages
        assert "ranking" in running_stages


class TestOrchestratorFailure:
    def test_execute_failure_from_exception(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()

        # Make extraction raise an exception
        async def _failing_extraction(
            prepared: PreparedPipelineExecution,  # noqa: ARG001
            stats: PipelineStats,  # noqa: ARG001
        ) -> None:
            raise RuntimeError("extraction failed hard")

        orchestrator._execute_extraction = _failing_extraction  # type: ignore[method-assign]

        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "failed"
        assert result.error_message == "extraction failed hard"
        assert result.error_code == "stage_error"

        # Usage summary records failure
        assert result.usage_summary["status"] == "failed"
        assert result.usage_summary["errors"]["code"] == "stage_error"

        # Diagnostics include error
        assert result.diagnostics["error"]["code"] == "stage_error"
        assert result.diagnostics["error"]["message"] == "extraction failed hard"

        # Final status update was "failed"
        final_update = callbacks.status_updates[-1]
        assert final_update["status_value"] == "failed"
        assert final_update["completed"] is True

        # Document stage failed was called
        assert len(callbacks.stage_failed_calls) == 1
        assert (
            callbacks.stage_failed_calls[0]["error_message"] == "extraction failed hard"
        )

        # Sync was called with preserve
        assert len(callbacks.sync_calls) == 1
        assert callbacks.sync_calls[0]["preserve_failed_pipeline_stage"] == "extracting"

    def test_execute_failure_from_stats_errors(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()

        async def _erroring_extraction(
            prepared: PreparedPipelineExecution,  # noqa: ARG001
            stats: PipelineStats,
        ) -> None:
            stats.errors.append("partial extraction failure")

        orchestrator._execute_extraction = _erroring_extraction  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=True,
            run_ranking=False,
            run_prompt_generation=False,
            run_image_generation=False,
        )
        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "failed"
        assert "partial extraction failure" in (result.error_message or "")
        assert result.usage_summary["status"] == "failed"
        assert result.usage_summary["errors"]["count"] >= 1

    def test_failure_at_ranking_stage_preserves_failed_stage(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()

        async def _failing_ranking(
            prepared: PreparedPipelineExecution,  # noqa: ARG001
            stats: PipelineStats,  # noqa: ARG001
        ) -> None:
            raise RuntimeError("ranking crash")

        orchestrator._execute_ranking = _failing_ranking  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=True,
            run_ranking=True,
            run_prompt_generation=False,
            run_image_generation=False,
        )
        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "failed"
        assert result.diagnostics["error"]["stage"] == "ranking"

        assert len(callbacks.sync_calls) == 1
        assert callbacks.sync_calls[0]["preserve_failed_pipeline_stage"] == "ranking"

    def test_missing_source_error_classification(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()

        async def _missing_source(
            prepared: PreparedPipelineExecution,  # noqa: ARG001
            stats: PipelineStats,  # noqa: ARG001
        ) -> None:
            raise ValueError("--book-path is required for scene extraction")

        orchestrator._execute_extraction = _missing_source  # type: ignore[method-assign]

        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "failed"
        assert result.error_code == "missing_source"


class TestOrchestratorUsageSummaryCompatibility:
    """Verify the usage_summary shape remains backward-compatible."""

    def test_usage_summary_has_required_top_level_keys(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        summary = result.usage_summary
        assert "status" in summary
        assert "timing" in summary
        assert "requested" in summary
        assert "effective" in summary
        assert "outputs" in summary
        assert "errors" in summary
        assert "diagnostics" in summary

    def test_usage_summary_requested_has_skip_flags(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        requested = result.usage_summary["requested"]
        assert "skip_extraction" in requested
        assert "skip_ranking" in requested
        assert "skip_prompts" in requested
        assert "mode" in requested

    def test_usage_summary_effective_has_config_overrides(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared(
            config_overrides={
                "resolved_images_for_scenes": 5,
                "resolved_book_slug": "x",
            }
        )
        result = asyncio.run(orchestrator.execute(prepared))

        effective = result.usage_summary["effective"]
        assert "config_overrides" in effective
        assert effective["config_overrides"]["resolved_images_for_scenes"] == 5
        assert "prompt_generation" in effective
        assert "image_generation" in effective

    def test_usage_summary_outputs_has_stage_counts(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        outputs = result.usage_summary["outputs"]
        for key in [
            "scenes_extracted",
            "scenes_refined",
            "scenes_ranked",
            "prompts_generated",
            "images_generated",
        ]:
            assert key in outputs

    def test_usage_summary_mode_is_always_sync_for_orchestrated_runs(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        prepared = _make_prepared()
        result = asyncio.run(orchestrator.execute(prepared))

        assert result.usage_summary["requested"]["mode"] == "sync"
        assert result.usage_summary["effective"]["image_generation"]["mode"] == "sync"

    def test_resumed_stage_is_not_reported_as_skipped(self) -> None:
        """A stage that resumes partial work has run_X=True, so skip_X must be False."""
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()
        # Simulate a partial extraction resume - extraction is enabled
        prepared = _make_prepared(
            run_extraction=True,
            run_ranking=True,
        )
        prepared.context.extraction_resume_from_chapter = 3
        prepared.context.extraction_resume_from_chunk = 1

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.usage_summary["requested"]["skip_extraction"] is False


class TestOrchestratorContextCarry:
    """Verify the orchestrator reads/writes PipelineExecutionContext."""

    def test_result_reflects_context_state(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator()

        # Pre-populate context with some created IDs
        prepared = _make_prepared()
        prepared.context.created_prompt_ids = [uuid4(), uuid4()]
        prepared.context.created_image_ids = [uuid4()]

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        # Stats remain at 0 since stage stubs don't update them,
        # but context is preserved
        assert len(prepared.context.created_prompt_ids) == 2
        assert len(prepared.context.created_image_ids) == 1


class TestOrchestratorSceneTarget:
    """Verify the orchestrator handles non-document targets."""

    def test_scene_target_skips_extraction_and_ranking(self) -> None:
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator(stub_stages=False)

        scene_id = uuid4()

        async def _stub_with_image(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            stats.images_generated = 1
            prepared.context.created_image_ids.append(uuid4())

        orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_prompt_generation = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_image_generation = _stub_with_image  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
            target=SceneTarget(scene_ids=[scene_id], book_slug="test-book"),
        )

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        # No extraction or ranking stage transitions
        stage_values = [u["current_stage"] for u in callbacks.status_updates]
        assert "extracting" not in stage_values
        assert "ranking" not in stage_values
        assert "generating_prompts" in stage_values
        assert "generating_images" in stage_values

    def test_scene_target_exact_prompt_ids_passed_to_image_generation(self) -> None:
        """Image generation must use the exact prompt IDs created during
        prompt generation, not a broader query."""
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator(stub_stages=False)

        scene_id = uuid4()
        prompt_ids = [uuid4(), uuid4(), uuid4()]
        image_ids = [uuid4()]

        async def _fake_prompt_gen(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            stats.prompts_generated = len(prompt_ids)
            prepared.context.created_prompt_ids.extend(prompt_ids)
            for pid in prompt_ids:
                prepared.context.created_prompt_ids_by_scene.setdefault(
                    scene_id, []
                ).append(pid)

        captured_prompt_ids: list[Any] = []

        async def _fake_image_gen(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            # Capture what prompt IDs the image generation sees
            captured_prompt_ids.extend(prepared.context.created_prompt_ids)
            stats.images_generated = len(image_ids)
            prepared.context.created_image_ids.extend(image_ids)

        orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_prompt_generation = _fake_prompt_gen  # type: ignore[method-assign]
        orchestrator._execute_image_generation = _fake_image_gen  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
            target=SceneTarget(scene_ids=[scene_id], book_slug="test-book"),
        )
        prepared.config.prompt_options.scene_variant_count = 3
        prepared.config.prompt_options.require_exact_scene_variants = True

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        assert captured_prompt_ids == prompt_ids
        assert result.stats.prompts_generated == 3
        assert result.stats.images_generated == 1

    def test_scene_target_partial_success_with_errors(self) -> None:
        """Scene-targeted run succeeds if at least one image is generated,
        even when some prompt generation errors occurred."""
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator(stub_stages=False)

        scene_id = uuid4()

        async def _prompt_with_error(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            prompt_id = uuid4()
            stats.prompts_generated = 1
            prepared.context.created_prompt_ids.append(prompt_id)
            stats.errors.append("Partial prompt failure for one variant")

        async def _image_gen_success(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            stats.images_generated = 1
            prepared.context.created_image_ids.append(uuid4())

        orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_prompt_generation = _prompt_with_error  # type: ignore[method-assign]
        orchestrator._execute_image_generation = _image_gen_success  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
            target=SceneTarget(scene_ids=[scene_id], book_slug="test-book"),
        )

        result = asyncio.run(orchestrator.execute(prepared))

        # Partial success: at least one image generated
        assert result.status == "completed"

    def test_scene_target_zero_images_is_failure(self) -> None:
        """Scene-targeted run fails if zero images are generated."""
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator(stub_stages=False)

        scene_id = uuid4()

        async def _prompt_gen_empty(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            # No prompts generated
            pass

        async def _image_gen_empty(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            # No images generated
            pass

        orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_prompt_generation = _prompt_gen_empty  # type: ignore[method-assign]
        orchestrator._execute_image_generation = _image_gen_empty  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
            target=SceneTarget(scene_ids=[scene_id], book_slug="test-book"),
        )

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "failed"
        assert "No images were generated" in (result.error_message or "")

    def test_scene_target_image_stage_does_not_fan_out(self) -> None:
        """Image stage must consume only the prompt IDs from this run,
        not all prompts for the scene."""
        callbacks = _CapturingCallbacks()
        orchestrator = callbacks.build_orchestrator(stub_stages=False)

        scene_id = uuid4()
        run_prompt_id = uuid4()

        async def _scene_prompt_gen(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            stats.prompts_generated = 1
            prepared.context.created_prompt_ids.append(run_prompt_id)

        image_gen_prompt_ids: list[Any] = []

        async def _capturing_image_gen(
            prepared: PreparedPipelineExecution,
            stats: PipelineStats,
        ) -> None:
            image_gen_prompt_ids.extend(prepared.context.created_prompt_ids)
            stats.images_generated = 1
            prepared.context.created_image_ids.append(uuid4())

        orchestrator._execute_extraction = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_ranking = _noop_stage  # type: ignore[method-assign]
        orchestrator._execute_prompt_generation = _scene_prompt_gen  # type: ignore[method-assign]
        orchestrator._execute_image_generation = _capturing_image_gen  # type: ignore[method-assign]

        prepared = _make_prepared(
            run_extraction=False,
            run_ranking=False,
            run_prompt_generation=True,
            run_image_generation=True,
            target=SceneTarget(scene_ids=[scene_id], book_slug="test-book"),
        )

        result = asyncio.run(orchestrator.execute(prepared))

        assert result.status == "completed"
        # Image generation must see exactly the one prompt from this run
        assert image_gen_prompt_ids == [run_prompt_id]
