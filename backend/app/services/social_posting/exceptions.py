"""Exceptions for social media posting service."""


class RateLimitError(Exception):
    """Raised when a social media API returns a rate limit error."""

    pass


class SocialPostingDisabledError(Exception):
    """Raised when social posting is globally disabled in settings."""

    pass
