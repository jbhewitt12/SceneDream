"""Provider/model routing helpers for LLM calls with key-based fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

LLMProvider = Literal["google", "openai"]


class LLMRoutingError(RuntimeError):
    """Raised when provider/model routing cannot resolve a usable model."""


@dataclass(frozen=True, slots=True)
class LLMRoutingConfig:
    """Defines a preferred model and a required cross-provider backup model."""

    default_vendor: LLMProvider
    default_model: str
    backup_vendor: LLMProvider
    backup_model: str


@dataclass(frozen=True, slots=True)
class ResolvedLLMModel:
    """Resolved provider/model choice for an invocation."""

    vendor: LLMProvider
    model: str
    used_backup: bool = False


def infer_provider_from_model_name(model_name: str) -> LLMProvider | None:
    """Infer provider from a model identifier when possible."""
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("gemini"):
        return "google"
    if normalized.startswith("gpt"):
        return "openai"
    if normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai"
    return None


def _has_key(value: str | None) -> bool:
    return bool(value and value.strip())


def has_provider_api_key(provider: LLMProvider) -> bool:
    """Return True when an API key exists for the requested provider."""
    load_dotenv()
    if provider == "openai":
        return _has_key(os.getenv("OPENAI_API_KEY"))
    if provider == "google":
        return _has_key(os.getenv("GEMINI_API_KEY"))
    return False


def resolve_llm_model(
    routing: LLMRoutingConfig,
    *,
    context: str,
) -> ResolvedLLMModel:
    """Resolve the provider/model by checking default key availability then backup."""
    default_model = routing.default_model.strip()
    backup_model = routing.backup_model.strip()
    if not default_model:
        raise LLMRoutingError(f"{context}: default_model must be configured")
    if not backup_model:
        raise LLMRoutingError(f"{context}: backup_model must be configured")
    default_vendor = routing.default_vendor
    backup_vendor = routing.backup_vendor
    inferred_default = infer_provider_from_model_name(default_model)
    inferred_backup = infer_provider_from_model_name(backup_model)
    if inferred_default is not None:
        default_vendor = inferred_default
    if inferred_backup is not None:
        backup_vendor = inferred_backup
    if default_vendor == backup_vendor:
        raise LLMRoutingError(
            f"{context}: default and backup vendors must differ; "
            f"got {default_vendor!r} for both"
        )

    if has_provider_api_key(default_vendor):
        return ResolvedLLMModel(vendor=default_vendor, model=default_model)
    if has_provider_api_key(backup_vendor):
        return ResolvedLLMModel(
            vendor=backup_vendor,
            model=backup_model,
            used_backup=True,
        )

    raise LLMRoutingError(
        f"{context}: no API key available for either model provider "
        f"({default_vendor} -> {backup_vendor}). "
        "Set OPENAI_API_KEY and/or GEMINI_API_KEY."
    )


__all__ = [
    "LLMRoutingConfig",
    "LLMRoutingError",
    "LLMProvider",
    "ResolvedLLMModel",
    "has_provider_api_key",
    "infer_provider_from_model_name",
    "resolve_llm_model",
]
