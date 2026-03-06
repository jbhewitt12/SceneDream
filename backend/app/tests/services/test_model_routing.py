from __future__ import annotations

import pytest

from app.services.langchain.model_routing import (
    LLMRoutingConfig,
    LLMRoutingError,
    infer_provider_from_model_name,
    resolve_llm_model,
)


def test_infer_provider_from_model_name() -> None:
    assert infer_provider_from_model_name("gemini-2.5-flash") == "google"
    assert infer_provider_from_model_name("gpt-5-mini") == "openai"
    assert infer_provider_from_model_name("o3-mini") == "openai"
    assert infer_provider_from_model_name("unknown-model") is None


def test_resolve_llm_model_prefers_default_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    resolved = resolve_llm_model(
        LLMRoutingConfig(
            default_vendor="google",
            default_model="gemini-2.5-flash-lite",
            backup_vendor="openai",
            backup_model="gpt-5-mini",
        ),
        context="unit-test",
    )

    assert resolved.vendor == "google"
    assert resolved.model == "gemini-2.5-flash-lite"
    assert resolved.used_backup is False


def test_resolve_llm_model_uses_backup_when_default_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    resolved = resolve_llm_model(
        LLMRoutingConfig(
            default_vendor="google",
            default_model="gemini-2.5-flash-lite",
            backup_vendor="openai",
            backup_model="gpt-5-mini",
        ),
        context="unit-test",
    )

    assert resolved.vendor == "openai"
    assert resolved.model == "gpt-5-mini"
    assert resolved.used_backup is True


def test_resolve_llm_model_raises_without_available_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(
        LLMRoutingError, match="Set OPENAI_API_KEY and/or GEMINI_API_KEY"
    ):
        resolve_llm_model(
            LLMRoutingConfig(
                default_vendor="google",
                default_model="gemini-2.5-flash-lite",
                backup_vendor="openai",
                backup_model="gpt-5-mini",
            ),
            context="unit-test",
        )


def test_resolve_llm_model_rejects_same_provider_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    with pytest.raises(LLMRoutingError, match="must differ"):
        resolve_llm_model(
            LLMRoutingConfig(
                default_vendor="openai",
                default_model="gpt-5-mini",
                backup_vendor="openai",
                backup_model="gpt-5-nano",
            ),
            context="unit-test",
        )
