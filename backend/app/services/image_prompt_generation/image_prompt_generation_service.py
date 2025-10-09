"""Service for generating structured image prompts from book scenes."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence
from uuid import UUID

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.langchain import gemini_api
from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CHEATSHEET_PATH = (
    "backend/app/services/image_prompt_generation/dalle3_sci_fi_prompting_cheatsheet.md"
)


@dataclass(slots=True)
class ImagePromptGenerationConfig:
    """Runtime configuration for image prompt generation."""

    model_vendor: str = "google"
    model_name: str = "gemini-2.5-pro"
    prompt_version: str = "image-prompts-v1"
    variants_count: int = 4
    temperature: float = 0.4
    max_output_tokens: int | None = 8192
    context_before: int = 3
    context_after: int = 1
    include_cheatsheet_path: str = DEFAULT_CHEATSHEET_PATH
    dry_run: bool = False
    allow_overwrite: bool = False
    autocommit: bool = True
    retry_attempts: int = 2
    retry_backoff_seconds: float = 2.0
    fail_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def copy_with(self, **overrides: Any) -> ImagePromptGenerationConfig:
        data = {
            "model_vendor": self.model_vendor,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "variants_count": self.variants_count,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "include_cheatsheet_path": self.include_cheatsheet_path,
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
            elif value is not None:
                normalized_overrides[key] = value
            elif key in {"max_output_tokens"}:
                normalized_overrides[key] = None
        data.update(normalized_overrides)
        return ImagePromptGenerationConfig(**data)


@dataclass(slots=True)
class ImagePromptPreview:
    """In-memory preview of generated image prompt variants."""

    scene_extraction_id: UUID
    variant_index: int
    title: str | None
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


class ImagePromptGenerationServiceError(RuntimeError):
    """Raised when image prompt generation fails under strict settings."""


@dataclass(slots=True)
class _ChapterContext:
    number: int
    title: str
    paragraphs: list[str]
    source_name: str


class _VariantModel(BaseModel):
    """Validate the structure returned by the LLM."""

    title: str | None = None
    prompt_text: str
    style_tags: list[str] | None = None
    attributes: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> _VariantModel:
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:  # pragma: no cover - raised with context
            raise ImagePromptGenerationServiceError(
                "LLM response did not match the required variant schema"
            ) from exc


class ImagePromptGenerationService:
    """Generate structured image prompts for scenes using Gemini."""

    _system_instruction = (
        "Respond only with strict JSON matching the requested array schema. "
        "Do not include commentary, markdown fences, or trailing text."
    )

    def __init__(
        self,
        session: Session,
        config: ImagePromptGenerationConfig | None = None,
    ) -> None:
        self._session = session
        self._config = config or ImagePromptGenerationConfig()
        self._scene_repo = SceneExtractionRepository(session)
        self._prompt_repo = ImagePromptRepository(session)
        self._ranking_repo = SceneRankingRepository(session)
        self._cheatsheet_text: dict[str, str] = {}
        self._book_cache: MutableMapping[str, dict[int, _ChapterContext]] = {}

    def generate_for_scene(
        self,
        scene: SceneExtraction | UUID,
        *,
        prompt_version: str | None = None,
        variants_count: int | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[ImagePrompt] | list[ImagePromptPreview]:
        target_scene = self._resolve_scene(scene)
        config = self._resolve_config(
            prompt_version=prompt_version,
            variants_count=variants_count,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            overwrite=overwrite,
            dry_run=dry_run,
            metadata=metadata,
        )
        if config.variants_count <= 0:
            raise ImagePromptGenerationServiceError("variants_count must be positive")

        if not config.allow_overwrite:
            existing = self._prompt_repo.get_latest_set_for_scene(
                target_scene.id, config.model_name, config.prompt_version
            )
            if existing:
                return existing

        context_window, context_text = self._build_scene_context(target_scene, config)
        prompt = self._build_prompt(
            scene=target_scene,
            config=config,
            context_text=context_text,
            context_window=context_window,
        )
        raw_payload, llm_request_id, execution_time_ms = self._invoke_llm(
            prompt=prompt,
            config=config,
        )
        variants = self._extract_variants(raw_payload, config)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        service_payload = {
            "prompt_version": config.prompt_version,
            "model_name": config.model_name,
            "model_vendor": config.model_vendor,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "variants_count": config.variants_count,
            "prompt_hash": prompt_hash,
            "context_window": dict(context_window),
            "cheatsheet_path": config.include_cheatsheet_path,
        }
        if config.metadata:
            service_payload["run_metadata"] = dict(config.metadata)
        raw_bundle = {
            "response": raw_payload,
            "service": service_payload,
        }
        records = self._build_records(
            scene=target_scene,
            config=config,
            variants=variants,
            context_window=context_window,
            raw_payload=raw_bundle,
            llm_request_id=llm_request_id,
            execution_time_ms=execution_time_ms,
        )

        if config.dry_run:
            previews: list[ImagePromptPreview] = []
            for record in records:
                preview_payload = dict(record["raw_response"])
                preview_payload["prompt"] = prompt
                preview_payload["context_excerpt"] = context_text
                previews.append(
                    ImagePromptPreview(
                        scene_extraction_id=record["scene_extraction_id"],
                        variant_index=record["variant_index"],
                        title=record["title"],
                        prompt_text=record["prompt_text"],
                        style_tags=record["style_tags"],
                        attributes=record["attributes"],
                        prompt_version=record["prompt_version"],
                        model_name=record["model_name"],
                        model_vendor=record["model_vendor"],
                        context_window=record["context_window"],
                        raw_response=preview_payload,
                        temperature=record["temperature"],
                        max_output_tokens=record["max_output_tokens"],
                        execution_time_ms=record["execution_time_ms"],
                        llm_request_id=record["llm_request_id"],
                    )
                )
            return previews

        if config.allow_overwrite:
            deleted = self._prompt_repo.delete_for_scene(
                target_scene.id,
                prompt_version=config.prompt_version,
                model_name=config.model_name,
                commit=False,
            )
            if deleted:
                logger.info(
                    "Deleted %s existing image prompt variants for scene %s", deleted, target_scene.id
                )

        created = self._prompt_repo.bulk_create(
            records,
            commit=config.autocommit,
            refresh=True,
        )
        if not config.autocommit:
            self._session.flush()
        return created

    def generate_for_scenes(
        self,
        scenes: Sequence[SceneExtraction | UUID],
        **overrides: Any,
    ) -> list[list[ImagePrompt] | list[ImagePromptPreview] | None]:
        results: list[list[ImagePrompt] | list[ImagePromptPreview] | None] = []
        for scene in scenes:
            try:
                result = self.generate_for_scene(scene, **overrides)
            except Exception as exc:  # pragma: no cover - defensive logging
                if self._config.fail_on_error or overrides.get("fail_on_error"):
                    raise
                logger.error("Image prompt generation failed for %s: %s", scene, exc)
                results.append(None)
                continue
            results.append(result)
        return results

    def generate_for_book(
        self,
        book_slug: str,
        *,
        scene_filter: Mapping[str, Any] | None = None,
        ranked_only: bool = False,
        top_n: int | None = None,
        **overrides: Any,
    ) -> list[list[ImagePrompt] | list[ImagePromptPreview] | None]:
        scene_filter = scene_filter or {}
        chapter_number = scene_filter.get("chapter_number")
        candidate_scenes = self._scene_repo.list_for_book(
            book_slug, chapter_number=chapter_number
        )
        if ranked_only:
            candidate_scenes = self._filter_ranked_scenes(
                candidate_scenes,
                top_n=top_n,
            )
        elif top_n is not None:
            candidate_scenes = candidate_scenes[:top_n]
        if not candidate_scenes:
            return []
        return self.generate_for_scenes(candidate_scenes, **overrides)

    def _resolve_scene(self, scene: SceneExtraction | UUID) -> SceneExtraction:
        if isinstance(scene, SceneExtraction):
            return scene
        resolved = self._scene_repo.get(scene)
        if resolved is None:
            raise ImagePromptGenerationServiceError(f"Scene {scene} was not found")
        return resolved

    def _resolve_config(
        self,
        *,
        prompt_version: str | None,
        variants_count: int | None,
        temperature: float | None,
        max_output_tokens: int | None,
        overwrite: bool | None,
        dry_run: bool | None,
        metadata: Mapping[str, Any] | None,
    ) -> ImagePromptGenerationConfig:
        overrides: dict[str, Any] = {}
        if prompt_version is not None:
            overrides["prompt_version"] = prompt_version
        if variants_count is not None:
            overrides["variants_count"] = variants_count
        if temperature is not None:
            overrides["temperature"] = temperature
        if max_output_tokens is not None:
            overrides["max_output_tokens"] = max_output_tokens
        if overwrite is not None:
            overrides["allow_overwrite"] = overwrite
        if dry_run is not None:
            overrides["dry_run"] = dry_run
        if metadata is not None:
            overrides["metadata"] = dict(metadata)
        return self._config.copy_with(**overrides)

    def _build_scene_context(
        self,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
    ) -> tuple[dict[str, Any], str]:
        if scene.scene_paragraph_start is None or scene.scene_paragraph_end is None:
            base_start = max(scene.chunk_paragraph_start or 1, 1)
            base_end = max(scene.chunk_paragraph_end or base_start, base_start)
        else:
            base_start = max(int(scene.scene_paragraph_start), 1)
            base_end = max(int(scene.scene_paragraph_end), base_start)
        chapters = self._load_book_context(scene.source_book_path)
        chapter_context = chapters.get(int(scene.chapter_number))
        if chapter_context is None:
            raise ImagePromptGenerationServiceError(
                f"Chapter {scene.chapter_number} not found in {scene.source_book_path}"
            )
        before = max(config.context_before, 0)
        after = max(config.context_after, 0)
        total_paragraphs = len(chapter_context.paragraphs)
        start = max(1, base_start - before)
        end = min(total_paragraphs, base_end + after)
        formatted_lines: list[str] = []
        for index in range(start, end + 1):
            paragraph_text = chapter_context.paragraphs[index - 1]
            formatted_lines.append(f"[Paragraph {index}] {paragraph_text}")
        context_text = "\n".join(formatted_lines)
        context_window = {
            "chapter_number": scene.chapter_number,
            "chapter_title": chapter_context.title,
            "paragraph_span": [start, end],
            "paragraphs_before": before,
            "paragraphs_after": after,
        }
        return context_window, context_text

    def _build_prompt(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        context_text: str,
        context_window: Mapping[str, Any],
    ) -> str:
        cheatsheet = self._load_cheatsheet_text(config.include_cheatsheet_path)
        scene_excerpt = scene.raw.strip()
        if not scene_excerpt:
            raise ImagePromptGenerationServiceError(
                f"Scene {scene.id} is missing raw excerpt text"
            )
        refined_excerpt = (scene.refined or "").strip()
        metadata_lines = [
            f"- Book slug: {scene.book_slug}",
            f"- Chapter number: {scene.chapter_number}",
            f"- Chapter title: {scene.chapter_title}",
            f"- Scene number: {scene.scene_number}",
            f"- Location marker: {scene.location_marker}",
            f"- Paragraph span: {context_window['paragraph_span'][0]}-{context_window['paragraph_span'][1]}",
            f"- Context paragraphs: {config.context_before} before, {config.context_after} after",
        ]
        if refined_excerpt:
            metadata_lines.append(
                "- A refined excerpt is available; prefer raw text but cross-check for clarity."
            )
        metadata_block = "\n".join(metadata_lines)
        guidance = (
            "Craft distinct, cinematic prompt variants that explore different artistic lenses, compositions, "
            "lighting styles, and moods inspired by the scene. Encourage variety across variants (camera angle, focus, palette, atmosphere)."
        )
        output_schema = json.dumps(
            {
                "title": "string",
                "prompt_text": "string",
                "style_tags": ["string"],
                "attributes": {
                    "camera": "string",
                    "lens": "string",
                    "composition": "string",
                    "lighting": "string",
                    "palette": "string",
                    "aspect_ratio": "string",
                    "references": ["string"],
                },
            },
            indent=2,
        )
        prompt_lines = [
            "You are an elite prompt engineer who converts novel scenes into world-class AI image prompts.",
            f"Your goal is to produce exactly {config.variants_count} distinct prompt variants suitable for a model like DALLE3 or Midjourney.",
            "",
            "## Scene Metadata",
            metadata_block,
            "",
            "## Scene Excerpt (verbatim)",
            scene_excerpt,
        ]
        if refined_excerpt:
            prompt_lines.extend(
                [
                    "",
                    "## Refined Excerpt (for reference)",
                    refined_excerpt,
                ]
            )
        prompt = "\n".join(prompt_lines)
        prompt += (
            "\n\n## Surrounding Context Paragraphs\n"
            f"{context_text}\n\n"
            "## Sci-Fi Prompting Cheat Sheet\n"
            f"{cheatsheet}\n\n"
            "## Creative Guidance\n"
            f"{guidance}\n\n"
            "## Output Requirements\n"
            f"- Return ONLY strict JSON (no markdown) representing an array of {config.variants_count} objects.\n"
            "- Each array element must contain the keys: title, prompt_text, style_tags, attributes.\n"
            "- title can be null; prompt_text must be richly descriptive and self-contained.\n"
            "- style_tags must be a list of short descriptors (2-5 entries).\n"
            "- attributes must detail composition, camera, lens, lighting, palette, aspect_ratio, and references (list).\n"
            "- Ensure each variant explores a different angle, subject emphasis, or aesthetic.\n"
            "- Do not include notes, warnings, or additional keys.\n"
            f"- The expected object shape is similar to: {output_schema}.\n"
            "- Never include copyrighted text beyond the provided excerpts."
        )
        return prompt


    def _invoke_llm(
        self,
        *,
        prompt: str,
        config: ImagePromptGenerationConfig,
    ) -> tuple[Any, str | None, int]:
        attempts = max(config.retry_attempts, 0) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            start_time = time.perf_counter()
            try:
                response = gemini_api.json_output(
                    prompt=prompt,
                    system_instruction=self._system_instruction,
                    model=config.model_name,
                    temperature=config.temperature,
                    max_tokens=config.max_output_tokens,
                )
                execution_time_ms = int((time.perf_counter() - start_time) * 1000)
                llm_request_id = None
                if isinstance(response, dict):
                    maybe_id = response.get("request_id") or response.get("id")
                    if isinstance(maybe_id, str):
                        llm_request_id = maybe_id
                return response, llm_request_id, execution_time_ms
            except Exception as exc:  # pragma: no cover - retry path
                last_error = exc
                logger.warning(
                    "Gemini prompt generation failed (attempt %s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt >= attempts:
                    break
                time.sleep(max(config.retry_backoff_seconds, 0))
        assert last_error is not None
        if config.fail_on_error:
            raise ImagePromptGenerationServiceError(
                f"Gemini prompt generation failed: {last_error}"
            ) from last_error
        raise ImagePromptGenerationServiceError(
            "Gemini prompt generation failed after retries"
        ) from last_error

    def _extract_variants(
        self,
        payload: Any,
        config: ImagePromptGenerationConfig,
    ) -> list[_VariantModel]:
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
            variants.append(_VariantModel.from_payload(item))
        if len(variants) != config.variants_count:
            raise ImagePromptGenerationServiceError(
                f"Expected {config.variants_count} variants, received {len(variants)}"
            )
        return variants

    def _build_records(
        self,
        *,
        scene: SceneExtraction,
        config: ImagePromptGenerationConfig,
        variants: Sequence[_VariantModel],
        context_window: Mapping[str, Any],
        raw_payload: Mapping[str, Any],
        llm_request_id: str | None,
        execution_time_ms: int,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, variant in enumerate(variants):
            style_tags = (
                list(variant.style_tags) if variant.style_tags else None
            )
            attributes = dict(variant.attributes)
            records.append(
                {
                    "scene_extraction_id": scene.id,
                    "model_vendor": config.model_vendor,
                    "model_name": config.model_name,
                    "prompt_version": config.prompt_version,
                    "variant_index": index,
                    "title": variant.title.strip() if isinstance(variant.title, str) else None,
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

    def _load_cheatsheet_text(self, path_str: str) -> str:
        if path_str in self._cheatsheet_text:
            return self._cheatsheet_text[path_str]
        path = Path(path_str)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not path.exists():
            raise ImagePromptGenerationServiceError(
                f"Cheat sheet file not found: {path_str}"
            )
        text = path.read_text(encoding="utf-8")
        self._cheatsheet_text[path_str] = text.strip()
        return self._cheatsheet_text[path_str]

    def _load_book_context(
        self,
        source_book_path: str,
    ) -> dict[int, _ChapterContext]:
        if source_book_path in self._book_cache:
            return self._book_cache[source_book_path]
        path = Path(source_book_path)
        if not path.is_absolute():
            path = (_PROJECT_ROOT / path).resolve()
        if not path.exists():
            raise ImagePromptGenerationServiceError(
                f"Source EPUB not found: {source_book_path}"
            )
        book = epub.read_epub(str(path))
        chapters: dict[int, _ChapterContext] = {}
        chapter_number = 1
        for spine_entry in book.spine:
            item_id = spine_entry[0]
            item = book.get_item_with_id(item_id)
            if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            name = (item.get_name() or "").lower()
            if any(skip in name for skip in ("nav", "cover", "titlepage", "toc")):
                continue
            html = item.get_content().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = self._extract_paragraphs(soup)
            if not paragraphs:
                continue
            title = self._extract_title(soup) or f"Chapter {chapter_number}"
            chapters[chapter_number] = _ChapterContext(
                number=chapter_number,
                title=title,
                paragraphs=paragraphs,
                source_name=item.get_name() or f"chapter_{chapter_number}",
            )
            chapter_number += 1
        if not chapters:
            raise ImagePromptGenerationServiceError(
                f"No chapters extracted from EPUB: {source_book_path}"
            )
        self._book_cache[source_book_path] = chapters
        return chapters

    def _extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        raw_text = soup.get_text("\n")
        lines = [line.strip() for line in raw_text.splitlines()]
        paragraphs: list[str] = []
        buffer: list[str] = []
        for line in lines:
            if not line:
                if buffer:
                    paragraphs.append(self._normalize_whitespace(" ".join(buffer)))
                    buffer = []
                continue
            buffer.append(line)
        if buffer:
            paragraphs.append(self._normalize_whitespace(" ".join(buffer)))
        return [p for p in paragraphs if p]

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        for selector in ("h1", "h2", "h3", "title"):
            node = soup.find(selector)
            if node:
                title = node.get_text(strip=True)
                if title:
                    return self._normalize_whitespace(title)
        return None

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return " ".join(text.split())

    def _filter_ranked_scenes(
        self,
        scenes: Sequence[SceneExtraction],
        *,
        top_n: int | None,
    ) -> list[SceneExtraction]:
        if not scenes:
            return []
        book_slug = scenes[0].book_slug
        if top_n is not None and top_n > 0:
            rankings = self._ranking_repo.list_top_rankings_for_book(
                book_slug=book_slug,
                limit=top_n,
                include_scene=True,
            )
            ranked_scenes: list[SceneExtraction] = []
            seen_ids: set[UUID] = set()
            for ranking in rankings:
                scene = ranking.scene_extraction
                if scene is None:
                    scene = self._scene_repo.get(ranking.scene_extraction_id)
                if scene is None:
                    continue
                if scene.id in seen_ids:
                    continue
                ranked_scenes.append(scene)
                seen_ids.add(scene.id)
                if len(ranked_scenes) >= top_n:
                    break
            if ranked_scenes:
                return ranked_scenes
        filtered: list[SceneExtraction] = []
        for scene in scenes:
            ranking = self._ranking_repo.get_latest_for_scene(scene.id)
            if ranking is not None:
                filtered.append(scene)
        if top_n is not None and top_n > 0:
            filtered = filtered[:top_n]
        return filtered


__all__ = [
    "ImagePromptGenerationConfig",
    "ImagePromptGenerationService",
    "ImagePromptGenerationServiceError",
    "ImagePromptPreview",
]
