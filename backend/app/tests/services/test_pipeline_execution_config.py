"""Tests for pipeline orchestration config types (Phase 1)."""

from __future__ import annotations

import uuid

from app.services.pipeline.orchestrator_config import (
    CustomRemixTarget,
    DocumentTarget,
    ImageExecutionOptions,
    PipelineExecutionConfig,
    PipelineExecutionContext,
    PipelineExecutionResult,
    PipelineStagePlan,
    PipelineStats,
    PreparedPipelineExecution,
    PromptExecutionOptions,
    RemixTarget,
    SceneTarget,
)

# ---------------------------------------------------------------------------
# PipelineStagePlan validation
# ---------------------------------------------------------------------------


class TestPipelineStagePlanValidation:
    def test_extraction_requires_document_target(self) -> None:
        plan = PipelineStagePlan(
            run_extraction=True, run_prompt_generation=True, run_image_generation=True
        )
        errors = plan.validate_for_target(SceneTarget(scene_ids=[uuid.uuid4()]))
        assert any("Extraction requires a DocumentTarget" in e for e in errors)

    def test_ranking_requires_document_target(self) -> None:
        plan = PipelineStagePlan(
            run_ranking=True, run_prompt_generation=True, run_image_generation=True
        )
        errors = plan.validate_for_target(RemixTarget())
        assert any("Ranking requires a DocumentTarget" in e for e in errors)

    def test_image_generation_requires_prompt_generation(self) -> None:
        plan = PipelineStagePlan(run_image_generation=True)
        errors = plan.validate_for_target(DocumentTarget())
        assert any("Image generation requires prompt generation" in e for e in errors)

    def test_at_least_one_stage_required(self) -> None:
        plan = PipelineStagePlan()
        errors = plan.validate_for_target(DocumentTarget())
        assert any("At least one stage must be enabled" in e for e in errors)

    def test_valid_full_pipeline(self) -> None:
        plan = PipelineStagePlan(
            run_extraction=True,
            run_ranking=True,
            run_prompt_generation=True,
            run_image_generation=True,
        )
        errors = plan.validate_for_target(DocumentTarget(book_slug="test"))
        assert errors == []

    def test_valid_prompt_and_image_only(self) -> None:
        plan = PipelineStagePlan(
            run_prompt_generation=True,
            run_image_generation=True,
        )
        errors = plan.validate_for_target(SceneTarget(scene_ids=[uuid.uuid4()]))
        assert errors == []

    def test_extraction_only_is_valid_for_document(self) -> None:
        plan = PipelineStagePlan(run_extraction=True)
        errors = plan.validate_for_target(DocumentTarget(book_slug="test"))
        assert errors == []

    def test_ranking_only_is_valid_for_document(self) -> None:
        plan = PipelineStagePlan(run_ranking=True)
        errors = plan.validate_for_target(DocumentTarget(book_slug="test"))
        assert errors == []

    def test_prompt_generation_only_is_valid(self) -> None:
        """Prompt generation without image generation is valid (dry-run etc)."""
        plan = PipelineStagePlan(run_prompt_generation=True)
        errors = plan.validate_for_target(DocumentTarget(book_slug="test"))
        assert errors == []


# ---------------------------------------------------------------------------
# PipelineExecutionConfig validation
# ---------------------------------------------------------------------------


