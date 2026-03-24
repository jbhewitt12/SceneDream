"""Tests for scene refinement service behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.scene_extraction.scene_refinement as scene_refinement
from app.services.langchain.model_routing import ResolvedLLMModel
from app.services.scene_extraction.scene_extraction import Chapter, RawScene
from app.services.scene_extraction.scene_refinement import (
    SceneRefinementError,
    SceneRefiner,
)


def _chapter() -> Chapter:
    return Chapter(
        number=3,
        title="Refinement Tests",
        paragraphs=[],
        source_name="chapter3.xhtml",
    )


def _scenes() -> list[RawScene]:
    return [
        RawScene(
            chapter_number=3,
            chapter_title="Refinement Tests",
            provisional_id=1,
            location_marker="Paragraph 10-12",
            raw_excerpt="A storm fractures the moonlit skyline.",
            chunk_index=0,
            chunk_span=(10, 12),
            scene_id=1,
        ),
        RawScene(
            chapter_number=3,
            chapter_title="Refinement Tests",
            provisional_id=2,
            location_marker="Paragraph 13-15",
            raw_excerpt="Pilots guide cargo through electric fog.",
            chunk_index=0,
            chunk_span=(13, 15),
            scene_id=2,
        ),
    ]


def _refiner() -> SceneRefiner:
    return SceneRefiner(
        default_vendor="google",
        model="gemini-test",
        backup_vendor="openai",
        backup_model="gpt-test",
        temperature=0.1,
    )


def test_refine_happy_path_with_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_refinement,
        "resolve_llm_model",
        lambda *_args, **_kwargs: ResolvedLLMModel(
            vendor="google",
            model="gemini-test",
            used_backup=False,
        ),
    )

    async def fake_structured_output(**_kwargs: object) -> object:
        return scene_refinement._RefinementResponse(
            scenes=[
                scene_refinement._RefinementScenePayload(
                    scene_id=1,
                    decision="discard",
                    rationale="Not enough visual specificity.",
                )
            ]
        )

    monkeypatch.setattr(
        scene_refinement.gemini_api,
        "structured_output",
        fake_structured_output,
    )

    refinements = _refiner().refine(_chapter(), _scenes(), fail_on_error=True)

    assert refinements[1].decision == "discard"
    assert refinements[1].rationale == "Not enough visual specificity."
    assert refinements[2].decision == "keep"
    assert refinements[2].rationale == "No refinement returned; defaulting to keep."


def test_refine_falls_back_to_openai_when_router_selects_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_refinement,
        "resolve_llm_model",
        lambda *_args, **_kwargs: ResolvedLLMModel(
            vendor="openai",
            model="gpt-test",
            used_backup=True,
        ),
    )

    async def fail_gemini(**_kwargs: object) -> object:
        raise AssertionError("Gemini should not be called for openai route")

    async def fake_openai_structured_output(**_kwargs: object) -> object:
        return SimpleNamespace(
            scenes=[
                {
                    "scene_id": 1,
                    "decision": "keep",
                    "rationale": "Strong visual anchors.",
                },
                {
                    "scene_id": 2,
                    "decision": "discard",
                    "rationale": "Too transitional.",
                },
            ]
        )

    monkeypatch.setattr(
        scene_refinement.gemini_api,
        "structured_output",
        fail_gemini,
    )
    monkeypatch.setattr(
        scene_refinement.openai_api,
        "structured_output",
        fake_openai_structured_output,
    )

    refiner = _refiner()
    refinements = refiner.refine(_chapter(), _scenes(), fail_on_error=True)

    assert refinements[1].decision == "keep"
    assert refinements[2].decision == "discard"
    assert refiner.last_model_vendor == "openai"
    assert refiner.last_model_name == "gpt-test"


def test_refine_error_handling_returns_empty_or_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scene_refinement,
        "resolve_llm_model",
        lambda *_args, **_kwargs: ResolvedLLMModel(
            vendor="google",
            model="gemini-test",
            used_backup=False,
        ),
    )

    async def failing_structured_output(**_kwargs: object) -> object:
        raise RuntimeError("llm failure")

    monkeypatch.setattr(
        scene_refinement.gemini_api,
        "structured_output",
        failing_structured_output,
    )
    monkeypatch.setattr(
        scene_refinement.openai_api,
        "structured_output",
        failing_structured_output,
    )

    refiner = _refiner()

    result = refiner.refine(_chapter(), _scenes(), fail_on_error=False)
    assert result == {}

    with pytest.raises(SceneRefinementError, match="llm failure"):
        refiner.refine(_chapter(), _scenes(), fail_on_error=True)
