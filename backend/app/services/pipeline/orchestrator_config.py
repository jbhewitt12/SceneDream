"""Orchestration config, context, and result types for pipeline execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Execution targets
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DocumentTarget:
    """Full-document pipeline target."""

    document_id: uuid.UUID | None = None
    book_slug: str | None = None
    book_path: str | None = None


@dataclass(slots=True)
class SceneTarget:
    """Scene-specific prompt/image generation target."""

    scene_ids: list[uuid.UUID] = field(default_factory=list)
    document_id: uuid.UUID | None = None
    book_slug: str | None = None


@dataclass(slots=True)
class RemixTarget:
    """Remix an existing generated image."""

    source_image_id: uuid.UUID = field(default_factory=uuid.uuid4)
    source_prompt_id: uuid.UUID = field(default_factory=uuid.uuid4)
    document_id: uuid.UUID | None = None
    book_slug: str | None = None


@dataclass(slots=True)
class CustomRemixTarget:
    """Custom-remix with user-supplied prompt text."""

    source_image_id: uuid.UUID = field(default_factory=uuid.uuid4)
    source_prompt_id: uuid.UUID = field(default_factory=uuid.uuid4)
    custom_prompt_id: uuid.UUID | None = None
    custom_prompt_text: str | None = None
    document_id: uuid.UUID | None = None
    book_slug: str | None = None


PipelineExecutionTarget = DocumentTarget | SceneTarget | RemixTarget | CustomRemixTarget

# ---------------------------------------------------------------------------
# Stage plan
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineStagePlan:
    """Explicit booleans for which stages to execute."""

    run_extraction: bool = False
    run_ranking: bool = False
    run_prompt_generation: bool = False
    run_image_generation: bool = False

    def copy_with(self, **overrides: Any) -> PipelineStagePlan:
        """Return a shallow copy with field overrides applied."""
        import dataclasses

        return dataclasses.replace(self, **overrides)

    def validate_for_target(self, target: PipelineExecutionTarget) -> list[str]:
        """Return a list of validation error messages (empty means valid)."""
        errors: list[str] = []

        is_document_target = isinstance(target, DocumentTarget)

        if self.run_extraction and not is_document_target:
            errors.append("Extraction requires a DocumentTarget.")
        if self.run_ranking and not is_document_target:
            errors.append("Ranking requires a DocumentTarget.")

        if self.run_image_generation and not self.run_prompt_generation:
            errors.append(
                "Image generation requires prompt generation in the same run."
            )

        if not any(
            [
                self.run_extraction,
                self.run_ranking,
                self.run_prompt_generation,
                self.run_image_generation,
            ]
        ):
            errors.append("At least one stage must be enabled.")

        return errors


# ---------------------------------------------------------------------------
# Execution options
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PromptExecutionOptions:
    """Options governing prompt generation behavior."""

    prompts_per_scene: int | None = None
    ignore_ranking_recommendations: bool = False
    prompts_for_scenes: int | None = None
    images_for_scenes: int | None = None
    scene_variant_count: int | None = None
    variants_count: int | None = None
    overwrite_prompts: bool = False
    prompt_version: str | None = None
    prompt_art_style_mode: str | None = None
    prompt_art_style_text: str | None = None
    require_exact_scene_variants: bool = False

    def copy_with(self, **overrides: Any) -> PromptExecutionOptions:
        """Return a shallow copy with field overrides applied."""
        import dataclasses

        return dataclasses.replace(self, **overrides)


@dataclass(slots=True)
class ImageExecutionOptions:
    """Options governing image generation behavior."""

    quality: str = "standard"
    style: str | None = None
    aspect_ratio: str | None = None
    concurrency: int = 3


# ---------------------------------------------------------------------------
# Execution config
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineExecutionConfig:
    """Effective execution contract built during preparation."""

    target: PipelineExecutionTarget
    stages: PipelineStagePlan = field(default_factory=PipelineStagePlan)
    prompt_options: PromptExecutionOptions = field(
        default_factory=PromptExecutionOptions
    )
    image_options: ImageExecutionOptions = field(default_factory=ImageExecutionOptions)
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def copy_with(self, **overrides: Any) -> PipelineExecutionConfig:
        """Return a shallow copy with field overrides applied."""
        import dataclasses

        return dataclasses.replace(self, **overrides)

    def validate(self) -> list[str]:
        """Return all validation errors for this config."""
        errors = self.stages.validate_for_target(self.target)

        if isinstance(self.target, SceneTarget) and not self.target.scene_ids:
            errors.append("SceneTarget requires at least one scene_id.")

        if (
            self.prompt_options.require_exact_scene_variants
            and self.prompt_options.scene_variant_count is None
        ):
            errors.append(
                "require_exact_scene_variants requires scene_variant_count to be set."
            )

        return errors


# ---------------------------------------------------------------------------
# Execution context (runtime state carried across stages)
# ---------------------------------------------------------------------------


@dataclass
class PipelineExecutionContext:
    """Mutable runtime state populated during preparation and updated by stages."""

    # Preparation-owned fields
    document_id: uuid.UUID | None = None
    book_slug: str | None = None
    book_path: str | None = None
    extraction_resume_from_chapter: int | None = None
    extraction_resume_from_chunk: int | None = None
    ranking_scene_ids: list[uuid.UUID] | None = None
    ranking_resume_scene_id: uuid.UUID | None = None
    requested_image_count: int | None = None

    # Execution-owned fields
    created_ranking_ids: list[uuid.UUID] = field(default_factory=list)
    created_prompt_ids: list[uuid.UUID] = field(default_factory=list)
    created_prompt_ids_by_scene: dict[uuid.UUID, list[uuid.UUID]] = field(
        default_factory=dict
    )
    created_image_ids: list[uuid.UUID] = field(default_factory=list)
    failed_image_ids: list[uuid.UUID] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prepared execution (output of preparation, input to orchestrator)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PreparedPipelineExecution:
    """Fully resolved execution ready to be handed to the orchestrator."""

    run_id: uuid.UUID
    config: PipelineExecutionConfig
    config_overrides: dict[str, Any] = field(default_factory=dict)
    context: PipelineExecutionContext = field(default_factory=PipelineExecutionContext)


# ---------------------------------------------------------------------------
# Pipeline stats
# ---------------------------------------------------------------------------


class PipelineStats:
    """Track statistics across the pipeline."""

    def __init__(self) -> None:
        self.scenes_extracted = 0
        self.scenes_refined = 0
        self.scenes_ranked = 0
        self.prompts_generated = 0
        self.images_generated = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "scenes_extracted": self.scenes_extracted,
            "scenes_refined": self.scenes_refined,
            "scenes_ranked": self.scenes_ranked,
            "prompts_generated": self.prompts_generated,
            "images_generated": self.images_generated,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineExecutionResult:
    """Outcome of an orchestrator execution."""

    run_id: uuid.UUID
    status: Literal["completed", "failed"]
    stats: PipelineStats = field(default_factory=PipelineStats)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    usage_summary: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    error_code: str | None = None
