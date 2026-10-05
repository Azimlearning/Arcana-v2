"""State and runtime context for one chat turn.

State is what flows between nodes (plain values). Context is what nodes are given from outside the
graph (stores, services, the turn's budget); LangGraph passes it as `runtime.context`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from api.core.budget import TokenBudget
from api.genui.generated import ErrorEnvelope, UIBlock
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult
from api.stores.doc_store import DocStore


@dataclass(frozen=True)
class Answer:
    """What the Research agent hands to the Composer: a CitedSummary PAYLOAD, not a block.
    Agents never build UIBlocks; only the Composer does (constraint 4)."""

    data: dict[str, Any]


class TurnState(TypedDict, total=False):
    question: str
    answer: Answer | None
    """None after research means retrieval or the model found no evidence to answer from."""
    error: ErrorEnvelope | None
    """Set when research failed; the Composer turns it into an error-state block."""
    block: UIBlock
    """The validated block, written only by the Composer."""


@dataclass
class TurnContext:
    docs: DocStore
    retrieve: Callable[[str], Awaitable[RetrievalResult]]
    llm: LLMService
    budget: TokenBudget
    block_id: str
