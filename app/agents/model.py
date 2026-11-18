"""Build the Agno model from environment variables."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("openai",)


def _openai_model_class() -> Any:
    """Return an Agno OpenAI model class for the installed Agno version.

    ``OpenAIChat`` is the chat-completions model the code was written against;
    the fallbacks cover Agno builds that ship only the responses model.
    """
    try:
        from agno.models.openai import OpenAIChat

        return OpenAIChat
    except ImportError:  # pragma: no cover - depends on the installed Agno
        try:
            from agno.models.openai import OpenAI

            return OpenAI
        except ImportError:
            from agno.models.openai import OpenAIResponses

            return OpenAIResponses


def build_model() -> Any:
    """Build the Agno model object, defaulting to an OpenAI chat model.

    The provider and model name come from ``AGNO_MODEL_PROVIDER`` and
    ``MODEL_NAME``; the key comes from ``OPENAI_API_KEY`` and is never logged.
    """
    provider = (settings.agno_model_provider or "openai").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"unsupported AGNO_MODEL_PROVIDER {provider!r}; "
            f"supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set: copy .env.example to .env and add your key"
        )

    model_kwargs: dict[str, Any] = {
        "id": settings.model_name,
        "api_key": settings.openai_api_key,
    }
    if settings.openai_base_url:
        model_kwargs["base_url"] = settings.openai_base_url

    logger.info("using %s model %s", provider, settings.model_name)
    return _openai_model_class()(**model_kwargs)
