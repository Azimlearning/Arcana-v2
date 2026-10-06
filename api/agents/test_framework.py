"""The agent framework: dispatch, budgets, loop guard, failures, trace, tool schemas (P1 task A3)."""

import ast
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from api.agents.framework import (
    Agent,
    AgentOutput,
    Roster,
    ToolSpec,
    TurnLimits,
    route_to_agent,
    tool_spec,
)
from api.agents.graph import build_turn_graph
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.core.errors import ProviderUnavailable
from api.genui.generated import TurnTrace


def make_ctx(*agents: Agent, max_hops: int = 8, budget: int = 1000) -> TurnContext:
    """A context with stand-in stores: these tests exercise dispatch, which touches none of them."""
    none: Any = None
    return TurnContext(
        docs=none, retrieve=none, llm=none, budget=TokenBudget(limit=budget), block_id="turn-x",
        roster=Roster(agents), limits=TurnLimits(max_hops=max_hops),
    )


def agent(name: str, run) -> Agent:
    return Agent(name=cast(Any, name), run=run)


def spender(cost: int, payload: dict | None = None):
    async def run(query: str, ctx: TurnContext) -> AgentOutput:
        ctx.budget.charge(cost)
        return AgentOutput(payload or {"echo": query})

    return run


# ── dispatch and the trace ────────────────────────────────────────────────────


async def test_an_ok_agent_returns_its_payload_and_is_traced():
    ctx = make_ctx(agent("research", spender(40)))
    result = await route_to_agent(ctx, "research", "why?")
    assert result.status == "ok" and result.payload == {"echo": "why?"} and result.error is None
    (step,) = ctx.steps.values()
    assert (step.hop, step.agent, step.status, step.tokens, step.note) == (0, "research", "ok", 40, None)
    assert step.latencyMs >= 0 and ctx.hops_used == 1 and ctx.results["research"] is result


async def test_nested_routing_is_traced_in_dispatch_order_with_inclusive_spend():
    async def orchestrate(query: str, ctx: TurnContext) -> AgentOutput:
        ctx.budget.charge(5)
        await route_to_agent(ctx, "research", query)
        await route_to_agent(ctx, "graph", query)
        return AgentOutput()

    ctx = make_ctx(agent("orchestrator", orchestrate), agent("research", spender(30)), agent("graph", spender(20)))
    await route_to_agent(ctx, "orchestrator", "q")
    trace = ctx.trace("answered")
    assert [(s.hop, s.agent) for s in trace.steps] == [(0, "orchestrator"), (1, "research"), (2, "graph")]
    assert [s.tokens for s in trace.steps] == [55, 30, 20]  # the orchestrator's total includes both children
    assert trace.hopsUsed == 3 and trace.tokensUsed == 55  # but the turn's total counts each one once


async def test_the_trace_is_a_valid_wire_object():
    ctx = make_ctx(agent("research", spender(1)))
    await route_to_agent(ctx, "research", "q")
    assert TurnTrace.model_validate(ctx.trace("answered").model_dump()).turnId == "turn-x"


async def test_a_partial_result_passes_through():
    async def run(query: str, ctx: TurnContext) -> AgentOutput:
        return AgentOutput({"found": 1}, status="partial", note="only one document")

    ctx = make_ctx(agent("graph", run))
    result = await route_to_agent(ctx, "graph", "q")
    assert result.status == "partial" and result.note == "only one document"
    assert ctx.steps[0].status == "partial"


# ── refusals ──────────────────────────────────────────────────────────────────


async def test_the_hop_budget_refuses_further_hops_and_does_not_spend_them():
    ctx = make_ctx(agent("research", spender(1)), agent("graph", spender(1)), max_hops=2)
    await route_to_agent(ctx, "research", "q")
    await route_to_agent(ctx, "graph", "q")
    refused = await route_to_agent(ctx, "research", "again")
    assert refused.status == "refused" and refused.note == "hop budget reached"
    assert refused.error is not None and refused.error.code == "budget_exhausted"
    assert ctx.hops_used == 2  # a refusal is traced but costs no hop
    assert [s.status for s in ctx.trace("answered").steps] == ["ok", "ok", "refused"]


async def test_a_spent_budget_refuses_a_hop():
    ctx = make_ctx(agent("research", spender(10)), budget=10)
    await route_to_agent(ctx, "research", "first")  # spends exactly the budget
    refused = await route_to_agent(ctx, "research", "second")
    assert refused.status == "refused" and refused.note == "token budget reached"
    assert refused.error is not None and refused.error.code == "budget_exhausted"


async def test_an_unknown_agent_is_refused_and_traced_as_the_orchestrators_step():
    ctx = make_ctx(agent("orchestrator", spender(0)))
    result = await route_to_agent(ctx, "wizard", "q")
    assert result.status == "refused" and result.note == "unknown agent"
    assert ctx.steps[0].agent == "orchestrator" and ctx.steps[0].status == "refused"  # never an off-schema name
    assert "wizard" not in ctx.results


async def test_a_loop_is_refused_directly_and_through_an_intermediary():
    async def a_calls_a(query: str, ctx: TurnContext) -> AgentOutput:
        inner = await route_to_agent(ctx, "research", query)
        return AgentOutput({"inner": inner.status, "note": inner.note})

    ctx = make_ctx(agent("research", a_calls_a))
    result = await route_to_agent(ctx, "research", "q")
    assert result.payload == {"inner": "refused", "note": "loop refused"}

    async def a(query: str, ctx: TurnContext) -> AgentOutput:
        return AgentOutput({"via_b": (await route_to_agent(ctx, "graph", query)).payload})

    async def b(query: str, ctx: TurnContext) -> AgentOutput:
        return AgentOutput({"back_to_a": (await route_to_agent(ctx, "research", query)).note})

    ctx2 = make_ctx(agent("research", a), agent("graph", b))
    result2 = await route_to_agent(ctx2, "research", "q")
    assert result2.payload == {"via_b": {"back_to_a": "loop refused"}}
    assert ctx2.stack == []  # the call stack unwinds fully


