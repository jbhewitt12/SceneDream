"""Service for ranking extracted scenes with LLM support."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlmodel import Session

from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.langchain import gemini_api
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


SCORING_CRITERIA: tuple[str, ...] = (
    "originality",
    "visual_style_potential",
    "image_prompt_fit",
    "video_prompt_fit",
    "emotional_intensity",
    "worldbuilding_depth",
    "character_focus",
    "action_dynamism",
    "clarity_for_prompting",
)

DEFAULT_WEIGHT_CONFIG: dict[str, float] = {
    "originality": 1.0,
    "visual_style_potential": 1.1,
    "image_prompt_fit": 1.2,
    "video_prompt_fit": 0.9,
    "emotional_intensity": 0.9,
    "worldbuilding_depth": 1.0,
    "character_focus": 0.9,
    "action_dynamism": 0.8,
    "clarity_for_prompting": 1.2,
}

DEFAULT_SYSTEM_INSTRUCTION = (
    "You score scenes from novels for their suitability as generative art prompts. "
    "Respond with strictly valid JSON that matches the requested schema. "
    "All numeric scores must be decimal numbers between 1.0 and 10.0 with one decimal place."
)

CRITERIA_GUIDANCE = (
    "originality: uniqueness of setting, tone, or scenario versus genre tropes.\n"
    "visual_style_potential: richness of color, texture, and atmosphere cues.\n"
    "image_prompt_fit: how well the moment can become a single still image.\n"
    "video_prompt_fit: motion or progression that would excel in short video.\n"
    "emotional_intensity: clarity and strength of emotional beats.\n"
    "worldbuilding_depth: distinct environmental or lore details to reference.\n"
    "character_focus: definition of characters, costumes, or poses.\n"
    "action_dynamism: kinetic energy or choreography to stage.\n"
    "clarity_for_prompting: absence of contradictions or confusing abstractions."
)

_PREVIOUS_RANKING_LIMIT = 3


class _RankingScores(BaseModel):
    model_config = ConfigDict(extra="ignore")

    originality: float = Field(..., ge=1.0, le=10.0)
    visual_style_potential: float = Field(..., ge=1.0, le=10.0)
    image_prompt_fit: float = Field(..., ge=1.0, le=10.0)
    video_prompt_fit: float = Field(..., ge=1.0, le=10.0)
    emotional_intensity: float = Field(..., ge=1.0, le=10.0)
    worldbuilding_depth: float = Field(..., ge=1.0, le=10.0)
    character_focus: float = Field(..., ge=1.0, le=10.0)
    action_dynamism: float = Field(..., ge=1.0, le=10.0)
    clarity_for_prompting: float = Field(..., ge=1.0, le=10.0)

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_score(cls, value: Any) -> float:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("empty score")
            match = re.search(r"\d+(?:\.\d+)?", stripped)
            if match:
                return float(match.group())
        raise ValueError(f"Unhandled score value: {value!r}")


class _RankingResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scores: _RankingScores
    overall_priority: float = Field(..., ge=1.0, le=10.0)
    justification: str = Field(..., min_length=1)
    warnings: list[str] | None = None
    character_tags: list[str] | None = None
    diagnostics: dict[str, Any] | None = None

    @field_validator("justification", mode="after")
    @classmethod
    def _trim_justification(cls, value: str) -> str:
        return value.strip()

    @field_validator("warnings", "character_tags", mode="before")
    @classmethod
    def _coerce_list(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list | tuple | set):
            items = list(value)
        else:
            return None
        normalized = [str(item).strip() for item in items if str(item).strip()]
        return normalized or None


@dataclass(slots=True)
class SceneRankingConfig:
    model_name: str = "gemini-2.5-flash"
    model_vendor: str = "google"
    prompt_version: str = "scene-ranking-v1"
    temperature: float = 0.1
    max_output_tokens: int | None = 2048
    system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION
    weight_config: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHT_CONFIG)
    )
    retry_attempts: int = 2
    retry_backoff_seconds: float = 2.0
    autocommit: bool = True
    skip_discarded_scenes: bool = True
    allow_overwrite: bool = False
    include_previous_rankings: bool = True
    dry_run: bool = False
    fail_on_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def copy_with(self, **overrides: Any) -> SceneRankingConfig:
        weight_override = overrides.pop("weight_config", None)
        metadata_override = overrides.pop("metadata", None)
        data: dict[str, Any] = {
            "model_name": self.model_name,
            "model_vendor": self.model_vendor,
            "prompt_version": self.prompt_version,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "system_instruction": self.system_instruction,
            "weight_config": dict(self.weight_config),
            "retry_attempts": self.retry_attempts,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "autocommit": self.autocommit,
            "skip_discarded_scenes": self.skip_discarded_scenes,
            "allow_overwrite": self.allow_overwrite,
            "include_previous_rankings": self.include_previous_rankings,
            "dry_run": self.dry_run,
            "fail_on_error": self.fail_on_error,
            "metadata": dict(self.metadata),
        }
        if weight_override is not None:
            data["weight_config"] = dict(weight_override)
        if metadata_override is not None:
            data["metadata"] = dict(metadata_override)
        data.update(overrides)
        return SceneRankingConfig(**data)


@dataclass(slots=True)
class SceneRankingPreview:
    scene_extraction_id: UUID
    scores: dict[str, float]
    overall_priority: float
    justification: str
    warnings: list[str] | None
    character_tags: list[str] | None
    prompt_version: str
    model_name: str
    weight_config: dict[str, float]
    weight_config_hash: str
    execution_time_ms: int
    raw_response: dict[str, Any]


class SceneRankingServiceError(RuntimeError):
    """Raised when ranking fails and the caller requested strict failure."""


class SceneRankingService:
    """Coordinates scene ranking requests and persistence."""

    def __init__(
        self, session: Session, *, config: SceneRankingConfig | None = None
    ) -> None:
        self._session = session
        self._config = config.copy_with() if config else SceneRankingConfig()
        self._scene_repo = SceneExtractionRepository(session)
        self._ranking_repo = SceneRankingRepository(session)

    @property
    def config(self) -> SceneRankingConfig:
        return self._config

    def rank_scene(
        self,
        scene: SceneExtraction | UUID,
        *,
        prompt_version: str | None = None,
        weight_config: Mapping[str, float] | None = None,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SceneRanking | SceneRankingPreview | None:
        overrides: dict[str, Any] = {}
        if prompt_version is not None:
            overrides["prompt_version"] = prompt_version
        if weight_config is not None:
            overrides["weight_config"] = dict(weight_config)
        if overwrite is not None:
            overrides["allow_overwrite"] = bool(overwrite)
        if dry_run is not None:
            overrides["dry_run"] = bool(dry_run)
            if dry_run:
                overrides.setdefault("autocommit", False)
        if metadata is not None:
            overrides["metadata"] = dict(metadata)
        config = self._config.copy_with(**overrides)
        target_scene = self._resolve_scene(scene)
        if (
            config.skip_discarded_scenes
            and target_scene.refinement_decision
            and target_scene.refinement_decision.strip().lower() == "discard"
        ):
            logger.debug(
                "Skipping scene %s because refinement marked it as discard.",
                target_scene.id,
            )
            return None
        weight_cfg = self._normalize_weight_config(config.weight_config)
        weight_hash = self._compute_weight_hash(weight_cfg)
        if not config.allow_overwrite:
            existing = self._ranking_repo.get_unique_run(
                scene_extraction_id=target_scene.id,
                model_name=config.model_name,
                prompt_version=config.prompt_version,
                weight_config_hash=weight_hash,
            )
            if existing is not None:
                logger.debug(
                    "Found existing ranking for scene %s (model=%s, prompt=%s, weight=%s)",
                    target_scene.id,
                    config.model_name,
                    config.prompt_version,
                    weight_hash,
                )
                return existing
        previous_rankings: Sequence[SceneRanking] = ()
        if config.include_previous_rankings:
            previous_rankings = self._ranking_repo.list_for_scene(
                target_scene.id,
                limit=_PREVIOUS_RANKING_LIMIT,
            )
        prompt = self._build_prompt(
            scene=target_scene,
            prompt_version=config.prompt_version,
            weight_config=weight_cfg,
            previous_rankings=previous_rankings,
        )
        start_time = time.perf_counter()
        try:
            raw_response = self._invoke_llm(prompt=prompt, config=config)
        except Exception as exc:  # pragma: no cover - depends on external API
            logger.error("LLM call failed for scene %s: %s", target_scene.id, exc)
            if config.fail_on_error:
                raise SceneRankingServiceError(str(exc)) from exc
            return None
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)
        try:
            parsed = _RankingResponse.model_validate(raw_response)
        except ValidationError as exc:
            logger.error(
                "Scene ranking validation failed for %s: %s", target_scene.id, exc
            )
            if config.fail_on_error:
                raise SceneRankingServiceError("Invalid response structure") from exc
            return None
        scores = self._normalize_scores(parsed.scores)
        overall_priority = self._calculate_overall_priority(scores, weight_cfg)
        warnings = list(parsed.warnings) if parsed.warnings else None
        character_tags = list(parsed.character_tags) if parsed.character_tags else None
        llm_overall = round(float(parsed.overall_priority), 1)
        metadata_block = {
            "prompt_version": config.prompt_version,
            "model_name": config.model_name,
            "model_vendor": config.model_vendor,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
            "execution_time_ms": execution_time_ms,
            "weights": weight_cfg,
            "prompt": prompt,
            "llm_overall_priority": llm_overall,
            "previous_rankings": self._serialize_previous_rankings(previous_rankings),
        }
        if config.metadata:
            metadata_block["run_metadata"] = dict(config.metadata)
        llm_request_id = None
        diagnostics = (
            raw_response.get("diagnostics") if isinstance(raw_response, dict) else None
        )
        if isinstance(diagnostics, dict):
            candidate = diagnostics.get("request_id") or diagnostics.get("id")
            if candidate is not None:
                llm_request_id = str(candidate)
        raw_payload = {
            "response": raw_response,
            "service": metadata_block,
        }
        if config.dry_run:
            return SceneRankingPreview(
                scene_extraction_id=target_scene.id,
                scores=scores,
                overall_priority=overall_priority,
                justification=parsed.justification,
                warnings=warnings,
                character_tags=character_tags,
                prompt_version=config.prompt_version,
                model_name=config.model_name,
                weight_config=weight_cfg,
                weight_config_hash=weight_hash,
                execution_time_ms=execution_time_ms,
                raw_response=raw_payload,
            )
        ranking = self._ranking_repo.create(
            data={
                "scene_extraction_id": target_scene.id,
                "model_vendor": config.model_vendor,
                "model_name": config.model_name,
                "prompt_version": config.prompt_version,
                "justification": parsed.justification,
                "scores": scores,
                "overall_priority": overall_priority,
                "weight_config": weight_cfg,
                "weight_config_hash": weight_hash,
                "warnings": warnings,
                "character_tags": character_tags,
                "raw_response": raw_payload,
                "execution_time_ms": execution_time_ms,
                "temperature": config.temperature,
                "llm_request_id": llm_request_id,
            },
            commit=config.autocommit,
            refresh=True,
        )
        if not config.autocommit:
            self._session.flush()
        return ranking

    def rank_scenes(
        self,
        scenes: Sequence[SceneExtraction | UUID],
        *,
        prompt_version: str | None = None,
        weight_config: Mapping[str, float] | None = None,
        overwrite: bool | None = None,
        dry_run: bool | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[SceneRanking | SceneRankingPreview | None]:
        results: list[SceneRanking | SceneRankingPreview | None] = []
        for scene in scenes:
            result = self.rank_scene(
                scene,
                prompt_version=prompt_version,
                weight_config=weight_config,
                overwrite=overwrite,
                dry_run=dry_run,
                metadata=metadata,
            )
            results.append(result)
        return results

    def _resolve_scene(self, scene: SceneExtraction | UUID) -> SceneExtraction:
        if isinstance(scene, SceneExtraction):
            return scene
        resolved = self._scene_repo.get(scene)
        if resolved is None:
            raise SceneRankingServiceError(f"Scene {scene} was not found")
        return resolved

    def _normalize_weight_config(
        self, weight_config: Mapping[str, float]
    ) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key in SCORING_CRITERIA:
            raw_value = weight_config.get(key, DEFAULT_WEIGHT_CONFIG.get(key, 1.0))
            try:
                numeric = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise SceneRankingServiceError(
                    f"Invalid weight for {key}: {raw_value!r}"
                ) from exc
            if numeric < 0:
                raise SceneRankingServiceError(
                    f"Weights must be non-negative (got {key}={numeric})"
                )
            normalized[key] = numeric
        total_weight = sum(normalized.values())
        if total_weight <= 0:
            raise SceneRankingServiceError(
                "Weight configuration must include at least one positive value"
            )
        return normalized

    def _compute_weight_hash(self, weight_config: Mapping[str, float]) -> str:
        ordered = {key: weight_config[key] for key in sorted(weight_config)}
        payload = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _calculate_overall_priority(
        self,
        scores: Mapping[str, float],
        weight_config: Mapping[str, float],
    ) -> float:
        numerator = 0.0
        denominator = 0.0
        for key in SCORING_CRITERIA:
            score_value = float(scores[key])
            weight_value = float(weight_config.get(key, 0.0))
            numerator += score_value * weight_value
            denominator += weight_value
        if denominator <= 0:
            return round(
                sum(float(scores[key]) for key in SCORING_CRITERIA)
                / len(SCORING_CRITERIA),
                1,
            )
        return round(numerator / denominator, 1)

    def _normalize_scores(self, payload: _RankingScores) -> dict[str, float]:
        raw_scores = payload.model_dump()
        normalized: dict[str, float] = {}
        for key in SCORING_CRITERIA:
            value = raw_scores.get(key)
            if value is None:
                raise SceneRankingServiceError(f"Missing score for {key}")
            normalized[key] = round(float(value), 1)
        return normalized

    def _format_previous_rankings(
        self,
        previous_rankings: Sequence[SceneRanking],
    ) -> str:
        if not previous_rankings:
            return ""
        lines: list[str] = []
        for ranking in previous_rankings[:_PREVIOUS_RANKING_LIMIT]:
            created = (
                ranking.created_at.isoformat()
                if isinstance(ranking.created_at, datetime)
                else "unknown"
            )
            weight_hash = ranking.weight_config_hash[:8]
            top_scores = self._top_score_summary(ranking.scores)
            lines.append(
                f"- {created} | overall {ranking.overall_priority:.1f} | model {ranking.model_name} | prompt {ranking.prompt_version} | weights {weight_hash} | top {top_scores}"
            )
        return "\n".join(lines)

    def _serialize_previous_rankings(
        self,
        previous_rankings: Sequence[SceneRanking],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for ranking in previous_rankings:
            serialized.append(
                {
                    "id": str(ranking.id),
                    "created_at": ranking.created_at.isoformat()
                    if isinstance(ranking.created_at, datetime)
                    else None,
                    "model_name": ranking.model_name,
                    "prompt_version": ranking.prompt_version,
                    "overall_priority": ranking.overall_priority,
                    "weight_config_hash": ranking.weight_config_hash,
                }
            )
        return serialized

    def _top_score_summary(self, scores: Mapping[str, Any]) -> str:
        if not scores:
            return "none"
        try:
            ordered = sorted(
                ((name, float(value)) for name, value in scores.items()),
                key=lambda item: item[1],
                reverse=True,
            )
        except (TypeError, ValueError):
            return "unavailable"
        top = ordered[:2]
        return ", ".join(f"{name}:{value:.1f}" for name, value in top)

    def _build_prompt(
        self,
        *,
        scene: SceneExtraction,
        prompt_version: str,
        weight_config: Mapping[str, float],
        previous_rankings: Sequence[SceneRanking],
    ) -> str:
        excerpt = (scene.refined or scene.raw or "").strip()
        if not excerpt:
            raise SceneRankingServiceError(
                f"Scene {scene.id} does not have content to rank"
            )
        metadata_lines = [
            f"book_slug: {scene.book_slug}",
            f"chapter_number: {scene.chapter_number}",
            f"chapter_title: {scene.chapter_title}",
            f"scene_number: {scene.scene_number}",
            f"location_marker: {scene.location_marker}",
        ]
        if scene.refinement_decision:
            metadata_lines.append(f"refinement_decision: {scene.refinement_decision}")
        if scene.refinement_rationale:
            metadata_lines.append(f"refinement_rationale: {scene.refinement_rationale}")
        if scene.extraction_model:
            metadata_lines.append(f"extraction_model: {scene.extraction_model}")
        if scene.refinement_model:
            metadata_lines.append(f"refinement_model: {scene.refinement_model}")
        if (
            scene.scene_paragraph_start is not None
            and scene.scene_paragraph_end is not None
        ):
            metadata_lines.append(
                f"scene_paragraph_span: {scene.scene_paragraph_start}-{scene.scene_paragraph_end}"
            )
        if (
            scene.chunk_paragraph_start is not None
            and scene.chunk_paragraph_end is not None
        ):
            metadata_lines.append(
                f"chunk_paragraph_span: {scene.chunk_paragraph_start}-{scene.chunk_paragraph_end}"
            )
        weight_lines = [
            f"- {key}: weight {weight_config[key]:.2f}" for key in SCORING_CRITERIA
        ]
        previous_section = self._format_previous_rankings(previous_rankings)
        prompt_parts = [
            f"You are using prompt template version {prompt_version}. Score the scene using the criteria below.",
            "Provide concise reasoning and flag sensitive content when relevant.",
            "Return JSON with keys:",
            "{",
            '  "scores": { "criterion": number },',
            '  "overall_priority": number,',
            '  "justification": string,',
            '  "warnings": [string],',
            '  "character_tags": [string],',
            '  "diagnostics": { ... }',
            "}",
            "\nScoring guidance:",
            CRITERIA_GUIDANCE,
            "\nWeight heuristic (do not output, just use for reasoning):",
            "\n".join(weight_lines),
            "\nScene metadata:",
            "\n".join(metadata_lines),
            "\nScene excerpt:\n<<<\n",
            excerpt,
            "\n>>>",
        ]
        if previous_section:
            prompt_parts.extend(
                ["\nRecent previous rankings for context:", previous_section]
            )
        return "\n".join(prompt_parts)

    def _invoke_llm(self, *, prompt: str, config: SceneRankingConfig) -> dict[str, Any]:
        last_error: Exception | None = None
        attempts = max(config.retry_attempts, 0)
        for attempt in range(attempts + 1):
            try:
                return gemini_api.json_output(
                    prompt=prompt,
                    system_instruction=config.system_instruction,
                    model=config.model_name,
                    temperature=config.temperature,
                    max_tokens=config.max_output_tokens,
                )
            except Exception as exc:  # pragma: no cover - depends on external API
                last_error = exc
                logger.warning("Gemini call attempt %s failed: %s", attempt + 1, exc)
                if attempt >= attempts:
                    break
                sleep_seconds = config.retry_backoff_seconds * (attempt + 1)
                time.sleep(max(sleep_seconds, 0.0))
        assert last_error is not None
        raise last_error


__all__ = [
    "SceneRankingConfig",
    "SceneRankingPreview",
    "SceneRankingService",
    "SceneRankingServiceError",
]
