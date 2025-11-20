"""Variant extraction and record-building helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

from .models import (
    ImagePromptGenerationConfig,
    ImagePromptGenerationServiceError,
)

logger = logging.getLogger(__name__)

ALLOWED_ASPECT_RATIOS = ("1:1", "16:9", "9:16")
_BANNED_STYLE_TERMS = (
    "photorealistic",
    "photorealism",
    "photo realistic",
    "photo-realistic",
    "photoreal",
    "photo real",
    "hyperrealistic",
    "hyper-realistic",
    "hyper realistic",
    "ultra realistic",
    "ultrarealistic",
    "ultra-realistic",
    "live-action",
    "live action",
)


class VariantModel(BaseModel):
    """Validate the structure returned by the LLM."""

    title: str | None = None
    prompt_text: str
    style_tags: list[str] | None = None
    attributes: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> VariantModel:
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover - raised with context
            raise ImagePromptGenerationServiceError(
                "LLM response did not match the required variant schema"
            ) from exc


class VariantProcessor:
    """Handle variant validation and persistence payload assembly."""

    def __init__(
        self,
        *,
        banned_style_terms: Sequence[str] = _BANNED_STYLE_TERMS,
        allowed_aspect_ratios: Sequence[str] = ALLOWED_ASPECT_RATIOS,
    ) -> None:
        self._banned_style_terms = tuple(banned_style_terms)
        self._allowed_aspect_ratios = tuple(allowed_aspect_ratios)
        normalized_map = {
            value.replace(" ", "").lower(): value for value in allowed_aspect_ratios
        }
        self._allowed_ratio_tokens = set(normalized_map)
        self._normalized_ratio_map = normalized_map
        self._fallback_aspect_ratio = (
            self._allowed_aspect_ratios[0] if self._allowed_aspect_ratios else None
        )

    def extract_variants(
        self,
        payload: Any,
        config: ImagePromptGenerationConfig,
    ) -> list[VariantModel]:
        if isinstance(payload, dict) and "variants" in payload:
            payload = payload["variants"]
        if not isinstance(payload, Sequence):
            raise ImagePromptGenerationServiceError(
                "Gemini response must be a JSON array of variant objects"
            )
        variants = []
        for index, item in enumerate(payload):
            if not isinstance(item, Mapping):
                raise ImagePromptGenerationServiceError(
                    f"Variant {index} is not a JSON object"
                )
            variant = VariantModel.from_payload(item)
            issues = self._enforce_variant_constraints(variant)
            if issues:
                logger.warning(
                    "Variant constraint issues detected for index %s: %s",
                    index,
                    "; ".join(issues),
                )
            variants.append(variant)
        if len(variants) != config.variants_count:
            raise ImagePromptGenerationServiceError(
                f"Expected {config.variants_count} variants, received {len(variants)}"
            )
        return variants

    def build_records(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        variants: Sequence[VariantModel],
        variant_indices: Sequence[int],
        context_window: Mapping[str, Any],
        raw_payload: Mapping[str, Any],
        llm_request_id: str | None,
        execution_time_ms: int,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, variant in enumerate(variants):
            try:
                variant_index = variant_indices[index]
            except IndexError as exc:  # pragma: no cover - defensive
                raise ImagePromptGenerationServiceError(
                    "Variant indices length did not match variant payloads"
                ) from exc
            style_tags = list(variant.style_tags) if variant.style_tags else None
            attributes = dict(variant.attributes)
            records.append(
                {
                    "scene_extraction_id": scene.id,
                    "model_vendor": config.model_vendor,
                    "model_name": config.model_name,
                    "prompt_version": config.prompt_version,
                    "variant_index": variant_index,
                    "title": variant.title.strip()
                    if isinstance(variant.title, str)
                    else None,
                    "prompt_text": variant.prompt_text.strip(),
                    "negative_prompt": None,
                    "style_tags": style_tags,
                    "attributes": attributes,
                    "notes": None,
                    "context_window": dict(context_window),
                    "raw_response": dict(raw_payload),
                    "temperature": config.temperature,
                    "max_output_tokens": config.max_output_tokens,
                    "llm_request_id": llm_request_id,
                    "execution_time_ms": execution_time_ms,
                }
            )
        return records

    def instantiate_prompts_from_records(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> list[ImagePrompt]:
        """Create transient ImagePrompt models from in-memory records."""
        prompts: list[ImagePrompt] = []
        for record in records:
            prompts.append(ImagePrompt(**record))  # type: ignore[arg-type]
        return prompts

    def _enforce_variant_constraints(self, variant: VariantModel) -> list[str]:
        issues: list[str] = []
        prompt_lower = variant.prompt_text.lower()
        for banned in self._banned_style_terms:
            if banned in prompt_lower:
                issues.append(
                    f"prompt_text contains banned realism descriptor '{banned}'"
                )
        for tag in variant.style_tags or []:
            tag_lower = tag.lower()
            for banned in self._banned_style_terms:
                if banned in tag_lower:
                    issues.append(
                        f"style tag '{tag}' includes banned realism descriptor '{banned}'"
                    )
        if not isinstance(variant.attributes, dict):
            variant.attributes = {}
        attributes = variant.attributes
        needs_fallback = True
        aspect_ratio_raw = attributes.get("aspect_ratio")
        if not isinstance(aspect_ratio_raw, str):
            issues.append("attributes.aspect_ratio is missing or not a string")
        else:
            normalized_ratio = aspect_ratio_raw.replace(" ", "").lower()
            canonical_ratio = self._normalized_ratio_map.get(normalized_ratio)
            if canonical_ratio is None:
                allowed_display = ", ".join(self._allowed_aspect_ratios)
                issues.append(
                    f"attributes.aspect_ratio '{aspect_ratio_raw}' is not permitted; expected one of: {allowed_display}"
                )
            else:
                attributes["aspect_ratio"] = canonical_ratio
                needs_fallback = False
        if needs_fallback and self._fallback_aspect_ratio:
            attributes["aspect_ratio"] = self._fallback_aspect_ratio
        return issues


__all__ = [
    "ALLOWED_ASPECT_RATIOS",
    "VariantModel",
    "VariantProcessor",
]
