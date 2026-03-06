from __future__ import annotations

from pathlib import Path

import pytest

from app.services.image_prompt_generation.models import (
    ImagePromptGenerationServiceError,
)
from app.services.image_prompt_generation.prompt_builder import PromptBuilder


def test_load_cheatsheet_supports_legacy_backend_prefixed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cheatsheet = (
        tmp_path
        / "app/services/image_prompt_generation/cheatsheets/gpt_image_cheatsheet.md"
    )
    cheatsheet.parent.mkdir(parents=True, exist_ok=True)
    cheatsheet.write_text("legacy cheatsheet", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.image_prompt_generation.prompt_builder._BACKEND_ROOT",
        tmp_path,
    )

    builder = PromptBuilder()
    text = builder._load_cheatsheet(
        "backend/app/services/image_prompt_generation/cheatsheets/gpt_image_cheatsheet.md"
    )

    assert text == "legacy cheatsheet"


def test_load_cheatsheet_supports_app_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cheatsheet = (
        tmp_path
        / "app/services/image_prompt_generation/cheatsheets/dalle3_cheatsheet.md"
    )
    cheatsheet.parent.mkdir(parents=True, exist_ok=True)
    cheatsheet.write_text("app-relative cheatsheet", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.image_prompt_generation.prompt_builder._BACKEND_ROOT",
        tmp_path,
    )

    builder = PromptBuilder()
    text = builder._load_cheatsheet(
        "app/services/image_prompt_generation/cheatsheets/dalle3_cheatsheet.md"
    )

    assert text == "app-relative cheatsheet"


def test_load_cheatsheet_raises_for_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.image_prompt_generation.prompt_builder._BACKEND_ROOT",
        tmp_path,
    )
    builder = PromptBuilder()

    with pytest.raises(
        ImagePromptGenerationServiceError, match="Cheat sheet file not found"
    ):
        builder._load_cheatsheet(
            "app/services/image_prompt_generation/cheatsheets/missing.md"
        )
