from __future__ import annotations

import pytest

from app.services.configuration_test_service import ConfigurationTestService
from app.services.langchain import gemini_api, openai_api


@pytest.mark.anyio("asyncio")
async def test_run_reports_pipeline_ready_with_openai_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    calls: list[str] = []

    async def fake_openai_simple_call(
        prompt: str,
        model: str,
        temperature: float,
        **_: object,
    ) -> str:
        assert prompt == "Reply with OK only."
        assert temperature == 0.0
        calls.append(model)
        return "OK"

    async def unexpected_gemini_simple_call(**_: object) -> str:
        raise AssertionError("Gemini should not be used when only OpenAI is configured")

    monkeypatch.setattr(openai_api, "simple_call", fake_openai_simple_call)
    monkeypatch.setattr(gemini_api, "simple_call", unexpected_gemini_simple_call)

    service = ConfigurationTestService()
    result = await service.run()

    checks = {check.key: check for check in result.checks}

    assert result.ready_for_pipeline is True
    assert result.status == "passed"
    assert len(calls) == 3
    assert set(checks) == {
        "scene_extraction",
        "scene_ranking",
        "prompt_generation",
    }
    assert checks["scene_extraction"].status == "passed"
    assert checks["scene_extraction"].provider == "openai"
    assert checks["scene_extraction"].used_backup_model is True
    assert checks["scene_ranking"].status == "passed"
    assert checks["prompt_generation"].status == "passed"


@pytest.mark.anyio("asyncio")
async def test_run_fails_when_no_provider_keys_are_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    service = ConfigurationTestService()
    result = await service.run()

    checks = {check.key: check for check in result.checks}

    assert result.ready_for_pipeline is False
    assert result.status == "failed"
    assert set(checks) == {
        "scene_extraction",
        "scene_ranking",
        "prompt_generation",
    }
    assert checks["scene_extraction"].status == "failed"
    assert checks["scene_extraction"].metadata["category"] == "missing_credentials"
    assert "OPENAI_API_KEY" in (checks["scene_extraction"].hint or "")
    assert checks["scene_ranking"].status == "failed"
    assert checks["scene_ranking"].metadata["category"] == "missing_credentials"
    assert checks["prompt_generation"].status == "failed"
    assert checks["prompt_generation"].metadata["category"] == "missing_credentials"


@pytest.mark.anyio("asyncio")
async def test_run_surfaces_provider_auth_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    async def fake_openai_simple_call(**_: object) -> str:
        raise RuntimeError("Incorrect API key provided: invalid key")

    monkeypatch.setattr(openai_api, "simple_call", fake_openai_simple_call)

    service = ConfigurationTestService()
    result = await service.run()

    failed_checks = [check for check in result.checks if check.status == "failed"]

    assert result.ready_for_pipeline is False
    assert result.status == "failed"
    assert len(failed_checks) == 3
    assert all(check.metadata["category"] == "authentication" for check in failed_checks)
    assert all(
        "rejected the configured API key" in check.message for check in failed_checks
    )
