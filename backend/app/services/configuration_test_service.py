"""Runtime configuration diagnostics for first-run pipeline setup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import time
from typing import Any

from app.api.errors import extract_exception_chain, is_safe_error_message
from app.core.config import settings
from app.schemas.app_settings import ConfigurationCheckRead, ConfigurationTestResponse
from app.services.image_generation import (
    dalle_image_api,  # noqa: F401 - ensures provider registration
    gpt_image_api,  # noqa: F401 - ensures provider registration
)
from app.services.image_generation.provider_registry import ProviderRegistry
from app.services.image_prompt_generation.models import ImagePromptGenerationConfig
from app.services.langchain import gemini_api, openai_api
from app.services.langchain.model_routing import (
    LLMProvider,
    LLMRoutingConfig,
    ResolvedLLMModel,
    resolve_llm_model,
)
from app.services.scene_extraction.scene_extraction import SceneExtractionConfig
from app.services.scene_ranking.scene_ranking_service import SceneRankingConfig

_MISSING_CREDENTIALS_KEYWORDS = (
    "no api key available",
    "api key not found",
    "api key is required",
    "api key missing",
    "no credentials",
    "credential is missing",
    "set openai_api_key",
    "set gemini_api_key",
)
_AUTH_KEYWORDS = (
    "incorrect api key",
    "invalid api key",
    "api key not valid",
    "invalid authentication",
    "authentication failed",
    "authentication error",
    "unauthorized",
    "unauthenticated",
    "invalid credentials",
    "revoked",
)
_QUOTA_KEYWORDS = (
    "insufficient_quota",
    "insufficient quota",
    "exceeded your current quota",
    "out of credits",
    "no credits",
    "billing hard limit",
    "credit balance",
    "prepaid balance",
    "please check your plan and billing details",
)
_MODEL_ACCESS_KEYWORDS = (
    "model not found",
    "does not have access to model",
    "do not have access to model",
    "you do not have access",
    "not authorized to access this model",
    "access to this model is denied",
    "unsupported model",
    "model is not supported",
    "is not supported for this account",
    "not available for your account",
    "not found or you do not have access",
)
_RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "too many requests",
    "resource exhausted",
    "resourceexhausted",
    "rate_limit_exceeded",
    "429",
)


@dataclass(frozen=True, slots=True)
class _LlmStageSpec:
    key: str
    label: str
    routing: LLMRoutingConfig


@dataclass(frozen=True, slots=True)
class _ProviderProbeFailure:
    message: str
    hint: str
    action_items: tuple[str, ...]
    metadata: dict[str, Any]
    cause_messages: list[str]


def _provider_label(provider: LLMProvider | str | None) -> str:
    normalized = (provider or "").strip().lower()
    if normalized == "openai":
        return "OpenAI"
    if normalized == "google":
        return "Gemini"
    return "The configured provider"


def _provider_env_var(provider: LLMProvider | str | None) -> str | None:
    normalized = (provider or "").strip().lower()
    if normalized == "openai":
        return "OPENAI_API_KEY"
    if normalized == "google":
        return "GEMINI_API_KEY"
    return None


def _message_matches(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.replace("_", " ").replace("-", " ")
    return any(
        keyword.replace("_", " ").replace("-", " ") in normalized
        for keyword in keywords
    )


def _status_code(exc: BaseException) -> int | None:
    raw_status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(raw_status, int):
        return raw_status

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None


def _safe_exception_messages(exc: BaseException) -> list[str]:
    return [
        message
        for message in extract_exception_chain(exc)
        if is_safe_error_message(message)
    ]


def _classify_provider_probe_error(
    exc: BaseException,
    *,
    provider: LLMProvider | str | None,
    model: str | None,
) -> _ProviderProbeFailure | None:
    provider_label = _provider_label(provider)
    provider_env_var = _provider_env_var(provider)
    safe_messages = _safe_exception_messages(exc)
    message_text = " | ".join(message.lower() for message in safe_messages)
    status_code = _status_code(exc)

    if _message_matches(message_text, _MISSING_CREDENTIALS_KEYWORDS):
        if provider_env_var is not None:
            hint = f"Add {provider_env_var} to `.env` and restart the backend."
            action_items = (
                f"Add a valid {provider_env_var} value to `.env`.",
                "Restart the backend so the updated environment is loaded.",
                "Run the configuration test again.",
            )
        else:
            hint = (
                "Add OPENAI_API_KEY and/or GEMINI_API_KEY to `.env` and restart "
                "the backend."
            )
            action_items = (
                "Add a valid API key for at least one configured provider.",
                "Restart the backend so the updated environment is loaded.",
                "Run the configuration test again.",
            )
        return _ProviderProbeFailure(
            message="No API key is configured for this check.",
            hint=hint,
            action_items=action_items,
            metadata={"category": "missing_credentials"},
            cause_messages=safe_messages
            or ["No API key is configured for this check."],
        )

    if _message_matches(message_text, _QUOTA_KEYWORDS):
        return _ProviderProbeFailure(
            message=f"Your {provider_label} account does not have available credits.",
            hint=(
                f"Add billing or prepaid credits to your {provider_label} account, "
                "then rerun this test."
            ),
            action_items=(
                f"Confirm billing is enabled for your {provider_label} API account.",
                "Add credits or raise your usage limit.",
                "Run the configuration test again.",
            ),
            metadata={"category": "quota"},
            cause_messages=safe_messages
            or [f"Your {provider_label} account does not have available credits."],
        )

    if status_code == 401 or _message_matches(message_text, _AUTH_KEYWORDS):
        return _ProviderProbeFailure(
            message=f"{provider_label} rejected the configured API key.",
            hint=(
                f"Replace {provider_env_var} with a valid key and restart the backend."
                if provider_env_var is not None
                else "Replace the configured API key with a valid value and restart the backend."
            ),
            action_items=(
                "Check that the configured API key is valid and active.",
                "Update the key in `.env` if needed.",
                "Restart the backend and run the test again.",
            ),
            metadata={"category": "authentication"},
            cause_messages=safe_messages
            or [f"{provider_label} rejected the configured API key."],
        )

    if status_code == 403 or _message_matches(message_text, _MODEL_ACCESS_KEYWORDS):
        model_name = model or "the configured model"
        return _ProviderProbeFailure(
            message=f"Your {provider_label} account cannot use {model_name}.",
            hint=f"Confirm your account has access to {model_name}, then rerun this test.",
            action_items=(
                f"Confirm {model_name} is enabled for your account.",
                "Change the configured model if needed.",
                "Run the configuration test again.",
            ),
            metadata={"category": "model_access"},
            cause_messages=safe_messages
            or [f"Your {provider_label} account cannot use {model_name}."],
        )

    if status_code == 429 or _message_matches(message_text, _RATE_LIMIT_KEYWORDS):
        return _ProviderProbeFailure(
            message=f"{provider_label} rate limits prevented this test from completing.",
            hint="Wait a few minutes and rerun the test.",
            action_items=(
                "Wait a few minutes before retrying.",
                "Reduce concurrent activity on the provider account if the problem repeats.",
                "Run the configuration test again.",
            ),
            metadata={"category": "rate_limit"},
            cause_messages=safe_messages
            or [f"{provider_label} rate limits prevented this test from completing."],
        )

    return None


class ConfigurationTestService:
    """Probe the configured pipeline providers without running a full document."""

    async def run(self) -> ConfigurationTestResponse:
        extraction_config = SceneExtractionConfig()
        ranking_config = SceneRankingConfig()
        prompt_config = ImagePromptGenerationConfig()

        llm_checks = [
            await self._run_llm_stage_check(
                _LlmStageSpec(
                    key="scene_extraction",
                    label="Scene extraction",
                    routing=LLMRoutingConfig(
                        default_vendor=extraction_config.extraction_model_vendor,
                        default_model=extraction_config.gemini_model,
                        backup_vendor=extraction_config.extraction_backup_model_vendor,
                        backup_model=extraction_config.extraction_backup_model,
                    ),
                )
            ),
            await self._run_llm_stage_check(
                _LlmStageSpec(
                    key="scene_ranking",
                    label="Scene ranking",
                    routing=LLMRoutingConfig(
                        default_vendor=ranking_config.model_vendor,
                        default_model=ranking_config.model_name,
                        backup_vendor=ranking_config.backup_model_vendor,
                        backup_model=ranking_config.backup_model_name,
                    ),
                )
            ),
            await self._run_llm_stage_check(
                _LlmStageSpec(
                    key="prompt_generation",
                    label="Prompt generation",
                    routing=LLMRoutingConfig(
                        default_vendor=prompt_config.model_vendor,
                        default_model=prompt_config.model_name,
                        backup_vendor=prompt_config.backup_model_vendor,
                        backup_model=prompt_config.backup_model_name,
                    ),
                )
            ),
        ]
        checks = [*llm_checks, self._run_image_generation_check()]
        failed_checks = [check for check in checks if check.status == "failed"]
        warning_checks = [check for check in checks if check.status == "warning"]

        if failed_checks:
            status = "failed"
            ready_for_pipeline = False
            if len(failed_checks) == 1:
                summary = (
                    f"{failed_checks[0].label} failed. Fix the issue below and rerun "
                    "the test."
                )
            else:
                summary = (
                    f"{len(failed_checks)} checks failed. Fix the failed items below "
                    "and rerun the test."
                )
        elif warning_checks:
            status = "warning"
            ready_for_pipeline = True
            summary = (
                "LLM access checks passed. Image generation configuration was only "
                "validated locally to avoid billed test images."
            )
        else:
            status = "passed"
            ready_for_pipeline = True
            summary = "All configuration checks passed."

        return ConfigurationTestResponse(
            status=status,
            ready_for_pipeline=ready_for_pipeline,
            summary=summary,
            checked_at=datetime.now(timezone.utc),
            checks=checks,
        )

    async def _run_llm_stage_check(
        self,
        spec: _LlmStageSpec,
    ) -> ConfigurationCheckRead:
        try:
            resolved = resolve_llm_model(
                spec.routing,
                context=f"{spec.label} configuration test",
            )
        except Exception as exc:
            return self._build_failed_check(
                key=spec.key,
                label=spec.label,
                provider=None,
                model=None,
                used_backup_model=False,
                latency_ms=None,
                exc=exc,
            )

        started_at = time.perf_counter()
        try:
            await self._probe_llm(provider=resolved.vendor, model=resolved.model)
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started_at) * 1000)
            return self._build_failed_check(
                key=spec.key,
                label=spec.label,
                provider=resolved.vendor,
                model=resolved.model,
                used_backup_model=resolved.used_backup,
                latency_ms=latency_ms,
                exc=exc,
            )

        latency_ms = round((time.perf_counter() - started_at) * 1000)
        provider_name = _provider_label(resolved.vendor)
        message = (
            f"Connected to {provider_name} {resolved.model} via the configured backup "
            "model."
            if resolved.used_backup
            else f"Connected to {provider_name} {resolved.model}."
        )
        return ConfigurationCheckRead(
            key=spec.key,
            label=spec.label,
            status="passed",
            provider=resolved.vendor,
            model=resolved.model,
            used_backup_model=resolved.used_backup,
            message=message,
            latency_ms=latency_ms,
        )

    async def _probe_llm(
        self,
        *,
        provider: LLMProvider,
        model: str,
    ) -> None:
        prompt = "Reply with OK only."
        if provider == "openai":
            await openai_api.simple_call(
                prompt=prompt,
                model=model,
                temperature=0.0,
                max_tokens=8,
                request_timeout=45,
            )
            return
        if provider == "google":
            await gemini_api.simple_call(
                prompt=prompt,
                model=model,
                temperature=0.0,
                max_output_tokens=8,
                request_timeout=45,
            )
            return
        raise ValueError(f"Unsupported provider for configuration test: {provider}")

    def _run_image_generation_check(self) -> ConfigurationCheckRead:
        provider_name = settings.DEFAULT_IMAGE_PROVIDER
        model_name = settings.DEFAULT_IMAGE_MODEL
        provider = ProviderRegistry.get(provider_name)

        if provider is None:
            return ConfigurationCheckRead(
                key="image_generation",
                label="Image generation",
                status="failed",
                provider=provider_name,
                model=model_name,
                used_backup_model=False,
                message=f"Unknown image provider: {provider_name}.",
                hint="Change DEFAULT_IMAGE_PROVIDER to a registered provider.",
                action_items=[
                    "Set DEFAULT_IMAGE_PROVIDER to a supported value.",
                    "Restart the backend and rerun the configuration test.",
                ],
                metadata={"available_providers": ProviderRegistry.list_providers()},
            )

        if model_name not in provider.supported_models:
            return ConfigurationCheckRead(
                key="image_generation",
                label="Image generation",
                status="failed",
                provider=provider_name,
                model=model_name,
                used_backup_model=False,
                message=f"{provider_name} does not support {model_name}.",
                hint="Change DEFAULT_IMAGE_MODEL to a model supported by the selected provider.",
                action_items=[
                    f"Choose one of: {', '.join(provider.supported_models)}.",
                    "Restart the backend and rerun the configuration test.",
                ],
                metadata={"supported_models": list(provider.supported_models)},
            )

        api_key = self._resolve_image_provider_api_key(provider_name)
        is_valid, error = provider.validate_config(api_key)
        if not is_valid:
            hint = "Add OPENAI_API_KEY to `.env` and restart the backend."
            if error and "format" in error.lower():
                hint = (
                    "Replace OPENAI_API_KEY with a valid key and restart the backend."
                )
            return ConfigurationCheckRead(
                key="image_generation",
                label="Image generation",
                status="failed",
                provider=provider_name,
                model=model_name,
                used_backup_model=False,
                message=error or "Image generation is not configured correctly.",
                hint=hint,
                action_items=[
                    "Update the image generation API key in `.env`.",
                    "Restart the backend so the updated environment is loaded.",
                    "Run the configuration test again.",
                ],
            )

        return ConfigurationCheckRead(
            key="image_generation",
            label="Image generation",
            status="warning",
            provider=provider_name,
            model=model_name,
            used_backup_model=False,
            message=(
                "Local image-generation configuration looks valid. SceneDream did "
                "not generate a billed test image."
            ),
            hint=(
                "Your first real image request is still the final check for "
                "image-generation-specific billing and model access."
            ),
            metadata={"remote_probe_skipped": True},
        )

    def _resolve_image_provider_api_key(self, provider_name: str) -> str | None:
        if provider_name in {"openai", "openai_gpt_image"}:
            if "OPENAI_API_KEY" in os.environ:
                return os.getenv("OPENAI_API_KEY")
            return settings.OPENAI_API_KEY
        return None

    def _build_failed_check(
        self,
        *,
        key: str,
        label: str,
        provider: LLMProvider | str | None,
        model: str | None,
        used_backup_model: bool,
        latency_ms: int | None,
        exc: Exception,
    ) -> ConfigurationCheckRead:
        classified = _classify_provider_probe_error(
            exc,
            provider=provider,
            model=model,
        )
        if classified is not None:
            return ConfigurationCheckRead(
                key=key,
                label=label,
                status="failed",
                provider=str(provider) if provider else None,
                model=model,
                used_backup_model=used_backup_model,
                message=classified.message,
                hint=classified.hint,
                action_items=list(classified.action_items),
                cause_messages=classified.cause_messages,
                latency_ms=latency_ms,
                metadata=classified.metadata,
            )

        safe_messages = _safe_exception_messages(exc)
        message = safe_messages[0] if safe_messages else "Configuration test failed."
        return ConfigurationCheckRead(
            key=key,
            label=label,
            status="failed",
            provider=str(provider) if provider else None,
            model=model,
            used_backup_model=used_backup_model,
            message=message,
            hint="Check the backend logs and provider configuration, then rerun the test.",
            cause_messages=safe_messages,
            latency_ms=latency_ms,
        )


__all__ = ["ConfigurationTestService"]
