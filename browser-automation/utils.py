"""Utility functions for Browser Automation API."""

from typing import Union


def normalize_use_vision(value: Union[str, bool]) -> Union[str, bool]:
    """Normalize use_vision parameter."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.lower()
        if lower == "true":
            return True
        elif lower == "false":
            return False
        else:
            return "auto"
    return "auto"


def is_empty_json_error(error_message: str) -> bool:
    """Detect empty/malformed JSON responses from providers like OpenAI."""
    if not error_message:
        return False

    indicators = [
        "EOF while parsing",
        "Invalid JSON",
        "input_value=''",
        "Expecting value",
        "No JSON object could be decoded",
    ]

    lowered = error_message.lower()
    return any(indicator.lower() in lowered for indicator in indicators)


def is_rate_limit_error(error_message: str) -> bool:
    """Detect rate limit style errors."""
    if not error_message:
        return False

    indicators = [
        "rate limit",
        "rate_limit_exceeded",
        "quota exceeded",
        "too many requests",
        "429",
    ]

    lowered = error_message.lower()
    return any(indicator in lowered for indicator in indicators)


def format_openai_error_message(original_error: str, error_type: str) -> str:
    """Provide tailored guidance for OpenAI-specific failures."""
    if error_type == "empty_json":
        base_msg = (
            "OpenAI returned an empty or malformed response. This is usually a transient issue."
        )
        suggestions = [
            "Retry the task (very likely to succeed)",
            "Check OpenAI status page for outages",
            "Ensure your API key has remaining quota",
        ]
    elif error_type == "rate_limit":
        base_msg = (
            "OpenAI API rate limit reached. Your account exceeded the allowed requests."
        )
        suggestions = [
            "Wait a few minutes and retry",
            "Upgrade the OpenAI plan for higher limits",
            "Switch to Gemini (no rate limits on free tier)",
        ]
    else:
        base_msg = f"OpenAI error: {original_error[:100]}"
        suggestions = [
            "Retry the task",
            "Try a different OpenAI model",
            "Check OpenAI status page for outages",
        ]

    formatted = f"{base_msg}\n\nSuggestions:\n"
    formatted += "\n".join(f"  - {tip}" for tip in suggestions)
    if original_error:
        formatted += f"\n\nOriginal error: {original_error[:200]}"

    return formatted