async def test_the_same_agent_may_run_again_after_it_finished():
    ctx = make_ctx(agent("research", spender(1)))
    assert (await route_to_agent(ctx, "research", "1")).status == "ok"
    assert (await route_to_agent(ctx, "research", "2")).status == "ok"  # sequential reuse is not a loop


# ── failures ──────────────────────────────────────────────────────────────────


async def test_an_agent_raising_an_arcana_error_is_a_failed_result_with_its_envelope():
    async def run(query: str, ctx: TurnContext) -> AgentOutput:
        raise ProviderUnavailable("model down")

    ctx = make_ctx(agent("research", run))
    result = await route_to_agent(ctx, "research", "q")
    assert result.status == "failed" and result.error is not None
    assert result.error.code == "provider_unavailable" and result.error.retryable
    assert ctx.steps[0].status == "failed" and ctx.steps[0].note == "provider_unavailable"
    assert ctx.stack == []


async def test_an_unexpected_exception_is_failed_and_its_message_never_reaches_the_trace_or_envelope():
    async def run(query: str, ctx: TurnContext) -> AgentOutput:
        raise RuntimeError("secret path C:\\Users\\x\\.env")

    ctx = make_ctx(agent("research", run))
    result = await route_to_agent(ctx, "research", "q")
    assert result.status == "failed" and result.error is not None and result.error.code == "internal"
    assert ctx.steps[0].note == "internal"
    assert "secret" not in str(ctx.trace("error").model_dump()) + result.error.message


async def test_one_agent_failing_does_not_stop_the_next():
    async def boom(query: str, ctx: TurnContext) -> AgentOutput:
        raise RuntimeError("x")

    ctx = make_ctx(agent("research", boom), agent("graph", spender(1)))
    await route_to_agent(ctx, "research", "q")
    assert (await route_to_agent(ctx, "graph", "q")).status == "ok"


# ── the Composer still ends the turn ──────────────────────────────────────────


async def run_graph(ctx: TurnContext):
    return (await build_turn_graph().ainvoke({"question": "q"}, context=ctx))["block"]


async def test_a_refused_orchestrator_still_ends_at_the_composer_with_an_error_block():
    ctx = make_ctx(agent("orchestrator", spender(0)), max_hops=0)  # no hop is allowed at all
    block = await run_graph(ctx)
    assert block.meta.status == "error" and block.meta.error is not None
    assert block.meta.error.code == "budget_exhausted"


async def test_a_crashing_orchestrator_still_ends_at_the_composer():
    async def boom(query: str, ctx: TurnContext) -> AgentOutput:
        raise RuntimeError("orchestrator bug")

    block = await run_graph(make_ctx(agent("orchestrator", boom)))
    assert block.meta.status == "error" and block.meta.error is not None and block.meta.error.code == "internal"


async def test_a_turn_with_no_budget_left_ends_at_the_composer():
    block = await run_graph(make_ctx(agent("orchestrator", spender(0)), budget=0))
    assert block.meta.status == "error" and block.meta.error is not None
    assert block.meta.error.code == "budget_exhausted"


async def test_an_empty_roster_ends_at_the_composer_not_in_an_exception():
    block = await run_graph(make_ctx())
    assert block.meta.status == "error"


# ── roster and tools ──────────────────────────────────────────────────────────


def test_a_roster_rejects_a_duplicate_agent_and_lists_its_members():
    with pytest.raises(ValueError, match="twice"):
        Roster([agent("research", spender(0)), agent("research", spender(0))])
    roster = Roster([agent("research", spender(0)), agent("graph", spender(0))])
    assert roster.names() == ["research", "graph"] and roster.get("nope") is None


def test_tool_spec_derives_a_json_schema_from_the_signature():
    def find_path(a: str, b: str, hops: int = 2, kinds: list[str] | None = None, mode: Literal["short", "all"] = "short",
                  ctx: TurnContext | None = None) -> dict:
        """Find the shortest path between two entities.

        Longer explanation that must not appear in the description."""
        return {}

    spec = tool_spec(find_path)
    assert isinstance(spec, ToolSpec) and spec.name == "find_path"
    assert spec.description == "Find the shortest path between two entities."
    assert spec.input_schema == {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "string"},
            "hops": {"type": "integer"},
            "kinds": {"type": "array", "items": {"type": "string"}},
            "mode": {"enum": ["short", "all"]},
        },
        "required": ["a", "b"],  # ctx is injected by the framework, never offered to a caller
    }


# ── agents never import each other ────────────────────────────────────────────

AGENTS_DIR = Path(__file__).resolve().parent
AGENT_MODULES = {"orchestrator", "research", "graph_agent", "fact_checker"}


def imported_agent_modules(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            parts = name.split(".")
            if parts[:2] == ["api", "agents"] and len(parts) > 2 and parts[2] in AGENT_MODULES:
                found.add(parts[2])
    return found


def test_no_agent_module_imports_another_agent_module():
    for module in sorted(AGENT_MODULES):
        path = AGENTS_DIR / f"{module}.py"
        if not path.exists():
            continue  # agents arrive over P1; the rule applies to each as it lands
        assert imported_agent_modules(path) - {module} == set(), f"{module} imports another agent"


def test_only_assembly_modules_import_the_agents():
    importers = {
        p.name
        for p in AGENTS_DIR.glob("*.py")
        if not p.name.startswith("test_") and imported_agent_modules(p)
    }
    assert importers <= {"roster.py"}, importers
