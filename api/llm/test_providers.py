"""Provider error mapping and request shape, with no network: SDK errors are constructed locally."""

from typing import ClassVar

import httpx
import httpx2
import pytest
import respx
from anthropic import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from api.llm.providers.anthropic import AnthropicProvider
from api.llm.providers.base import ProviderFailure
from api.llm.providers.openrouter import OpenRouterProvider
from api.llm.types import LLMRequest

REQUEST = LLMRequest(prompt="hi", purpose="t", system="sys", max_tokens=50, effort="low")
HTTPX2_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class _Usage:
    input_tokens = 10
    output_tokens = 5
    cache_creation_input_tokens = None
    cache_read_input_tokens = None


class _Block:
    type = "text"
    text = "answer"


class _Message:
    model = "claude-sonnet-5-5"
    stop_reason = "end_turn"
    content: ClassVar[list[_Block]] = [_Block()]
    usage = _Usage()


class _Messages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.params: dict = {}

    async def create(self, **params):
        self.params = params
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _Client:
    def __init__(self, outcome):
        self.messages = _Messages(outcome)


def anthropic_with(outcome) -> tuple[AnthropicProvider, _Client]:
    client = _Client(outcome)
    return AnthropicProvider("k", client=client), client  # type: ignore[arg-type]


async def test_anthropic_success_maps_text_and_usage():
    provider, _ = anthropic_with(_Message())
    response = await provider.complete(REQUEST, "claude-sonnet-5-5")
    assert (response.text, response.tokens_in, response.tokens_out) == ("answer", 10, 5)


async def test_anthropic_sends_effort_only_to_models_that_accept_it_and_no_sampling():
    provider, client = anthropic_with(_Message())
    await provider.complete(REQUEST, "claude-sonnet-5-5")
    assert client.messages.params["output_config"] == {"effort": "low"}
    assert client.messages.params["system"] == "sys"
    assert "temperature" not in client.messages.params

    provider, client = anthropic_with(_Message())
    await provider.complete(REQUEST, "claude-haiku-4-5")
    assert "output_config" not in client.messages.params


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RateLimitError("x", response=httpx2.Response(429, request=HTTPX2_REQ), body=None), "rate_limit"),
        (APITimeoutError(request=HTTPX2_REQ), "timeout"),
        (APIConnectionError(request=HTTPX2_REQ), "connection"),
        (APIStatusError("x", response=httpx2.Response(503, request=HTTPX2_REQ), body=None), "status_503"),
    ],
)
async def test_anthropic_errors_become_provider_failures(error, reason):
    provider, _ = anthropic_with(error)
    with pytest.raises(ProviderFailure) as exc:
        await provider.complete(REQUEST, "claude-sonnet-5-5")
    assert exc.value.reason == reason


async def test_anthropic_refusal_is_a_provider_failure():
    message = _Message()
    message.stop_reason = "refusal"
    provider, _ = anthropic_with(message)
    with pytest.raises(ProviderFailure) as exc:
        await provider.complete(REQUEST, "claude-sonnet-5-5")
    assert exc.value.reason == "refusal"


URL = "https://openrouter.ai/api/v1/chat/completions"


@respx.mock
async def test_openrouter_success_and_reported_cost():
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "anthropic/claude-sonnet-5.5",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "cost": 0.0004},
            },
        )
    )
    response = await OpenRouterProvider("k").complete(REQUEST, "anthropic/claude-sonnet-5.5")
    assert (response.text, response.tokens_in, response.tokens_out, response.cost_usd) == (
        "ok", 7, 3, 0.0004,
    )
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer k"
    assert b'"role":"system"' in sent.content.replace(b" ", b"")


@respx.mock
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), "rate_limit"),
        (httpx.Response(402), "status_402"),
        (httpx.Response(200, json={"error": {"message": "boom"}}), "bad_response"),
        (httpx.Response(200, text="not json"), "bad_response"),
    ],
)
async def test_openrouter_failures(response, reason):
    respx.post(URL).mock(return_value=response)
    with pytest.raises(ProviderFailure) as exc:
        await OpenRouterProvider("k").complete(REQUEST, "m")
    assert exc.value.reason == reason


@respx.mock
async def test_openrouter_timeout():
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderFailure) as exc:
        await OpenRouterProvider("k").complete(REQUEST, "m")
    assert exc.value.reason == "timeout"
