"""Generate shareable metadata (title + flavour text) for image prompts."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.repositories.image_prompt import ImagePromptRepository
from app.services.langchain import gemini_api, openai_api
from app.services.langchain.model_routing import (
    LLMProvider,
    LLMRoutingConfig,
    resolve_llm_model,
)
from models.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(slots=True)
class PromptMetadataConfig:
    """Runtime configuration for metadata generation."""

    model_vendor: LLMProvider = "google"
    model_name: str = "gemini-3-flash-preview"
    backup_model_vendor: LLMProvider = "openai"
    backup_model_name: str = "gpt-5-nano"
    temperature: float = 0.85
    retry_attempts: int = 2
    retry_backoff_seconds: float = 1.0
    fail_on_error: bool = False
    overwrite_existing: bool = False
    dry_run: bool = False


class PromptMetadataGenerationServiceError(RuntimeError):
    """Raised when metadata generation fails."""


class PromptMetadataGenerationService:
    """Generate short titles and flavour text for image prompts."""

    _system_instruction = (
        "You craft social-media-ready microcopy for AI-generated artwork. "
        "Respond only with a JSON object containing `title` and `flavour_text` keys. "
        "Titles must be 1-5 words. Flavour text must be a single sentence (8-16 words). "
        "Never reference licensed character names, book titles, author names, or direct plot details. "
        "Write flavour text like a Magic: The Gathering card—clever, intriguing, mysterious, or wry rather than literal."
    )

    def __init__(
        self,
        session: Session,
        config: PromptMetadataConfig | None = None,
    ) -> None:
        self._session = session
        self._config = config or PromptMetadataConfig()
        self._prompt_repo = ImagePromptRepository(session)

    async def generate_metadata_for_prompt(
        self,
        prompt: ImagePrompt | UUID,
        *,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
    ) -> ImagePrompt | dict[str, Any] | None:
        """
        Generate metadata for a single prompt.

        Returns the updated ImagePrompt when persisting, or a preview dict when dry_run is True.
        """
        target_prompt = self._resolve_prompt(prompt)
        effective_overwrite = (
            self._config.overwrite_existing if overwrite is None else overwrite
        )
        effective_dry_run = self._config.dry_run if dry_run is None else dry_run

        if not effective_overwrite and self._has_text(target_prompt.flavour_text):
            if effective_dry_run:
                return {
                    "prompt_id": str(target_prompt.id),
                    "title": target_prompt.title,
                    "flavour_text": target_prompt.flavour_text,
                    "skipped": True,
                }
            return target_prompt

        prompt_payload = self._build_metadata_prompt(target_prompt)
        try:
            metadata = await self._invoke_llm(
                payload=prompt_payload,
                prompt_id=target_prompt.id,
            )
        except PromptMetadataGenerationServiceError as exc:
            logger.warning(
                "Metadata generation failed for prompt %s: %s",
                target_prompt.id,
                exc,
            )
            if self._config.fail_on_error:
                raise
            return None

        clean_title = self._normalize_title(metadata.get("title"))
        clean_flavour = self._normalize_flavour_text(metadata.get("flavour_text"))
        if not clean_flavour:
            message = "Gemini response did not include flavour_text"
            if self._config.fail_on_error:
                raise PromptMetadataGenerationServiceError(message)
            logger.warning("%s for prompt %s", message, target_prompt.id)
            return None

        if effective_dry_run:
            return {
                "prompt_id": str(target_prompt.id),
                "title": clean_title or target_prompt.title,
                "flavour_text": clean_flavour,
                "skipped": False,
            }

        updated = False
        if clean_flavour:
            target_prompt.flavour_text = clean_flavour
            updated = True

        if clean_title and (
            effective_overwrite or not self._has_text(target_prompt.title)
        ):
            target_prompt.title = clean_title
            updated = True

        if updated:
            target_prompt.updated_at = datetime.now(timezone.utc)
            self._session.add(target_prompt)
            self._session.flush()

        return target_prompt

    async def generate_metadata_for_prompts(
        self,
        prompts: Sequence[ImagePrompt | UUID],
        *,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
    ) -> list[ImagePrompt | dict[str, Any] | None]:
        """Generate metadata for a batch of prompts."""
        results: list[ImagePrompt | dict[str, Any] | None] = []
        for prompt in prompts:
            result = await self.generate_metadata_for_prompt(
                prompt,
                overwrite=overwrite,
                dry_run=dry_run,
            )
            results.append(result)
        return results

    def _resolve_prompt(self, prompt: ImagePrompt | UUID) -> ImagePrompt:
        if isinstance(prompt, ImagePrompt):
            return prompt
        resolved = self._prompt_repo.get(prompt)
        if resolved is None:
            raise PromptMetadataGenerationServiceError(
                f"ImagePrompt {prompt} was not found"
            )
        return resolved

    def _build_prompt_context(self, prompt: ImagePrompt) -> dict[str, str]:
        prompt_text = self._truncate(prompt.prompt_text.strip(), limit=1200)
        style_tags = ", ".join(prompt.style_tags or []) or "unspecified"
        attributes = prompt.attributes or {}
        attribute_lines = "\n".join(
            f"- {key}: {self._stringify_value(value)}"
            for key, value in attributes.items()
        )
        if not attribute_lines:
            attribute_lines = "- None provided"
        context_window = prompt.context_window or {}
        scene_summary = context_window.get("scene_excerpt") or ""
        scene_summary = self._truncate(str(scene_summary), limit=500)
        return {
            "prompt_text": prompt_text,
            "style_tags": style_tags,
            "attribute_lines": attribute_lines,
            "scene_summary": scene_summary or "N/A",
        }

    def _build_metadata_prompt(self, prompt: ImagePrompt) -> str:
        context = self._build_prompt_context(prompt)
        template = dedent(
            """
            TASK:
            You are creating social-media-ready metadata for an AI-generated illustration.

            SOURCE PROMPT:
            {prompt_text}

            STYLE TAGS:
            {style_tags}

            KEY ATTRIBUTES:
            {attribute_lines}

            SCENE EXCERPT (internal context, do not reproduce literally):
            {scene_summary}

            REQUIREMENTS:
            1. Title must be 1-5 evocative words without punctuation except hyphens.
            2. Flavour text must be a single sentence (8-16 words) that lands as interesting, funny, or mysterious.
            3. Never mention character names, author names, or book titles. Use descriptive, archetypal language instead.
            4. Capture the mood, color, and energy implied by the prompt without copying its wording verbatim.
            5. Keep things cool, modern, and hype without sounding clickbait or cringe.
            6. Let the flavour text read like an MTG-style whisper, sly prophecy, or wry aside rather than a literal caption.
            7. Never use the word "gilded" in the title or flavour text.

            Respond ONLY with JSON: {{"title": "<string>", "flavour_text": "<string>"}}
            """
        ).strip()
        return template.format(**context)

    def _build_variants_prompt(
        self,
        prompt: ImagePrompt,
        *,
        variants_count: int,
    ) -> str:
        context = self._build_prompt_context(prompt)
        template = dedent(
            """
            TASK:
            You are curating multiple social-media-ready metadata options for an AI-generated illustration.

            SOURCE PROMPT:
            {prompt_text}

            STYLE TAGS:
            {style_tags}

            KEY ATTRIBUTES:
            {attribute_lines}

            SCENE EXCERPT (internal context, do not reproduce literally):
            {scene_summary}

            REQUIREMENTS:
            1. Produce {variants_count} distinct options that feel meaningfully different in tone or creative angle.
            2. Every option must have a title of 1-5 evocative words (hyphens allowed) and a flavour text sentence of 8-16 words.
            3. Never mention character names, author names, or book titles. Use descriptive, archetypal language instead.
            4. Capture the vibe, palette, and energy implied by the prompt without copying its wording verbatim.
            5. Keep things modern and hype without sounding like clickbait.
            6. Let the flavour text read like an MTG-style whisper, sly prophecy, or wry aside rather than a literal caption.
            7. Never use the word "gilded" in any title or flavour text.

            Respond ONLY with JSON in this exact shape:
            {{
              "variants": [
                {{"title": "<string>", "flavour_text": "<string>"}},
                ...
              ]
            }}
            """
        ).strip()
        return template.format(**context, variants_count=variants_count)

    async def generate_metadata_variants(
        self,
        prompt: ImagePrompt | UUID,
        *,
        variants_count: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate multiple metadata variants for preview without persisting them."""
        target_prompt = self._resolve_prompt(prompt)
        bounded_count = max(1, min(variants_count, 10))
        payload = self._build_variants_prompt(
            target_prompt,
            variants_count=bounded_count,
        )
        try:
            response = await self._invoke_llm(
                payload=payload,
                prompt_id=target_prompt.id,
            )
        except PromptMetadataGenerationServiceError as exc:
            logger.warning(
                "Metadata variant generation failed for prompt %s: %s",
                target_prompt.id,
                exc,
            )
            if self._config.fail_on_error:
                raise
            return []

        raw_variants = (
            response.get("variants") if isinstance(response, Mapping) else None
        )
        if not isinstance(raw_variants, Sequence):
            logger.warning(
                "Gemini variants payload missing or invalid for prompt %s: %r",
                target_prompt.id,
                response,
            )
            return []

        cleaned_variants: list[dict[str, Any]] = []
        for variant in raw_variants:
            if not isinstance(variant, Mapping):
                continue
            clean_title = self._normalize_title(variant.get("title"))
            clean_flavour = self._normalize_flavour_text(variant.get("flavour_text"))
            if not clean_flavour:
                continue
            cleaned_variants.append(
                {
                    "title": clean_title,
                    "flavour_text": clean_flavour,
                }
            )

        if not cleaned_variants:
            logger.warning(
                "No usable metadata variants produced for prompt %s",
                target_prompt.id,
            )
        return cleaned_variants

    async def _invoke_llm(
        self,
        *,
        payload: str,
        prompt_id: UUID,
    ) -> Mapping[str, Any]:
        resolved = resolve_llm_model(
            LLMRoutingConfig(
                default_vendor=self._config.model_vendor,
                default_model=self._config.model_name,
                backup_vendor=self._config.backup_model_vendor,
                backup_model=self._config.backup_model_name,
            ),
            context="PromptMetadataGenerationService.generate",
        )
        attempts = max(self._config.retry_attempts, 0) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            start_time = time.perf_counter()
            try:
                if resolved.vendor == "google":
                    response = await gemini_api.json_output(
                        prompt=payload,
                        system_instruction=self._system_instruction,
                        model=resolved.model,
                        temperature=self._config.temperature,
                    )
                else:
                    response = await openai_api.json_output(
                        prompt=payload,
                        system_instruction=self._system_instruction,
                        model=resolved.model,
                        temperature=self._config.temperature,
                    )
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                logger.debug(
                    "Metadata LLM call succeeded for prompt %s in %sms (vendor=%s, model=%s)",
                    prompt_id,
                    elapsed_ms,
                    resolved.vendor,
                    resolved.model,
                )
                return self._coerce_metadata_payload(response)
            except Exception as exc:  # pragma: no cover - retry path
                last_error = exc
                logger.warning(
                    "Metadata call failed for prompt %s (attempt %s/%s, vendor=%s, model=%s): %s",
                    prompt_id,
                    attempt,
                    attempts,
                    resolved.vendor,
                    resolved.model,
                    exc,
                )
                if attempt >= attempts:
                    break
                await asyncio.sleep(max(self._config.retry_backoff_seconds, 0))
        assert last_error is not None
        raise PromptMetadataGenerationServiceError(
            f"Metadata generation failed after {attempts} attempts"
        ) from last_error

    def _coerce_metadata_payload(self, payload: Any) -> Mapping[str, Any]:
        if isinstance(payload, Mapping):
            return payload
        raise PromptMetadataGenerationServiceError(
            "Metadata response must be a JSON object"
        )

    @staticmethod
    def _truncate(value: str, *, limit: int) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        truncated = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-")
        return f"{truncated}..."

    @staticmethod
    def _stringify_value(value: Any) -> str:
        if isinstance(value, list | tuple):
            return ", ".join(
                PromptMetadataGenerationService._stringify_value(v) for v in value
            )
        if isinstance(value, Mapping):
            parts = [
                f"{k}: {PromptMetadataGenerationService._stringify_value(v)}"
                for k, v in value.items()
            ]
            return "{" + ", ".join(parts) + "}"
        return str(value)

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value and value.strip())

    @staticmethod
    def _normalize_title(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            return None
        words = cleaned.split()
        if len(words) > 5:
            cleaned = " ".join(words[:5])
        return cleaned

    @staticmethod
    def _normalize_flavour_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            return None
        sentences = cleaned.split(". ")
        if len(sentences) > 2:
            cleaned = ". ".join(sentences[:2]).rstrip(".") + "."
        if len(cleaned) > 400:
            cleaned = cleaned[:400].rsplit(" ", 1)[0].rstrip(",.;:-") + "..."
        return cleaned
