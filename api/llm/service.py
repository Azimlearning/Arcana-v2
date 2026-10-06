"""The LLM seam. Nothing else in the codebase calls a provider.

complete() tries the primary, then the fallback, on any ProviderFailure. Before each attempt it
reserves that attempt's worst-case cost against the monthly cap and checks the per-turn token
budget; a refusal there happens before the provider is invoked. Every attempt, including failed
ones, is written to the spend ledger.
"""

from __future__ import annotations

from api.core.budget import TokenBudget
from api.core.errors import BadRequest, BudgetExhausted, ProviderUnavailable
from api.core.logging import get_logger
from api.llm.ledger import SpendLedger
from api.llm.pricing import cost_usd, estimate_call_cost, estimate_input_tokens
from api.llm.providers.base import Provider, ProviderFailure
from api.llm.types import MAX_OUTPUT_TOKENS, LLMRequest, LLMResult

log = get_logger(__name__)


class LLMService:
    def __init__(self, primary: Provider, fallback: Provider | None, ledger: SpendLedger):
        self._providers = [primary] + ([fallback] if fallback is not None else [])
        self._ledger = ledger

    def remaining_usd(self) -> float | None:
        """What the monthly cap still allows (None: no cap). For up-front checks before a big job."""
        return self._ledger.remaining_usd()

    async def complete(self, request: LLMRequest, budget: TokenBudget | None = None) -> LLMResult:
        if not 1 <= request.max_tokens <= MAX_OUTPUT_TOKENS:
            raise BadRequest(f"max_tokens must be between 1 and {MAX_OUTPUT_TOKENS}.")
        if budget is not None:
            worst_case = estimate_input_tokens(request) + request.max_tokens
            if not budget.can_afford(worst_case):
                raise BudgetExhausted(
                    f"Turn token budget cannot cover this call (up to {worst_case} tokens, "
                    f"{budget.remaining} remaining). The call was not sent."
                )

        last_failure: ProviderFailure | None = None
        for index, provider in enumerate(self._providers):
            model = provider.model_for(request.tier)
            reservation = self._ledger.reserve(estimate_call_cost(provider.name, model, request))
            try:
                response = await provider.complete(request, model)
            except ProviderFailure as failure:
                self._ledger.settle(
                    reservation,
                    provider=provider.name,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    purpose=request.purpose,
                    status="failed",
                )
                log.warning("provider_failed", provider=provider.name, reason=failure.reason)
                last_failure = failure
                continue
            except BaseException:
                # Cancellation or a bug: release the reservation, then let it propagate.
                self._ledger.settle(
                    reservation,
                    provider=provider.name,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    purpose=request.purpose,
                    status="failed",
                )
                raise

            # Price by the model that was REQUESTED (an id this code chose and the table knows), never by the
            # id echoed back. A provider-reported cost is trusted only as a lower bound: a bring-your-own-key
            # route can report 0 for a call that still costs money, so book the larger of the two.
            estimated = cost_usd(provider.name, model, response.tokens_in, response.tokens_out)
            cost = estimated if response.cost_usd is None else max(response.cost_usd, estimated)
            self._ledger.settle(
                reservation,
                provider=provider.name,
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=cost,
                purpose=request.purpose,
            )
            if budget is not None:
                budget.charge(response.tokens_in + response.tokens_out)
            return LLMResult(
                text=response.text,
                provider=provider.name,
                model=response.model,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=cost,
                fell_back=index > 0,
            )

        raise ProviderUnavailable("No LLM provider could serve the request.") from last_failure
