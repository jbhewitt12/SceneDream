"""Prompt builder that orchestrates prompt assembly using strategies and core components."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from models.scene_extraction import SceneExtraction

from .core import CriticalConstraints, OutputSchemaBuilder, StyleSampler, ToneGuardrails
from .models import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationServiceError,
    PromptArtStylePlan,
)
from .strategies import PromptStrategyRegistry

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class PromptBuilder:
    """Orchestrates prompt assembly using core components and provider strategies."""

    def __init__(
        self,
        *,
        style_sampler: StyleSampler | None = None,
        tone_guardrails: ToneGuardrails | None = None,
        output_schema: OutputSchemaBuilder | None = None,
    ) -> None:
        self._style_sampler = style_sampler or StyleSampler()
        self._tone_guardrails = tone_guardrails or ToneGuardrails()
        self._output_schema = output_schema or OutputSchemaBuilder()
        self._cheatsheet_cache: dict[str, str] = {}

    def sample_styles(self, variants_count: int) -> list[str]:
        """Sample styles for the given number of variants."""
        return self._style_sampler.sample(variants_count)

    def build_prompt(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        context_text: str,
        context_window: Mapping[str, Any],
        style_plan: PromptArtStylePlan,
        target_provider: str,
    ) -> str:
        """
        Build the complete prompt for LLM submission.

        Args:
            scene: The scene to generate prompts for
            config: Generation configuration
            context_text: Surrounding context paragraphs
            context_window: Context window metadata
            style_plan: Resolved prompt art style plan
            target_provider: The target image provider name

        Returns:
            Complete prompt text

        Raises:
            ImagePromptGenerationServiceError: If scene is missing required data
            PromptStrategyNotFoundError: If no strategy for target_provider
        """
        strategy = PromptStrategyRegistry.get(target_provider)

        scene_excerpt = scene.raw.strip()
        if not scene_excerpt:
            raise ImagePromptGenerationServiceError(
                f"Scene {scene.id} is missing raw excerpt text"
            )

        # Build metadata block
        metadata_block = self._build_metadata_block(scene, context_window, config)

        # Get cheatsheet
        cheatsheet_path = config.include_cheatsheet_path
        strategy_cheatsheet = strategy.get_cheatsheet_path()
        if strategy_cheatsheet:
            cheatsheet_path = strategy_cheatsheet
        cheatsheet = self._load_cheatsheet(cheatsheet_path)

        # Get creative guidance with book-specific additions
        guidance = strategy.get_creative_guidance()
        book_guidance = self._tone_guardrails.get_book_specific_guidance(scene)
        if book_guidance:
            guidance += book_guidance

        # Get style strategy
        style_strategy = strategy.get_style_strategy(style_plan.mode)

        # Create constraints using strategy's aspect ratios (strategy is the source of truth)
        constraints = CriticalConstraints(
            allowed_aspect_ratios=strategy.get_supported_aspect_ratios()
        )
        aspect_ratio_display = constraints.aspect_ratio_display

        # Get quality objectives
        quality_objectives = strategy.get_quality_objectives(
            config.variants_count, aspect_ratio_display
        )

        # Get constraints
        critical_constraints = constraints.get_constraints_text()

        # Get tone guardrails
        tone_guardrails = self._tone_guardrails.get_guardrails_text()

        # Get output schema
        output_schema = self._output_schema.get_schema_json()

        # Assemble the prompt
        prompt = self._assemble_prompt(
            scene_excerpt=scene_excerpt,
            config=config,
            metadata_block=metadata_block,
            context_text=context_text,
            cheatsheet=cheatsheet,
            style_plan=style_plan,
            guidance=guidance,
            style_strategy=style_strategy,
            quality_objectives=quality_objectives,
            critical_constraints=critical_constraints,
            tone_guardrails=tone_guardrails,
            output_schema=output_schema,
            variants_count=config.variants_count,
            aspect_ratio_display=aspect_ratio_display,
        )

        return prompt

    def _build_metadata_block(
        self,
        scene: SceneExtraction,
        context_window: Mapping[str, Any],
        config: ImagePromptGenerationConfig,
    ) -> str:
        """Build the scene metadata block."""
        metadata_lines = [
            f"- Book slug: {scene.book_slug}",
            f"- Chapter number: {scene.chapter_number}",
            f"- Chapter title: {scene.chapter_title}",
            f"- Scene number: {scene.scene_number}",
            f"- Location marker: {scene.location_marker}",
            f"- Paragraph span: {context_window['paragraph_span'][0]}-{context_window['paragraph_span'][1]}",
            f"- Context paragraphs: {config.context_before} before, {config.context_after} after",
        ]
        return "\n".join(metadata_lines)

    def _assemble_prompt(
        self,
        *,
        scene_excerpt: str,
        config: ImagePromptGenerationConfig,
        metadata_block: str,
        context_text: str,
        cheatsheet: str,
        style_plan: PromptArtStylePlan,
        guidance: str,
        style_strategy: str,
        quality_objectives: str,
        critical_constraints: str,
        tone_guardrails: str,
        output_schema: str,
        variants_count: int,
        aspect_ratio_display: str,
    ) -> str:
        """Assemble the complete prompt from all components."""
        style_guidance = self._build_style_section(
            style_plan=style_plan,
            variants_count=variants_count,
        )
        output_requirements = self._build_output_requirements(
            style_plan=style_plan,
            output_schema=output_schema,
            variants_count=variants_count,
            aspect_ratio_display=aspect_ratio_display,
        )

        prompt_lines = [
            "You are an elite prompt engineer who converts novel scenes into world-class AI image prompts.",
            f"Your goal is to produce exactly {variants_count} distinct prompt variants that produce exceptional images.",
            "",
            "## Scene Metadata",
            metadata_block,
            "",
            "## Scene Excerpt (verbatim)",
            scene_excerpt,
        ]
        prompt = "\n".join(prompt_lines)
        prompt += (
            "\n\n## Surrounding Context Paragraphs\n"
            f"{context_text}\n\n"
            "## Prompting Cheat Sheet\n"
            f"{cheatsheet}\n\n"
            f"{style_guidance}"
            "## Creative Guidance\n"
            f"{guidance}\n\n"
            "## Style Variation Strategy\n"
            f"{style_strategy}\n\n"
            "## Quality Objectives\n"
            f"{quality_objectives}\n\n"
            "## Critical Constraints\n"
            f"{critical_constraints}\n\n"
            "## Tone Guardrails\n"
            f"{tone_guardrails}\n\n"
            "## Output Requirements\n"
            f"{output_requirements}"
        )
        return prompt

    def _build_style_section(
        self,
        *,
        style_plan: PromptArtStylePlan,
        variants_count: int,
    ) -> str:
        """Build the mode-aware style section."""

        if style_plan.sampled_styles:
            return (
                "## Suggested Styles for This Request\n"
                f"The following {len(style_plan.sampled_styles)} styles have been curated for variety and quality. "
                f"Select from this list when designing your {variants_count} variants, ensuring each variant uses a different style:\n"
                f"{', '.join(style_plan.sampled_styles)}\n\n"
            )

        if style_plan.style_text is None:
            raise ImagePromptGenerationServiceError(
                "single_style mode requires style text"
            )

        return (
            "## Fixed Art Style for This Request\n"
            "Use this exact art style consistently across every variant. "
            "Vary angle, composition, lighting, framing, and emotional emphasis without changing the core style:\n"
            f"{style_plan.style_text}\n\n"
        )

    def _build_output_requirements(
        self,
        *,
        style_plan: PromptArtStylePlan,
        output_schema: str,
        variants_count: int,
        aspect_ratio_display: str,
    ) -> str:
        """Build mode-aware output requirements."""

        style_variation_requirement = (
            "- Ensure each variant explores a different angle, subject emphasis, or aesthetic; do not reuse the same style family or medium twice.\n"
            if style_plan.sampled_styles
            else "- Ensure each variant explores a different angle, composition, lighting setup, or emotional emphasis while keeping the same art style across the full set.\n"
        )

        return (
            f"- Return ONLY strict JSON (no markdown) representing an array of {variants_count} objects.\n"
            "- Each array element must contain the keys: title, prompt_text, style_tags, attributes.\n"
            "- title can be null; prompt_text must be self-contained, visually clear, and built around a clear central subject plus one readable moment.\n"
            "- style_tags must be a list of short descriptors (2-5 entries).\n"
            "- attributes must detail composition, camera, lens, lighting, palette, atmosphere, aspect_ratio, style_intent, and references (list of influences or movements).\n"
            "- Make composition, perspective, and palette explicit in both prompt_text and attributes so the image direction is easy to interpret.\n"
            "- Use exclusion clauses only when they prevent a likely unwanted element; keep them brief and minimal.\n"
            f"{style_variation_requirement}"
            "- Do not include notes, warnings, or additional keys.\n"
            f"- The expected object shape is similar to: {output_schema}.\n"
            "- Never include copyrighted text beyond the provided excerpts."
        )

    def _load_cheatsheet(self, path_str: str) -> str:
        """Load and cache cheatsheet text."""
        if path_str in self._cheatsheet_cache:
            return self._cheatsheet_cache[path_str]

        path = Path(path_str)
        candidates: list[Path]
        if path.is_absolute():
            candidates = [path]
        else:
            candidates = [_BACKEND_ROOT / path]
            # Backward compatibility for legacy paths that started with "backend/".
            if path.parts and path.parts[0] == "backend":
                candidates.append(_BACKEND_ROOT / Path(*path.parts[1:]))

        resolved = next(
            (candidate for candidate in candidates if candidate.exists()), None
        )
        if resolved is None:
            raise ImagePromptGenerationServiceError(
                f"Cheat sheet file not found: {path_str}"
            )
        text = resolved.read_text(encoding="utf-8")
        self._cheatsheet_cache[path_str] = text.strip()
        return self._cheatsheet_cache[path_str]


__all__ = ["PromptBuilder"]
