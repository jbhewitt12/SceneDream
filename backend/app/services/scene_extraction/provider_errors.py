from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.langchain.model_routing import (
    LLMProvider,
    infer_provider_from_model_name,
)


def _extract_exception_chain(exc: BaseException) -> list[str]:
    messages: list[str] = []
    seen_ids: set[int] = set()
    seen_messages: set[str] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen_ids:
        seen_ids.add(id(current))
        message = str(current).strip() or current.__class__.__name__
        if message not in seen_messages:
            messages.append(message[:500])
            seen_messages.add(message)
        current = current.__cause__ or current.__context__

    return messages


def _resolve_provider(
    provider: LLMProvider | str | None,
    model: str | None,
) -> LLMProvider | None:
    normalized = (provider or "").strip().lower()
    if normalized == "google":
        return "google"
    if normalized == "openai":
        return "openai"
    if model:
        return infer_provider_from_model_name(model)
    return None


def _provider_label(provider: LLMProvider | None) -> str:
    if provider == "openai":
        return "OpenAI"
    if provider == "google":
        return "Gemini"
    return "The configured provider"


def _provider_env_var(provider: LLMProvider | None) -> str | None:
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "google":
        return "GEMINI_API_KEY"
    return None


def _message_matches(text: str, keywords: tuple[str, ...]) -> bool:
    normalized_text = text.replace("_", " ").replace("-", " ")
    return any(
        keyword.replace("_", " ").replace("-", " ") in normalized_text
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
class ExtractionFailureInfo:
    code: str
    message: str
    category: str
    hint: str
    action_items: tuple[str, ...]
    provider: str | None = None
    model: str | None = None
    cause_messages: tuple[str, ...] = ()

    def metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "category": self.category,
            "hint": self.hint,
            "action_items": list(self.action_items),
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.model:
            payload["model"] = self.model
        return payload


class ExtractionFatalError(RuntimeError):
    def __init__(self, info: ExtractionFailureInfo) -> None:
        super().__init__(info.message)
        self.info = info

    @property
    def error_code(self) -> str:
        return self.info.code

    @property
    def display_message(self) -> str:
        return self.info.message

    @property
    def error_metadata(self) -> dict[str, Any]:
        return self.info.metadata()

    @property
    def cause_messages(self) -> list[str]:
        return list(self.info.cause_messages) or [self.info.message]


class ExtractionSetupError(ExtractionFatalError):
    """Raised when extraction cannot start because required setup is missing."""


class ExtractionProviderAccessError(ExtractionFatalError):
    """Raised when the provider rejects credentials or model access."""


class ExtractionQuotaError(ExtractionFatalError):
    """Raised when the provider account lacks quota or credits."""


class ExtractionRateLimitError(ExtractionFatalError):
    """Raised when provider throttling blocks extraction startup."""


def classify_extraction_provider_error(
    exc: BaseException,
    *,
    provider: LLMProvider | str | None,
    model: str | None,
) -> ExtractionFatalError | None:
    resolved_provider = _resolve_provider(provider, model)
    provider_label = _provider_label(resolved_provider)
    provider_env_var = _provider_env_var(resolved_provider)
    messages = _extract_exception_chain(exc)
    message_text = " | ".join(message.lower() for message in messages)
    status_code = _status_code(exc)

    if _message_matches(message_text, _MISSING_CREDENTIALS_KEYWORDS):
        if provider_env_var is not None:
            hint = f"Add {provider_env_var} to your .env file and restart the backend."
            action_items = (
                f"Add a valid {provider_env_var} value to `.env`.",
                "Restart the backend so the updated environment is loaded.",
                "Rerun the pipeline.",
            )
        else:
            hint = (
                "Add OPENAI_API_KEY and/or GEMINI_API_KEY to your .env file and "
                "restart the backend."
            )
            action_items = (
                "Add a valid API key for at least one configured extraction provider.",
                "Restart the backend so the updated environment is loaded.",
                "Rerun the pipeline.",
            )
        message = "No API key is configured for extraction."
        return ExtractionSetupError(
            ExtractionFailureInfo(
                code="extraction_setup_error",
                message=message,
                category="missing_credentials",
                hint=hint,
                action_items=action_items,
                provider=resolved_provider,
                model=model,
                cause_messages=(message,),
            )
        )

    if _message_matches(message_text, _QUOTA_KEYWORDS):
        message = f"Your {provider_label} account does not have available credits for extraction."
        return ExtractionQuotaError(
            ExtractionFailureInfo(
                code="extraction_quota_error",
                message=message,
                category="quota",
                hint=f"Add billing or prepaid credits to your {provider_label} account, then rerun the pipeline.",
                action_items=(
                    f"Confirm billing is enabled for your {provider_label} API account.",
                    "Add credits or raise your usage limit.",
                    "Rerun the pipeline.",
                ),
                provider=resolved_provider,
                model=model,
                cause_messages=(message,),
            )
        )

    if status_code == 401 or _message_matches(message_text, _AUTH_KEYWORDS):
        auth_action = (
            f"Replace {provider_env_var} with a valid key and restart the backend."
            if provider_env_var is not None
            else "Replace the configured API key with a valid value and restart the backend."
        )
        message = f"{provider_label} rejected the configured API key for extraction."
        return ExtractionProviderAccessError(
            ExtractionFailureInfo(
                code="extraction_auth_error",
                message=message,
                category="authentication",
                hint=auth_action,
                action_items=(
                    "Check that the configured API key is valid and active.",
                    "Update the key in `.env` if needed.",
                    "Restart the backend and rerun the pipeline.",
                ),
                provider=resolved_provider,
                model=model,
                cause_messages=(message,),
            )
        )

    if status_code == 403 or _message_matches(message_text, _MODEL_ACCESS_KEYWORDS):
        model_name = model or "the configured extraction model"
        message = (
            f"Your {provider_label} account cannot use the configured extraction model."
        )
        return ExtractionProviderAccessError(
            ExtractionFailureInfo(
                code="extraction_model_access_error",
                message=message,
                category="model_access",
                hint=(
                    f"Confirm your account has access to {model_name} or change the "
                    "configured extraction model."
                ),
                action_items=(
                    f"Confirm {model_name} is enabled for your account.",
                    "Change the extraction model configuration if needed.",
                    "Rerun the pipeline.",
                ),
                provider=resolved_provider,
                model=model,
                cause_messages=(message,),
            )
        )

    if status_code == 429 or _message_matches(message_text, _RATE_LIMIT_KEYWORDS):
        message = f"{provider_label} rate limits prevented extraction from starting."
        return ExtractionRateLimitError(
            ExtractionFailureInfo(
                code="extraction_rate_limit_error",
                message=message,
                category="rate_limit",
                hint="Retry later or reduce the extraction workload if this persists.",
                action_items=(
                    "Wait a few minutes before retrying.",
                    "Reduce concurrency or workload if the problem repeats.",
                    "Rerun the pipeline.",
                ),
                provider=resolved_provider,
                model=model,
                cause_messages=(message,),
            )
        )

    return None


__all__ = [
    "ExtractionFatalError",
    "ExtractionProviderAccessError",
    "ExtractionQuotaError",
    "ExtractionRateLimitError",
    "ExtractionSetupError",
    "classify_extraction_provider_error",
]
