"""LLM Factory - Creates native browser-use LLM instances.

No Langchain required! browser-use provides native LLM wrappers:
- ChatBrowserUse: Optimized for browser automation (fastest)
- ChatGoogle: Google Gemini models
- ChatOpenAI: OpenAI GPT models
- ChatAnthropic: Anthropic Claude models
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

LLMProvider = Literal["browseruse", "gemini", "openai", "anthropic"]


def create_llm(
    provider: LLMProvider,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> Any:
    """Create LLM instance using native browser-use classes.

    Args:
        provider: LLM provider name
        model: Model name/ID (uses provider default if not specified)
        temperature: Model temperature (default 0.0 for deterministic output)

    Returns:
        Native browser-use LLM instance

    Raises:
        ValueError: If provider is not supported
        ImportError: If required browser-use components not available
    """
    provider = provider.lower()

    if provider == "browseruse":
        from browser_use import ChatBrowserUse
        logger.info("Creating ChatBrowserUse LLM")
        # ChatBrowserUse uses BROWSER_USE_API_KEY env var
        return ChatBrowserUse()

    elif provider in ("gemini", "google"):
        from browser_use import ChatGoogle
        model_name = model or "gemini-flash-latest"
        logger.info("Creating ChatGoogle LLM with model: %s", model_name)
        return ChatGoogle(model=model_name)

    elif provider == "openai":
        from browser_use import ChatOpenAI
        model_name = model or "gpt-5-mini"
        logger.info("Creating ChatOpenAI LLM with model: %s", model_name)
        return ChatOpenAI(model=model_name)

    elif provider == "anthropic":
        from browser_use import ChatAnthropic
        model_name = model or "claude-haiku-4-5"
        logger.info("Creating ChatAnthropic LLM with model: %s", model_name)
        return ChatAnthropic(model=model_name, temperature=temperature)

    else:
        # Default to Gemini as it has free tier
        logger.warning("Unknown provider '%s', falling back to Gemini", provider)
        from browser_use import ChatGoogle
        return ChatGoogle(model="gemini-flash-latest")


def get_default_model(provider: LLMProvider) -> str:
    """Get default model for a provider."""
    defaults = {
        "browseruse": "browseruse-default",
        "gemini": "gemini-flash-latest",
        "google": "gemini-flash-latest",
        "openai": "gpt-5-mini",
        "anthropic": "claude-haiku-4-5",
    }
    return defaults.get(provider.lower(), "gemini-flash-latest")
