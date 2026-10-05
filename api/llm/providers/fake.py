"""A deterministic provider for tests and ARCANA_LLM_MODE=fake. Spends nothing.

`responder` maps a request to the reply text, so each caller (extraction, research) can supply a
purpose-specific fake. `name` and `models` can be set to make the fake price like a real provider,
which is how the cap tests exercise non-zero costs.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from api.llm.models import ANTHROPIC_MODELS
from api.llm.providers.base import ProviderFailure
from api.llm.types import LLMRequest, ProviderResponse, Tier


def _echo(request: LLMRequest) -> str:
    return f"[fake:{request.purpose}] {request.prompt[:80]}"


class FakeProvider:
    def __init__(
        self,
        responder: Callable[[LLMRequest], str] = _echo,
        *,
        name: str = "fake",
        models: dict[Tier, str] | None = None,
        fail_with: str | None = None,
    ):
        self.name = name
        self._responder = responder
        self._models = models or ANTHROPIC_MODELS
        self._fail_with = fail_with
        self.calls: list[LLMRequest] = []

    def model_for(self, tier: Tier) -> str:
        return self._models[tier]

    async def complete(self, request: LLMRequest, model: str) -> ProviderResponse:
        self.calls.append(request)
        if self._fail_with is not None:
            raise ProviderFailure(self.name, self._fail_with)
        text = self._responder(request)
        chars_in = len(request.prompt) + len(request.system or "")
        return ProviderResponse(
            text=text,
            model=model,
            tokens_in=math.ceil(chars_in / 4),
            tokens_out=math.ceil(len(text) / 4),
        )
