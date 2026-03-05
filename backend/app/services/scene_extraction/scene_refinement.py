from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from textwrap import dedent
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.services.langchain import gemini_api, openai_api
from app.services.langchain.model_routing import (
    LLMProvider,
    LLMRoutingConfig,
    ResolvedLLMModel,
    resolve_llm_model,
)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .scene_extraction import Chapter, RawScene


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _RefinementScenePayload(BaseModel):
    scene_id: int = Field(..., description="Original scene identifier.")
    decision: str = Field(..., description="Either 'keep' or 'discard'.")
    rationale: str = Field(..., description="Brief explanation for the decision.")


class _RefinementResponse(BaseModel):
    scenes: list[_RefinementScenePayload]


REFINEMENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["keep", "discard"]},
                    "rationale": {"type": "string"},
                },
                "required": ["scene_id", "decision", "rationale"],
            },
        }
    },
    "required": ["scenes"],
}


@dataclass
class RefinedScene:
    scene_id: int
    decision: str
    rationale: str


class SceneRefinementError(RuntimeError):
    """Raised when the refinement client cannot execute successfully."""


class SceneRefiner:
    """Handles scene refinement with provider-aware fallback routing."""

    def __init__(
        self,
        *,
        default_vendor: LLMProvider,
        model: str,
        backup_vendor: LLMProvider,
        backup_model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> None:
        self._routing = LLMRoutingConfig(
            default_vendor=default_vendor,
            default_model=model,
            backup_vendor=backup_vendor,
            backup_model=backup_model,
        )
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._last_model: ResolvedLLMModel | None = None

    @property
    def last_model_name(self) -> str | None:
        return self._last_model.model if self._last_model else None

    @property
    def last_model_vendor(self) -> LLMProvider | None:
        return self._last_model.vendor if self._last_model else None

    def refine(
        self,
        chapter: Chapter,
        scenes: list[RawScene],
        *,
        fail_on_error: bool = False,
    ) -> dict[int, RefinedScene]:
        if not scenes:
            return {}
        prompt = self._build_refinement_prompt(chapter, scenes)
        try:
            resolved = resolve_llm_model(
                self._routing,
                context="SceneRefiner.refine",
            )
            self._last_model = resolved
            if resolved.vendor == "google":
                payload = asyncio.run(
                    gemini_api.structured_output(
                        prompt=prompt,
                        schema=_RefinementResponse,
                        method="json_mode",
                        model=resolved.model,
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    )
                )
            else:
                payload = asyncio.run(
                    openai_api.structured_output(
                        prompt=prompt,
                        schema=_RefinementResponse,
                        method="json_mode",
                        model=resolved.model,
                        temperature=self._temperature,
                        max_tokens=self._max_tokens,
                    )
                )
        except Exception as exc:
            chapter_number = getattr(chapter, "number", "?")
            logger.error("Refinement failed for chapter %s: %s", chapter_number, exc)
            if fail_on_error:
                raise SceneRefinementError(str(exc)) from exc
            return {}
        entries = payload.scenes if hasattr(payload, "scenes") else None
        refinements: dict[int, RefinedScene] = {}
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, _RefinementScenePayload):
                    scene_id = item.scene_id
                    decision_raw = item.decision.strip().lower()
                    rationale = item.rationale.strip()
                elif isinstance(item, dict):
                    scene_id = item.get("scene_id")
                    decision_raw = str(item.get("decision", "keep")).strip().lower()
                    rationale = str(item.get("rationale", "")).strip()
                else:
                    continue
                if scene_id is None:
                    continue
                try:
                    numeric_id = int(scene_id)
                except (TypeError, ValueError):
                    continue
                decision = (
                    decision_raw if decision_raw in {"keep", "discard"} else "keep"
                )
                refinements[numeric_id] = RefinedScene(
                    scene_id=numeric_id,
                    decision=decision,
                    rationale=rationale,
                )
        for scene in scenes:
            scene_id = getattr(scene, "scene_id", None)
            if scene_id is None:
                continue
            refinements.setdefault(
                scene_id,
                RefinedScene(
                    scene_id=scene_id,
                    decision="keep",
                    rationale="No refinement returned; defaulting to keep.",
                ),
            )
        return refinements

    def _build_refinement_prompt(self, chapter: Chapter, scenes: list[RawScene]) -> str:
        chapter_number = getattr(chapter, "number", "?")
        chapter_title = getattr(chapter, "title", "")
        header = dedent(
            f"""
            You are the visual storytelling gatekeeper reviewing extracted scenes from Chapter {chapter_number} ({chapter_title}).

            GOAL
            - Keep only excerpts that already read like a cinematic moment with enough unique, concrete visuals to guide image or video generation.
            - If a scene feels borderline, choose `discard`.

            KEEP WHEN THE EXCERPT OFFERS
            - Multiple specific details about the setting, characters, objects, lighting, and motion that together form a coherent shot.
            - Novel or striking imagery that could anchor a composition without needing additional explanation.
            - Descriptions that let an artist infer the subject, the surrounding environment, and what is happening in the moment.
            - All of the above elements at once: a defined focal subject, a clearly described backdrop, and a meaningful action or transformation.

            DISCARD WHEN ANY ARE TRUE
            - The text is a single beat, reaction, or short exchange without broader spatial context.
            - The imagery hinges on one minor detail (e.g., a colour shift, a brief glance, a UI change) with no supporting description.
            - The language is generic, low-stakes, or dependent on prior narrative knowledge to visualise.
            - The moment centres on things like body-language beats, small talk, maintenance actions, or routine hospitality (e.g., turning, refilling a glass, belching) rather than showcasing the world.
            - The excerpt is short, static, or lacks a sense of place, atmosphere, or composition even if the actions are clear.
            - The passage is a transitional beat (e.g., travelling, glancing out a window, entering a room) that punts on describing the broader scene. Travel snippets where someone simply notices the surroundings should be discarded even if the technology sounds interesting.

            OUTPUT REQUIREMENTS
            - Evaluate each scene independently.
            - Respond with JSON only, following the provided schema exactly.
            - Provide a concise, specific rationale aligned with either `keep` or `discard`.
            """
        ).strip()
        scenes_text: list[str] = []
        for scene in scenes:
            scene_id = getattr(scene, "scene_id", None)
            if scene_id is None:
                continue
            location = str(getattr(scene, "location_marker", "")).strip()
            excerpt = str(getattr(scene, "raw_excerpt", "")).strip()
            if not excerpt:
                continue
            scenes_text.append(f"Scene {scene_id} | {location}\n{excerpt}\n---")
        scene_body = "\n".join(scenes_text)
        schema_hint = (
            "Schema reminder (types shown as comments):\n"
            '{\n  "scenes": [\n    {\n      "scene_id": "integer",\n      "decision": "keep|discard",\n      "rationale": "string"\n    }\n  ]\n}\n'
        )
        return f"{header}\n\n{schema_hint}\nScenes to review:\n\n{scene_body}"

    def _system_instruction(self) -> str:
        return (
            "You evaluate scene extractions for visual storytelling readiness. "
            "Respond with JSON only, following the provided schema exactly."
        )


__all__ = ["SceneRefiner", "RefinedScene", "SceneRefinementError", "REFINEMENT_SCHEMA"]
