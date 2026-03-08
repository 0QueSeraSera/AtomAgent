"""Content redaction and truncation utilities."""

from __future__ import annotations

import re

# Pattern to match API keys (common formats)
_API_KEY_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|"
    r"sk_live_[a-zA-Z0-9]{20,}|"
    r"sk_test_[a-zA-Z0-9]{20,}|"
    r"Bearer\s+[a-zA-Z0-9_-]{20,}|"
    r"[aA]pi[_-]?[kK]ey[=:]\s*[a-zA-Z0-9_-]{20,}|"
    r"x-api-key[=:]\s*[a-zA-Z0-9_-]{20,})"
)

_REDACTED = "[REDACTED]"


def truncate_content(text: str | None, max_len: int = 200) -> str:
    """
    Truncate content to a maximum length.

    Args:
        text: The text to truncate
        max_len: Maximum length (default 200)

    Returns:
        Truncated text with ellipsis if needed, or empty string if None
    """
    if text is None:
        return ""

    if len(text) <= max_len:
        return text

    # Try to truncate at a word boundary
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]

    return truncated + "..."


def redact_api_key(text: str | None) -> str:
    """
    Redact API keys from text.

    Args:
        text: The text to redact

    Returns:
        Text with API keys replaced by [REDACTED]
    """
    if text is None:
        return ""

    return _API_KEY_PATTERN.sub(_REDACTED, text)


def safe_repr(obj: object, max_len: int = 100) -> str:
    """
    Create a safe string representation of an object.

    Truncates and redacts potentially sensitive information.

    Args:
        obj: Object to represent
        max_len: Maximum length

    Returns:
        Safe string representation
    """
    try:
        text = repr(obj)
    except Exception:
        return "<unrepresentable>"

    text = redact_api_key(text)
    return truncate_content(text, max_len)
