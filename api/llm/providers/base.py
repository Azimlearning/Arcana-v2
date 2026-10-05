"""The provider interface. Providers translate every SDK failure into ProviderFailure."""

from __future__ import annotations

from typing import Protocol

from api.llm.types import LLMRequest, ProviderResponse, Tier


class ProviderFailure(Exception):
    """A provider could not serve the call (rate limit, timeout, outage, refusal, bad status).

    The service answers any ProviderFailure by trying the fallback. `reason` is short and safe to
    log: it never carries a key or a response body.
    """

    def __init__(self, provider: str, reason: str):
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason


class Provider(Protocol):
    name: str

    def model_for(self, tier: Tier) -> str: ...

    async def complete(self, request: LLMRequest, model: str) -> ProviderResponse: ...
