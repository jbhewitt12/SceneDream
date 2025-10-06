"""Local stub for sentry_sdk to allow OpenAPI generation without dependency."""

def init(*_args, **_kwargs) -> None:
    """No-op init for environments where sentry-sdk isn't installed."""

