"""Anthropic Messages API provider (primary, D-08).

Written against the anthropic 1.x SDK. Model-specific rules honoured here:
  - Opus 5.5 and Sonnet 5.5 think by default and reject non-default sampling parameters, so no
    temperature or top_p is ever sent; `effort` is the only depth control.
  - Haiku 4.5 rejects `effort`, so it is sent only to the models that accept it.
  - Responses can end in stop_reason "refusal"; that is a ProviderFailure, so the fallback runs.
"""

from __future__ import annotations

import anthropic

from api.core.logging import get_logger
from api.llm.models import ANTHROPIC_MODELS
from api.llm.providers.base import ProviderFailure
from api.llm.types import LLMRequest, ProviderResponse, Tier

log = get_logger(__name__)

NAME = "anthropic"
EFFORT_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})


class AnthropicProvider:
    name = NAME

    def __init__(
        self,
        api_key: str,
        *,
        models: dict[Tier, str] | None = None,
        client: anthropic.AsyncAnthropic | None = None,
        timeout_s: float = 60.0,
    ):
        self._models = models or ANTHROPIC_MODELS
        # No SDK retries: a retry is a second billed request under ONE ledger row (the reservation covers
        # one), and the fallback provider is the intended recovery. A failure is settled and falls back.
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout_s, max_retries=0
        )

    def model_for(self, tier: Tier) -> str:
        return self._models[tier]

    async def complete(self, request: LLMRequest, model: str) -> ProviderResponse:
        params: dict = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            params["system"] = request.system
        if request.effort and model in EFFORT_MODELS:
            params["output_config"] = {"effort": request.effort}

        try:
            message = await self._client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise ProviderFailure(NAME, "rate_limit") from exc
        except anthropic.APITimeoutError as exc:  # subclass of APIConnectionError: keep it first
            raise ProviderFailure(NAME, "timeout") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderFailure(NAME, "connection") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderFailure(NAME, f"status_{exc.status_code}") from exc

        if message.stop_reason == "refusal":
            raise ProviderFailure(NAME, "refusal")

        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        tokens_in = (
            usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0)
        )
        return ProviderResponse(
            text=text, model=message.model, tokens_in=tokens_in, tokens_out=usage.output_tokens
        )
