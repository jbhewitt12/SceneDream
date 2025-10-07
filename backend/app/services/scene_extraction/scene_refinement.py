from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from app.services.langchain import gemini_api

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .scene_extraction import Chapter, RawScene


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _RefinementScenePayload(BaseModel):
    scene_id: int = Field(..., description="Original scene identifier.")
    decision: str = Field(..., description="Either 'keep' or 'discard'.")
    rationale: str = Field(..., description="Brief explanation for the decision.")


class _RefinementResponse(BaseModel):
    scenes: List[_RefinementScenePayload]


REFINEMENT_SCHEMA: Dict[str, object] = {
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
    """Handles scene refinement with Gemini."""

    def __init__(
        self,
        *,
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def refine(
        self,
        chapter: "Chapter",
        scenes: List["RawScene"],
        *,
        fail_on_error: bool = False,
    ) -> Dict[int, RefinedScene]:
        if not scenes:
            return {}
        prompt = self._build_refinement_prompt(chapter, scenes)
        try:
            payload = gemini_api.structured_output(
                prompt=prompt,
                schema=_RefinementResponse,
                method="json_mode",
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            chapter_number = getattr(chapter, "number", "?")
            logger.error("Refinement failed for chapter %s: %s", chapter_number, exc)
            if fail_on_error:
                raise SceneRefinementError(str(exc)) from exc
            return {}
        entries = payload.scenes if hasattr(payload, "scenes") else None
        refinements: Dict[int, RefinedScene] = {}
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
                decision = decision_raw if decision_raw in {"keep", "discard"} else "keep"
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

    def _build_refinement_prompt(self, chapter: "Chapter", scenes: List["RawScene"]) -> str:
        chapter_number = getattr(chapter, "number", "?")
        chapter_title = getattr(chapter, "title", "")
        header = (
            f"Review the extracted scenes from Chapter {chapter_number} ({chapter_title}).\n"
            "For each scene, respond with a decision of keep or discard.\n"
            "Keep only scenes that communicate unique, visually specific details that can inspire image or video generation. We only want scenes that have something interesting about them. Be selective.\n"
            "Discard scenes that lack descriptive detail (e.g. 'A smile flickered around his lips, like a small flame in a high wind.'),\n"
            "do not include anything original or unique (e.g. 'She sucked at the knuckle she'd hit against the field cylinder.'),\n"
            "omit concrete visual elements (e.g. 'The sound of another great tumble of falling rock split the skies.'), or\n"
            "are just descriptions of basic things (e.g. 'She reached out across the sand and pulled a straw sun-hat over her head.').\n"
            "Provide a brief rationale for each decision.\n"
            "Return structured JSON matching the provided schema."
        )
        scenes_text: List[str] = []
        for scene in scenes:
            scene_id = getattr(scene, "scene_id", None)
            if scene_id is None:
                continue
            location = str(getattr(scene, "location_marker", "")).strip()
            excerpt = str(getattr(scene, "raw_excerpt", "")).strip()
            if not excerpt:
                continue
            scenes_text.append(
                f"Scene {scene_id} | {location}\n{excerpt}\n---"
            )
        scene_body = "\n".join(scenes_text)
        schema_hint = (
            "Schema reminder (types shown as comments):\n"
            "{\n  \"scenes\": [\n    {\n      \"scene_id\": \"integer\",\n      \"decision\": \"keep|discard\",\n      \"rationale\": \"string\"\n    }\n  ]\n}\n"
        )
        return f"{header}\n\n{schema_hint}\nScenes to review:\n\n{scene_body}"

    def _system_instruction(self) -> str:
        return (
            "You evaluate scene extractions for visual storytelling readiness. "
            "Respond with JSON only, following the provided schema exactly."
        )


__all__ = ["SceneRefiner", "RefinedScene", "SceneRefinementError", "REFINEMENT_SCHEMA"]