class TestPipelineExecutionConfigValidation:
    def test_valid_full_pipeline(self) -> None:
        config = PipelineExecutionConfig(
            target=DocumentTarget(book_slug="test"),
            stages=PipelineStagePlan(
                run_extraction=True,
                run_ranking=True,
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        assert config.validate() == []

    def test_valid_scene_target(self) -> None:
        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[uuid.uuid4()]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(
                scene_variant_count=3,
                require_exact_scene_variants=True,
            ),
        )
        assert config.validate() == []

    def test_valid_remix_target(self) -> None:
        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=uuid.uuid4(),
                source_prompt_id=uuid.uuid4(),
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        assert config.validate() == []

    def test_valid_custom_remix_target(self) -> None:
        config = PipelineExecutionConfig(
            target=CustomRemixTarget(
                source_image_id=uuid.uuid4(),
                source_prompt_id=uuid.uuid4(),
                custom_prompt_text="A painting of a castle",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        assert config.validate() == []

    def test_scene_target_requires_scene_ids(self) -> None:
        config = PipelineExecutionConfig(
            target=SceneTarget(),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        errors = config.validate()
        assert any("SceneTarget requires at least one scene_id" in e for e in errors)

    def test_require_exact_variants_needs_variant_count(self) -> None:
        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[uuid.uuid4()]),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(
                require_exact_scene_variants=True,
            ),
        )
        errors = config.validate()
        assert any(
            "require_exact_scene_variants requires scene_variant_count" in e
            for e in errors
        )

    def test_extraction_on_scene_target_invalid(self) -> None:
        config = PipelineExecutionConfig(
            target=SceneTarget(scene_ids=[uuid.uuid4()]),
            stages=PipelineStagePlan(
                run_extraction=True,
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        errors = config.validate()
        assert any("Extraction requires a DocumentTarget" in e for e in errors)

    def test_no_stages_is_invalid(self) -> None:
        config = PipelineExecutionConfig(target=DocumentTarget(book_slug="test"))
        errors = config.validate()
        assert any("At least one stage must be enabled" in e for e in errors)


# ---------------------------------------------------------------------------
# PipelineExecutionConfig.copy_with
# ---------------------------------------------------------------------------


class TestPipelineExecutionConfigCopyWith:
    def test_copy_with_preserves_original(self) -> None:
        original = PipelineExecutionConfig(
            target=DocumentTarget(book_slug="test"),
            stages=PipelineStagePlan(run_extraction=True),
            dry_run=False,
        )
        copy = original.copy_with(dry_run=True)
        assert copy.dry_run is True
        assert original.dry_run is False

    def test_copy_with_replaces_target(self) -> None:
        original = PipelineExecutionConfig(
            target=DocumentTarget(book_slug="old"),
        )
        new_target = DocumentTarget(book_slug="new")
        copy = original.copy_with(target=new_target)
        assert isinstance(copy.target, DocumentTarget)
        assert copy.target.book_slug == "new"
        assert isinstance(original.target, DocumentTarget)
        assert original.target.book_slug == "old"


# ---------------------------------------------------------------------------
# Config expressiveness (can describe all four run types)
# ---------------------------------------------------------------------------


class TestConfigExpressiveness:
    def test_full_pipeline_config(self) -> None:
        config = PipelineExecutionConfig(
            target=DocumentTarget(
                document_id=uuid.uuid4(),
                book_slug="test-book",
                book_path="documents/test-book.epub",
            ),
            stages=PipelineStagePlan(
                run_extraction=True,
                run_ranking=True,
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(
                images_for_scenes=5,
                prompt_art_style_mode="random_mix",
            ),
            image_options=ImageExecutionOptions(quality="hd"),
        )
        assert config.validate() == []

    def test_scene_targeted_config(self) -> None:
        scene_id = uuid.uuid4()
        config = PipelineExecutionConfig(
            target=SceneTarget(
                scene_ids=[scene_id],
                document_id=uuid.uuid4(),
                book_slug="test-book",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
            prompt_options=PromptExecutionOptions(
                scene_variant_count=3,
                require_exact_scene_variants=True,
            ),
        )
        assert config.validate() == []

    def test_remix_config(self) -> None:
        config = PipelineExecutionConfig(
            target=RemixTarget(
                source_image_id=uuid.uuid4(),
                source_prompt_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                book_slug="test-book",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        assert config.validate() == []

    def test_custom_remix_config(self) -> None:
        config = PipelineExecutionConfig(
            target=CustomRemixTarget(
                source_image_id=uuid.uuid4(),
                source_prompt_id=uuid.uuid4(),
                custom_prompt_text="A dramatic sunset scene",
                document_id=uuid.uuid4(),
                book_slug="test-book",
            ),
            stages=PipelineStagePlan(
                run_prompt_generation=True,
                run_image_generation=True,
            ),
        )
        assert config.validate() == []


# ---------------------------------------------------------------------------
# PipelineExecutionContext stage-output handoff
# ---------------------------------------------------------------------------


class TestPipelineExecutionContext:
    def test_prompt_ids_accumulate(self) -> None:
        ctx = PipelineExecutionContext()
        prompt_id_1 = uuid.uuid4()
        prompt_id_2 = uuid.uuid4()
        ctx.created_prompt_ids.append(prompt_id_1)
        ctx.created_prompt_ids.append(prompt_id_2)
        assert ctx.created_prompt_ids == [prompt_id_1, prompt_id_2]

    def test_prompt_ids_by_scene_handoff(self) -> None:
        ctx = PipelineExecutionContext()
        scene_id = uuid.uuid4()
        prompt_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        ctx.created_prompt_ids_by_scene[scene_id] = prompt_ids
        ctx.created_prompt_ids.extend(prompt_ids)

        assert ctx.created_prompt_ids_by_scene[scene_id] == prompt_ids
        assert len(ctx.created_prompt_ids) == 3

    def test_image_ids_track_success_and_failure(self) -> None:
        ctx = PipelineExecutionContext()
        ok = uuid.uuid4()
        fail = uuid.uuid4()
        ctx.created_image_ids.append(ok)
        ctx.failed_image_ids.append(fail)
        assert ctx.created_image_ids == [ok]
        assert ctx.failed_image_ids == [fail]

    def test_context_instances_are_independent(self) -> None:
        """Verify default_factory isolation (no shared mutable defaults)."""
        ctx_a = PipelineExecutionContext()
        ctx_b = PipelineExecutionContext()
        ctx_a.created_prompt_ids.append(uuid.uuid4())
        assert ctx_b.created_prompt_ids == []

    def test_preparation_fields_preserved(self) -> None:
        doc_id = uuid.uuid4()
        scene_id = uuid.uuid4()
        ctx = PipelineExecutionContext(
            document_id=doc_id,
            book_slug="test",
            book_path="documents/test.epub",
            extraction_resume_from_chapter=3,
            extraction_resume_from_chunk=7,
            ranking_scene_ids=[scene_id],
            ranking_resume_scene_id=scene_id,
            requested_image_count=5,
        )
        assert ctx.document_id == doc_id
        assert ctx.extraction_resume_from_chapter == 3
        assert ctx.extraction_resume_from_chunk == 7
        assert ctx.ranking_scene_ids == [scene_id]
        assert ctx.ranking_resume_scene_id == scene_id
        assert ctx.requested_image_count == 5


# ---------------------------------------------------------------------------
# Effective config does not carry contradictory skip/run representations
# ---------------------------------------------------------------------------


class TestNoContradictoryStageSkipFlags:
    """The effective config uses PipelineStagePlan booleans only.

    There must not be separate ``skip_*`` fields that could contradict
    the ``run_*`` stage booleans.
    """

    def test_config_has_no_skip_fields(self) -> None:
        config = PipelineExecutionConfig(target=DocumentTarget())
        field_names = {f.name for f in config.__dataclass_fields__.values()}
        skip_fields = {n for n in field_names if n.startswith("skip_")}
        assert skip_fields == set(), f"unexpected skip fields: {skip_fields}"

    def test_stage_plan_has_no_skip_fields(self) -> None:
        plan = PipelineStagePlan()
        field_names = {f.name for f in plan.__dataclass_fields__.values()}
        skip_fields = {n for n in field_names if n.startswith("skip_")}
        assert skip_fields == set(), f"unexpected skip fields: {skip_fields}"


# ---------------------------------------------------------------------------
# PreparedPipelineExecution
# ---------------------------------------------------------------------------


class TestPreparedPipelineExecution:
    def test_construction(self) -> None:
        run_id = uuid.uuid4()
        config = PipelineExecutionConfig(
            target=DocumentTarget(book_slug="test"),
            stages=PipelineStagePlan(run_extraction=True),
        )
        prepared = PreparedPipelineExecution(
            run_id=run_id,
            config=config,
            config_overrides={"book_slug": "test"},
            context=PipelineExecutionContext(book_slug="test"),
        )
        assert prepared.run_id == run_id
        assert prepared.config is config
        assert prepared.config_overrides["book_slug"] == "test"
        assert prepared.context.book_slug == "test"


# ---------------------------------------------------------------------------
# PipelineStats (moved from image_gen_cli)
# ---------------------------------------------------------------------------


class TestPipelineStats:
    def test_defaults_are_zero(self) -> None:
        stats = PipelineStats()
        assert stats.scenes_extracted == 0
        assert stats.scenes_refined == 0
        assert stats.scenes_ranked == 0
        assert stats.prompts_generated == 0
        assert stats.images_generated == 0
        assert stats.errors == []

    def test_to_dict(self) -> None:
        stats = PipelineStats()
        stats.scenes_extracted = 10
        stats.prompts_generated = 5
        stats.errors.append("oops")
        d = stats.to_dict()
        assert d["scenes_extracted"] == 10
        assert d["prompts_generated"] == 5
        assert d["errors"] == ["oops"]

    def test_backward_compatible_import_from_cli(self) -> None:
        from app.services.image_gen_cli import PipelineStats as CliStats

        assert CliStats is PipelineStats


# ---------------------------------------------------------------------------
# PipelineExecutionResult
# ---------------------------------------------------------------------------


class TestPipelineExecutionResult:
    def test_completed_result(self) -> None:
        run_id = uuid.uuid4()
        stats = PipelineStats()
        stats.images_generated = 3
        result = PipelineExecutionResult(
            run_id=run_id,
            status="completed",
            stats=stats,
            diagnostics={"events": []},
            usage_summary={"outputs": {"images_generated": 3}},
        )
        assert result.status == "completed"
        assert result.stats.images_generated == 3
        assert result.error_message is None

    def test_failed_result(self) -> None:
        run_id = uuid.uuid4()
        result = PipelineExecutionResult(
            run_id=run_id,
            status="failed",
            error_message="extraction failed",
            error_code="EXTRACTION_ERROR",
        )
        assert result.status == "failed"
        assert result.error_message == "extraction failed"
        assert result.error_code == "EXTRACTION_ERROR"
