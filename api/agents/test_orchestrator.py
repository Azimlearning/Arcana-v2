"""Orchestrator routing: rules first, one model call when unsure, a safe default when that fails (P1 A4)."""

from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import create_engine

from api.agents.framework import Agent, AgentOutput, Roster
from api.agents.graph import build_turn_graph
from api.agents.orchestrator import INTENT_PLANS, ORCHESTRATOR, ROUTE_SYSTEM, classify
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.llm.types import LLMRequest

# ── the rules ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "intent", "confident"),
    [
        ("What do the papers collectively conclude about hybrid retrieval?", "compare", True),
        ("How does Dense Retrieval compare with BM25?", "compare", True),
        ("Where do the sources disagree about chunk size?", "compare", True),
        ("What is the difference between sparse and dense retrieval?", "compare", True),
        ("How is a knowledge graph related to retrieval?", "relate", True),
        ("What is the relationship between BM25 and dense retrieval?", "relate", True),  # strong beats weak
        ("Is chunk size connected to answer quality?", "relate", True),
        ("What is Reciprocal Rank Fusion and how does it combine ranked lists?", "single", True),
        ("Define BM25.", "single", True),
        ("Explain dense retrieval.", "single", True),
        ("How does BM25 score a document?", None, False),  # nothing matches
        ("Compare the papers and connect their definitions.", None, False),  # two strong intents
        ("", None, False),
    ],
)
def test_the_rules_classify_and_report_their_confidence(question: str, intent: str | None, confident: bool):
    assert classify(question) == (intent, confident)


def test_every_intent_has_a_plan_that_ends_in_research():
    assert set(INTENT_PLANS) == {"single", "compare", "relate"}
    assert all(plan[-1] == "research" for plan in INTENT_PLANS.values())  # the answering agent runs last


# ── routing in a turn ─────────────────────────────────────────────────────────


class Spy:
    """A stand-in agent that records that it ran and what intent the Orchestrator chose."""

    def __init__(self) -> None:
        self.ran: list[tuple[str, str]] = []

    def agent(self, name: str) -> Agent:
        async def run(query: str, ctx: TurnContext) -> AgentOutput:
            self.ran.append((name, ctx.intent))
            return AgentOutput({"answer": None})

        return Agent(name=cast(Any, name), run=run)


def make_ctx(tmp_path: Path, responder, spy: Spy, *, names=("research", "graph"), fail_with: str | None = None):
    provider = FakeProvider(responder, fail_with=fail_with)
    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'l.db'}"), None)
    none: Any = None
    roster = Roster([ORCHESTRATOR, *(spy.agent(n) for n in names)])
    ctx = TurnContext(
        docs=none, retrieve=none, llm=LLMService(provider, None, ledger), budget=TokenBudget(), block_id="turn-x", roster=roster
    )
    return ctx, provider


async def route(ctx: TurnContext, question: str):
    return (await build_turn_graph().ainvoke({"question": question}, context=ctx))["block"]


def says(intent: str):
    return lambda request: f'{{"intent": "{intent}"}}'


async def test_a_confident_rule_never_asks_the_model(tmp_path: Path):
    spy = Spy()
    ctx, provider = make_ctx(tmp_path, says("relate"), spy)
    await route(ctx, "How does Dense Retrieval compare with BM25?")
    assert provider.calls == []  # no routing call at all
    assert spy.ran == [("research", "compare")]
    assert ctx.results["orchestrator"].payload["routed_by"] == "rules"


async def test_an_unsure_rule_asks_the_model_exactly_once_and_follows_its_answer(tmp_path: Path):
    spy = Spy()
    ctx, provider = make_ctx(tmp_path, says("relate"), spy)
    await route(ctx, "How does BM25 score a document?")  # no rule matches
    assert [c.purpose for c in provider.calls] == ["route"]
    request: LLMRequest = provider.calls[0]
    assert request.tier == "light" and request.system == ROUTE_SYSTEM and request.prompt == "How does BM25 score a document?"
    assert spy.ran == [("graph", "relate"), ("research", "relate")]  # relate runs graph, then research
    assert ctx.results["orchestrator"].payload["routed_by"] == "model"


@pytest.mark.parametrize("reply", ["no idea", "{broken", '{"intent": "dance"}', "[]", '{"nope": 1}'])
async def test_an_unusable_routing_reply_falls_back_to_the_default_plan(tmp_path: Path, reply: str):
    spy = Spy()
    ctx, _ = make_ctx(tmp_path, lambda request: reply, spy)
    await route(ctx, "How does BM25 score a document?")
    assert spy.ran == [("research", "single")]
    assert ctx.results["orchestrator"].payload["routed_by"] == "default"
    assert ctx.results["orchestrator"].status == "ok"  # a routing hiccup does not fail the turn


async def test_a_failing_routing_call_falls_back_to_the_default_plan(tmp_path: Path):
    spy = Spy()
    ctx, _ = make_ctx(tmp_path, says("compare"), spy, fail_with="timeout")
    await route(ctx, "How does BM25 score a document?")
    assert spy.ran == [("research", "single")]
    assert ctx.results["orchestrator"].payload["routed_by"] == "default"


async def test_agents_missing_from_the_roster_are_skipped_not_fatal(tmp_path: Path):
    spy = Spy()
    ctx, _ = make_ctx(tmp_path, says("single"), spy, names=("research",))  # no graph agent yet
    await route(ctx, "How is a knowledge graph related to retrieval?")
    assert spy.ran == [("research", "relate")]
    assert ctx.results["orchestrator"].payload["plan"] == ["research"]


async def test_the_routing_call_spends_from_the_turns_budget(tmp_path: Path):
    spy = Spy()
    ctx, _ = make_ctx(tmp_path, says("single"), spy)
    await route(ctx, "How does BM25 score a document?")
    assert ctx.budget.used > 0  # the routing call is charged like any other
    assert ctx.steps[0].agent == "orchestrator" and ctx.steps[0].tokens == ctx.budget.used


async def test_every_routing_path_ends_at_the_composer(tmp_path: Path):
    for question in ("How does Dense Retrieval compare with BM25?", "How does BM25 score a document?", "Define BM25."):
        spy = Spy()
        ctx, _ = make_ctx(tmp_path, says("single"), spy)
        block = await route(ctx, question)
        assert block.meta.status == "empty"  # the spy answers nothing; the point is a block, always
