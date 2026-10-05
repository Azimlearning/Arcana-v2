"""OpenRouter provider (fallback, D-08): POST {base}/chat/completions, OpenAI-style body.

Per https://openrouter.ai/docs/api-reference/overview: Bearer auth; body of model, messages,
max_tokens; response with choices[0].message.content and usage.{prompt_tokens, completion_tokens,
cost}. OpenRouter can also answer HTTP 200 with an "error" object, which is treated as a failure.
"""

from __future__ import annotations

import httpx

from api.llm.models import OPENROUTER_MODELS
from api.llm.providers.base import ProviderFailure
from api.llm.types import LLMRequest, ProviderResponse, Tier

NAME = "openrouter"
BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    name = NAME

    def __init__(
        self,
        api_key: str,
        *,
        models: dict[Tier, str] | None = None,
        client: httpx.AsyncClient | None = None,
        base_url: str = BASE_URL,
        timeout_s: float = 60.0,
    ):
        self._models = models or OPENROUTER_MODELS
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._url = f"{base_url}/chat/completions"

    def model_for(self, tier: Tier) -> str:
        return self._models[tier]

    async def complete(self, request: LLMRequest, model: str) -> ProviderResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body = {"model": model, "messages": messages, "max_tokens": request.max_tokens}

        try:
            response = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.TimeoutException as exc:
            raise ProviderFailure(NAME, "timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(NAME, "connection") from exc

        if response.status_code == 429:
            raise ProviderFailure(NAME, "rate_limit")
        if response.status_code >= 400:
            raise ProviderFailure(NAME, f"status_{response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderFailure(NAME, "bad_response") from exc
        if not isinstance(data, dict) or "error" in data or not data.get("choices"):
            raise ProviderFailure(NAME, "bad_response")

        usage = data.get("usage") or {}
        cost = usage.get("cost")
        return ProviderResponse(
            text=data["choices"][0].get("message", {}).get("content") or "",
            model=data.get("model") or model,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
        )
