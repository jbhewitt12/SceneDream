from __future__ import annotations

import asyncio

import pytest
from sqlmodel import Session

from app.services.langchain import gemini_api, openai_api
from app.services.prompt_metadata import (
    PromptMetadataConfig,
    PromptMetadataGenerationService,
)


def test_generate_metadata_falls_back_to_openai(
    db: Session,
    scene_factory,
    prompt_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)

    async def fail_gemini(**_: object) -> dict[str, object]:
        raise AssertionError("Gemini should not be called when key is missing")

    async def fake_openai_json_output(**_: object) -> dict[str, object]:
        return {
            "title": "Neon Verdict",
            "flavour_text": "City lights whisper truths no witness can afford to hear.",
        }

    monkeypatch.setattr(gemini_api, "json_output", fail_gemini)
    monkeypatch.setattr(openai_api, "json_output", fake_openai_json_output)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    service = PromptMetadataGenerationService(
        db,
        PromptMetadataConfig(dry_run=True),
    )
    result = asyncio.run(
        service.generate_metadata_for_prompt(prompt, overwrite=True, dry_run=True)
    )

    assert isinstance(result, dict)
    assert result["title"] == "Neon Verdict"
    assert result["flavour_text"]


def test_build_metadata_prompt_bans_gilded(
    db: Session,
    scene_factory,
    prompt_factory,
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    service = PromptMetadataGenerationService(db)

    payload = service._build_metadata_prompt(prompt)

    assert 'Never use the word "gilded" in the title or flavour text.' in payload


def test_build_variants_prompt_bans_gilded(
    db: Session,
    scene_factory,
    prompt_factory,
) -> None:
    scene = scene_factory()
    prompt = prompt_factory(scene)
    service = PromptMetadataGenerationService(db)

    payload = service._build_variants_prompt(prompt, variants_count=3)

    assert 'Never use the word "gilded" in any title or flavour text.' in payload
