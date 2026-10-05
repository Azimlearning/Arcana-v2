"""Build the LLM service for the configured mode (ARCANA_LLM_MODE)."""

from __future__ import annotations

from collections.abc import Callable

from api.core.settings import Settings
from api.llm.ledger import SpendLedger
from api.llm.providers.anthropic import AnthropicProvider
from api.llm.providers.fake import FakeProvider
from api.llm.providers.openrouter import OpenRouterProvider
from api.llm.service import LLMService
from api.llm.types import LLMRequest


def build_llm_service(
    settings: Settings,
    ledger: SpendLedger,
    fake_responder: Callable[[LLMRequest], str] | None = None,
) -> LLMService:
    """Fake mode: one free fake provider. Live mode: Anthropic, falling back to OpenRouter.

    load_settings() has already guaranteed the keys exist when the mode is live.
    """
    if settings.arcana_llm_mode == "fake":
        provider = FakeProvider(fake_responder) if fake_responder else FakeProvider()
        return LLMService(provider, None, ledger)

    assert settings.anthropic_api_key and settings.openrouter_api_key
    return LLMService(
        AnthropicProvider(settings.anthropic_api_key.get_secret_value()),
        OpenRouterProvider(settings.openrouter_api_key.get_secret_value()),
        ledger,
    )
