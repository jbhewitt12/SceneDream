"""Shared models for image prompt generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PromptArtStyleMode,
    coerce_prompt_art_style_selection,
    normalize_prompt_art_style_text,
)
from app.services.langchain.model_routing import LLMProvider

DEFAULT_CHEATSHEET_PATH = (
    "app/services/image_prompt_generation/dalle3_multi_genre_prompting_cheatsheet.md"
)


class ImagePromptGenerationServiceError(RuntimeError):
    """Raised when image prompt generation fails under strict settings."""


@dataclass(slots=True)
class ImagePromptGenerationConfig:
    """Runtime configuration for image prompt generation."""

    model_vendor: LLMProvider = "google"
    model_name: str = "gemini-3-pro-preview"
    backup_model_vendor: LLMProvider = "openai"
    backup_model_name: str = "gpt-5-mini"
    prompt_version: str = "image-prompts-v3"
    prompt_art_style_mode: PromptArtStyleMode = cast(
        PromptArtStyleMode, PROMPT_ART_STYLE_MODE_RANDOM_MIX
    )
    prompt_art_style_text: str | None = None
    variants_count: int = 4
    use_ranking_recommendation: bool = True
    temperature: float = 0.4
    max_output_tokens: int | None = 8192
    context_before: int = 3
    context_after: int = 1
    include_cheatsheet_path: str = DEFAULT_CHEATSHEET_PATH
    target_provider: str = "gpt-image"
    blocked_warnings: set[str] = field(
        default_factory=lambda: {"violence", "sexual", "drugs", "horror", "hate"}
    )
    skip_scenes_with_warnings: bool = True
    dry_run: bool = False
    allow_overwrite: bool = False
    autocommit: bool = True
    retry_attempts: int = 2
    retry_backoff_seconds: float = 2.0
    fail_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.prompt_art_style_text = normalize_prompt_art_style_text(
            self.prompt_art_style_text
        )
        (
            resolved_mode,
            self.prompt_art_style_text,
        ) = coerce_prompt_art_style_selection(
            mode=self.prompt_art_style_mode,
            text=self.prompt_art_style_text,
        )
        self.prompt_art_style_mode = cast(PromptArtStyleMode, resolved_mode)

    def copy_with(self, **overrides: Any) -> ImagePromptGenerationConfig:
        data: dict[str, Any] = {
            "model_vendor": self.model_vendor,
            "model_name": self.model_name,
            "backup_model_vendor": self.backup_model_vendor,
            "backup_model_name": self.backup_model_name,
            "prompt_version": self.prompt_version,
            "prompt_art_style_mode": self.prompt_art_style_mode,
            "prompt_art_style_text": self.prompt_art_style_text,
            "variants_count": self.variants_count,
            "use_ranking_recommendation": self.use_ranking_recommendation,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "include_cheatsheet_path": self.include_cheatsheet_path,
            "target_provider": self.target_provider,
            "blocked_warnings": set(self.blocked_warnings),
            "skip_scenes_with_warnings": self.skip_scenes_with_warnings,
            "dry_run": self.dry_run,
            "allow_overwrite": self.allow_overwrite,
            "autocommit": self.autocommit,
            "retry_attempts": self.retry_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "fail_on_error": self.fail_on_error,
            "metadata": dict(self.metadata),
        }
        normalized_overrides: dict[str, Any] = {}
        for key, value in overrides.items():
            if key == "metadata":
                normalized_overrides[key] = dict(value) if value is not None else {}
            elif key == "blocked_warnings":
                normalized_overrides[key] = set(value) if value is not None else set()
            elif value is not None:
                normalized_overrides[key] = value
            elif key in {"max_output_tokens"}:
                normalized_overrides[key] = None
        data.update(normalized_overrides)
        return ImagePromptGenerationConfig(**data)


@dataclass(slots=True)
class PromptArtStylePlan:
    """Resolved prompt art-style behavior for a single generation request."""

    mode: PromptArtStyleMode
    style_text: str | None = None
    sampled_styles: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.style_text = normalize_prompt_art_style_text(self.style_text)
        self.sampled_styles = list(self.sampled_styles)
        (
            resolved_mode,
            self.style_text,
        ) = coerce_prompt_art_style_selection(
            mode=self.mode,
            text=self.style_text,
        )
        self.mode = cast(PromptArtStyleMode, resolved_mode)
        if self.mode != PROMPT_ART_STYLE_MODE_RANDOM_MIX:
            self.sampled_styles = []

    def to_metadata(self) -> dict[str, Any]:
        """Return a serializable metadata payload for persistence and previews."""

        payload: dict[str, Any] = {
            "mode": self.mode,
            "style_text": self.style_text,
        }
        if self.sampled_styles:
            payload["sampled_styles"] = list(self.sampled_styles)
        return payload


@dataclass(slots=True)
class ImagePromptPreview:
    """In-memory preview of generated image prompt variants."""

    scene_extraction_id: UUID
    variant_index: int
    title: str | None
    flavour_text: str | None
    prompt_text: str
    style_tags: list[str] | None
    attributes: dict[str, Any]
    prompt_version: str
    model_name: str
    model_vendor: str
    context_window: dict[str, Any]
    raw_response: dict[str, Any]
    temperature: float
    max_output_tokens: int | None
    execution_time_ms: int
    llm_request_id: str | None


__all__ = [
    "DEFAULT_CHEATSHEET_PATH",
    "ImagePromptGenerationConfig",
    "ImagePromptGenerationServiceError",
    "ImagePromptPreview",
    "PromptArtStylePlan",
]
