"""State and runtime context for one chat turn.

State is what flows between graph nodes (plain values). Context is the turn's working set, handed to
nodes by LangGraph as `runtime.context`: stores and services, the roster, the budgets, and the record of
what each agent did (results and trace steps).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from api.agents.framework import AgentResult, Roster, TurnLimits
from api.core.budget import TokenBudget
from api.genui.catalog import ComponentRecord, Composition, component_decisions
from api.genui.generated import AgentStep, TurnOutcome, TurnTrace, UIBlock
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult
from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore


@dataclass(frozen=True)
class Answer:
    """What the Research agent hands over: a CitedSummary PAYLOAD, not a block.
    Agents never build UIBlocks; only the Composer does (constraint 4)."""

    data: dict[str, Any]


class TurnState(TypedDict, total=False):
    question: str
    block: UIBlock
    """The terminal block (the answer), validated, written only by the Composer."""
    composition: Composition
    """Every block the Composer chose, with a record per component, written only by the Composer."""


@dataclass
class TurnContext:
    # The first five fields are the original P0 shape; the rest are defaults so older callers still work.
    docs: DocStore
    retrieve: Callable[[str], Awaitable[RetrievalResult]]
    llm: LLMService
    budget: TokenBudget
    block_id: str
    roster: Roster = field(default_factory=Roster)
    graph: GraphStore | None = None
    """The knowledge graph, for the Graph agent. None when a turn is built without one."""
    limits: TurnLimits = field(default_factory=TurnLimits)
    # What happened this turn:
    results: dict[str, AgentResult] = field(default_factory=dict)
    steps: dict[int, AgentStep] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    next_step: int = 0
    hops_used: int = 0
    intent: str = "single"
    """Set by the Orchestrator; read by the agents it routes to."""
    composition: tuple[ComponentRecord, ...] = ()
    """What the Composer decided per component this turn. Set by `run_turn` once the turn is composed."""

    def trace(self, outcome: TurnOutcome) -> TurnTrace:
        steps = [self.steps[i] for i in sorted(self.steps)]
        return TurnTrace(
            turnId=self.block_id,
            steps=steps,
            hopsUsed=self.hops_used,
            tokensUsed=self.budget.used,
            outcome=outcome,
            composition=component_decisions(self.composition),
        )
