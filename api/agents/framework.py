# Adapted in part from Azimlearning/Arcana (v1), api/agents/base.py @ 9a3d67f. Read in full. Kept: the
# route_to_agent idea (charge a hop before dispatch, return a "partial" result when the budget is
# spent) and the JSON schema derived from a function signature. Not ported: the process-wide global
# registry (v2 passes an explicit Roster, D-22), and the Pydantic AgentState (v2 keeps a turn context).
"""The agent framework: how agents are dispatched, budgeted and traced (D-22).

    - A `Roster` is an explicit object. There is no global registry.
    - `route_to_agent` is the ONLY way one agent runs another: it refuses an unknown agent, a hop back
      to an agent already on the call stack (a loop), and any hop once the hop or token budget is
      spent; it times and records a trace step for every dispatch, including the refused ones.
    - An agent never imports another agent. It asks the framework to run one by name.
    - Nothing in here can stop a turn from reaching the Composer: an agent that raises, or a hop that is
      refused, becomes a `failed` or `refused` result, never an exception that escapes the turn.

Trace notes carry a short reason code, never an exception message.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, get_args, get_origin

from api.core.errors import ArcanaError, envelope_from_exception
from api.core.logging import get_logger
from api.genui.generated import AgentName, AgentStep, ErrorCode, ErrorEnvelope, StepStatus

if TYPE_CHECKING:
    from api.agents.state import TurnContext

log = get_logger(__name__)

DEFAULT_MAX_HOPS = 8


# ── tools ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolSpec:
    """A typed tool an agent offers: a name, a one-line description, and a JSON schema for its inputs."""

    name: str
    description: str
    input_schema: dict[str, Any]


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is None:
        return {}
    simple = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if annotation in simple:
        return {"type": simple[annotation]}
    origin = get_origin(annotation)
    if origin in (list, tuple):
        args = get_args(annotation)
        return {"type": "array", "items": _annotation_schema(args[0]) if args else {}}
    if origin is Literal:
        return {"enum": list(get_args(annotation))}
    args = [a for a in get_args(annotation) if a is not type(None)]  # T | None
    return _annotation_schema(args[0]) if len(args) == 1 else {}


def tool_spec(fn: Callable[..., Any]) -> ToolSpec:
    """Derive a ToolSpec from a function's name, first docstring line and annotated parameters."""
    hints = inspect.get_annotations(fn, eval_str=True)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        if name in {"self", "cls", "ctx"}:  # the turn context is injected, never chosen by a caller
            continue
        properties[name] = _annotation_schema(hints.get(name, inspect.Parameter.empty))
        if param.default is inspect.Parameter.empty:
            required.append(name)
    summary = (fn.__doc__ or "").strip().split("\n", 1)[0]
    return ToolSpec(fn.__name__, summary, {"type": "object", "properties": properties, "required": required})


# ── agents and the roster ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentOutput:
    """What an agent's `run` returns. `partial` means usable but incomplete."""

    payload: dict[str, Any] = field(default_factory=dict)
    status: Literal["ok", "partial"] = "ok"
    note: str | None = None


@dataclass(frozen=True)
class AgentResult:
    """What `route_to_agent` returns: the agent's output, or why there is none."""

    agent: AgentName
    status: StepStatus
    payload: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    error: ErrorEnvelope | None = None
    """Set when status is failed or refused. The Composer turns it into an error block."""


AgentRun = Callable[[str, "TurnContext"], Awaitable[AgentOutput]]


@dataclass(frozen=True)
class Agent:
    name: AgentName
    run: AgentRun
    tools: tuple[ToolSpec, ...] = ()


class Roster:
    """The agents available to a turn. Explicit and immutable once built."""

    def __init__(self, agents: Iterable[Agent] = ()):
        self._agents: dict[str, Agent] = {}
        for agent in agents:
            if agent.name in self._agents:
                raise ValueError(f"agent {agent.name!r} is registered twice")
            self._agents[agent.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def names(self) -> list[str]:
        return list(self._agents)

    def tools_for(self, name: str) -> tuple[ToolSpec, ...]:
        agent = self._agents.get(name)
        return agent.tools if agent else ()


@dataclass
class TurnLimits:
    max_hops: int = DEFAULT_MAX_HOPS


# ── dispatch ──────────────────────────────────────────────────────────────────


def _refusal(code: ErrorCode, message: str) -> ErrorEnvelope:
    return ErrorEnvelope(code=code, message=message, issues=[], retryable=False)


def _record(ctx: TurnContext, index: int, step: AgentStep) -> None:
    ctx.steps[index] = step


async def route_to_agent(ctx: TurnContext, name: str, query: str) -> AgentResult:
    """Run the named agent for this turn, within the turn's budgets. Never raises."""
    index = ctx.next_step
    ctx.next_step += 1
    agent_name: AgentName = name  # type: ignore[assignment]  # validated against the roster below

    def refuse(reason: str, error: ErrorEnvelope, note: str) -> AgentResult:
        log.warning("hop_refused", agent=name, reason=reason, hops_used=ctx.hops_used)
        # An unknown name cannot be put on the wire as an agent; record it as the orchestrator's step.
        traced: AgentName = agent_name if ctx.roster.get(name) else "orchestrator"
        _record(ctx, index, AgentStep(hop=index, agent=traced, status="refused", tokens=0, latencyMs=0, note=note))
        result = AgentResult(agent=traced, status="refused", note=note, error=error)
        if ctx.roster.get(name) and name not in ctx.results:
            ctx.results[traced] = result  # visible to the Composer; never overwrites a real result
        return result

    agent = ctx.roster.get(name)
    if agent is None:
        return refuse("unknown_agent", _refusal("internal", "No such agent."), "unknown agent")
    if name in ctx.stack:
        return refuse("loop", _refusal("internal", "An agent cannot be routed back to while it is running."), "loop refused")
    if ctx.hops_used >= ctx.limits.max_hops:
        return refuse("hop_budget", _refusal("budget_exhausted", "The turn used its hop budget."), "hop budget reached")
    if ctx.budget.remaining <= 0:
        return refuse("token_budget", _refusal("budget_exhausted", "The turn used its token budget."), "token budget reached")

    ctx.hops_used += 1
    ctx.stack.append(name)
    tokens_before = ctx.budget.used
    started = time.perf_counter()
    status: StepStatus = "ok"
    note: str | None = None
    error: ErrorEnvelope | None = None
    payload: dict[str, Any] = {}
    try:
        output = await agent.run(query, ctx)
        payload, status, note = output.payload, output.status, output.note
    except Exception as exc:  # an agent's failure is a result, not an escape from the turn
        status, error = "failed", envelope_from_exception(exc)
        note = exc.code if isinstance(exc, ArcanaError) else "internal"
        log.warning("agent_failed", agent=name, error=type(exc).__name__)
    finally:
        ctx.stack.pop()
        _record(
            ctx,
            index,
            AgentStep(
                hop=index,
                agent=agent.name,
                status=status,
                tokens=ctx.budget.used - tokens_before,  # includes any agent this one routed to
                latencyMs=round((time.perf_counter() - started) * 1000),
                note=note,
            ),
        )
    result = AgentResult(agent=agent.name, status=status, payload=payload, note=note, error=error)
    ctx.results[agent.name] = result
    return result
