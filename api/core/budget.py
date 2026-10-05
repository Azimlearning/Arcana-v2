"""Per-turn token budget. One object is created per turn and passed down; every LLM call charges it.

A budget that runs out raises BudgetExhausted, which the turn converts to an error envelope: the
turn still terminates (constraint 4), it just ends early. The monthly money cap is separate and
lives in api/llm/ledger.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.core.errors import BudgetExhausted

DEFAULT_TURN_TOKENS = 60_000


@dataclass
class TokenBudget:
    limit: int = DEFAULT_TURN_TOKENS
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    def can_afford(self, tokens: int) -> bool:
        return self.used + tokens <= self.limit

    def charge(self, tokens: int) -> None:
        """Record spend. Raises BudgetExhausted if it takes the turn over its limit."""
        if tokens < 0:
            raise ValueError("tokens must be non-negative")
        self.used += tokens
        if self.used > self.limit:
            raise BudgetExhausted(f"Turn token budget of {self.limit} exhausted ({self.used} used).")
