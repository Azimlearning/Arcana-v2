"""The Fact Checker: quotes verbatim, claims supported, and nothing unchecked ever shown (P1 A7)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine

from api.agents.compose import compose_block
from api.agents.fact_checker import (
    FACT_CHECKER,
    JUDGE_TIER,
    SUPPORT_OVERLAP,
    CheckOutcome,
    lexical_support,
    parse_verdicts,
    screen_answer,
)
from api.agents.framework import Agent, AgentOutput, Roster, route_to_agent
from api.agents.state import Answer, TurnContext
from api.core.budget import TokenBudget
from api.genui.generated import CitedSummary
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService

DENSE = "Dense retrieval embeds queries and passages into one vector space. It ranks by cosine similarity."
SPARSE = "BM25 scores documents by term frequency and inverse document frequency. It needs no training."
CHUNKS = {
    "k1": SimpleNamespace(id="k1", doc_id="d1", text=DENSE),
    "k2": SimpleNamespace(id="k2", doc_id="d2", text=SPARSE),
}
CLAIM_1 = "Dense retrieval embeds queries and passages into a shared vector space."
CLAIM_2 = "BM25 scores documents using term frequency and inverse document frequency."


def data_of(outcome: CheckOutcome) -> dict[str, Any]:
    assert outcome.data is not None
    return outcome.data


def error_of(block: Any):
    assert block.meta.error is not None
    return block.meta.error


def cite(cid: str, chunk: str, quote: str, doc: str | None = None) -> dict[str, Any]:
    doc_id = doc or CHUNKS[chunk].doc_id
    return {"id": cid, "chunkId": chunk, "docId": doc_id, "docTitle": "T", "page": 1, "quote": quote}


def good_answer() -> dict[str, Any]:
    return {
        "segments": [
            {"text": CLAIM_1, "citationIds": ["c1"]},
            {"text": CLAIM_2, "citationIds": ["c2"]},
        ],
        "citations": [
            cite("c1", "k1", "It ranks by cosine similarity."),
            cite("c2", "k2", "It needs no training."),
        ],
    }


# ── the quote check (deterministic) ───────────────────────────────────────────


def test_a_clean_answer_passes_both_checks_unchanged():
    outcome = screen_answer(good_answer(), CHUNKS).finalize()
    assert outcome.data == good_answer() and outcome.removed == 0 and outcome.citations_dropped == 0


def test_a_non_verbatim_quote_drops_its_citation_and_the_segment_that_only_it_supported():
    answer = good_answer()
    answer["citations"][0]["quote"] = "It always ranks by cosine similarity."  # one word added
    outcome = screen_answer(answer, CHUNKS).finalize()
    assert outcome.citations_dropped == 1
    assert [s["text"] for s in data_of(outcome)["segments"]] == [CLAIM_2]
    assert [c["id"] for c in data_of(outcome)["citations"]] == ["c2"]  # no orphan citation left behind


def test_a_citation_pointing_at_the_wrong_chunk_is_dropped():
    answer = good_answer()
    answer["citations"][0]["chunkId"] = "k2"  # the quote is from k1, the citation says k2
    outcome = screen_answer(answer, CHUNKS).finalize()
    assert outcome.citations_dropped == 1 and outcome.segments_kept == 1


def test_a_citation_naming_the_wrong_document_is_dropped():
    answer = good_answer()
    answer["citations"][0]["docId"] = "d2"
    assert screen_answer(answer, CHUNKS).finalize().citations_dropped == 1


def test_a_citation_to_a_chunk_that_no_longer_exists_is_dropped():
    answer = good_answer()
    answer["citations"][1]["chunkId"] = "gone"
    outcome = screen_answer(answer, CHUNKS).finalize()
    assert outcome.citations_dropped == 1 and outcome.segments_kept == 1


def test_a_trivial_quote_is_dropped():
    answer = good_answer()
    answer["citations"][0]["quote"] = "It"  # a verbatim span, but not evidence
    assert screen_answer(answer, CHUNKS).finalize().citations_dropped == 1


def test_a_segment_keeps_going_while_one_of_its_citations_survives():
    answer = good_answer()
    answer["segments"][0]["citationIds"] = ["c1", "c2"]
    answer["citations"][1]["quote"] = "invented"
    outcome = screen_answer(answer, CHUNKS).finalize({0: True})
    assert data_of(outcome)["segments"][0]["citationIds"] == ["c1"]


def test_malformed_input_fails_rather_than_passing():
    for data in ({}, {"segments": "x", "citations": None}, {"segments": [None, 3], "citations": [None, {}]}):
        assert screen_answer(data, CHUNKS).finalize().data is None


# ── the support check ─────────────────────────────────────────────────────────


def test_lexical_support_separates_a_paraphrase_from_an_invented_claim():
    assert lexical_support(CLAIM_1, [DENSE]) >= SUPPORT_OVERLAP
    assert lexical_support("Dense retrieval always beats every other method on every benchmark.", [DENSE]) < SUPPORT_OVERLAP
    assert lexical_support("", [DENSE]) == 0.0


def test_a_judge_verdict_is_decisive_in_both_directions():
    screened = screen_answer(good_answer(), CHUNKS)
    rejected = screened.finalize({0: False, 1: True})  # the claim matches its evidence but the judge says no
    assert [s["text"] for s in data_of(rejected)["segments"]] == [CLAIM_2] and rejected.by_model == 2
    answer = good_answer()
    answer["segments"][0]["text"] = "Something unrelated to the passage entirely."
    accepted = screen_answer(answer, CHUNKS).finalize({0: True, 1: True})
    assert accepted.segments_kept == 2  # the lexical rule never overrules a verdict


def test_a_segment_without_a_verdict_falls_to_the_lexical_rule():
    answer = good_answer()
    answer["segments"][1]["text"] = "Quantum entanglement permits faster than light messaging."
    outcome = screen_answer(answer, CHUNKS).finalize({0: True})  # no verdict for segment 2
    assert outcome.segments_kept == 1 and outcome.by_model == 1 and outcome.by_lexical == 1


def test_only_real_booleans_for_asked_segments_count_as_verdicts():
    screened = screen_answer(good_answer(), CHUNKS)
    reply = (
        '{"verdicts": [{"segment": 1, "supported": "yes"}, {"segment": 2, "supported": true},'
        ' {"segment": 9, "supported": true}, {"segment": true, "supported": true}, 5]}'
    )
    assert parse_verdicts(reply, screened.candidates) == {1: True}


# ── the agent ─────────────────────────────────────────────────────────────────


def make_ctx(tmp_path: Path, answer: dict[str, Any] | None, responder=lambda r: "{}", *, fail_with: str | None = None):
    docs: Any = SimpleNamespace(get_chunks=lambda ids: {i: CHUNKS[i] for i in ids if i in CHUNKS})
    provider = FakeProvider(responder, fail_with=fail_with)
    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'f.db'}"), None)
    none: Any = None

    async def research(query: str, ctx: TurnContext) -> AgentOutput:
        return AgentOutput({"answer": Answer(answer) if answer is not None else None})

    roster = Roster([Agent(name="research", run=research), FACT_CHECKER])
    ctx = TurnContext(docs, none, LLMService(provider, None, ledger), TokenBudget(), "blk", roster=roster)
    return ctx, provider


async def check(ctx: TurnContext):
    await route_to_agent(ctx, "research", "q")
    return await route_to_agent(ctx, "fact_checker", "q")


async def test_the_judge_runs_once_on_a_different_tier_and_sees_the_evidence(tmp_path: Path):
    ctx, provider = make_ctx(tmp_path, good_answer(), lambda r: '{"verdicts": [{"segment": 1, "supported": true}, {"segment": 2, "supported": true}]}')
    result = await check(ctx)
    assert result.status == "ok" and result.payload["report"]["judged_by_model"] == 2
    assert len(provider.calls) == 1 and provider.calls[0].purpose == "check"
    assert provider.calls[0].tier == JUDGE_TIER and JUDGE_TIER != "standard"  # the generator's tier
    assert DENSE in provider.calls[0].prompt and CLAIM_2 in provider.calls[0].prompt


async def test_a_failing_judge_falls_back_to_the_lexical_rule_and_still_checks(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, good_answer(), fail_with="timeout")
    result = await check(ctx)
    assert result.status == "ok" and result.payload["report"]["judged_by_lexical"] == 2


async def test_an_unusable_judge_reply_falls_back_too(tmp_path: Path):
    for reply in ("not json", "[]", '{"verdicts": "no"}', "{}"):
        ctx, _ = make_ctx(tmp_path, good_answer(), lambda r, reply=reply: reply)
        result = await check(ctx)
        assert result.status == "ok" and result.payload["report"]["judged_by_lexical"] == 2


async def test_an_unsupported_claim_is_removed_and_the_step_says_so(tmp_path: Path):
    answer = good_answer()
    answer["segments"][1]["text"] = "BM25 outperforms every neural model on all benchmarks without exception."
    ctx, _ = make_ctx(tmp_path, answer)
    result = await check(ctx)
    assert result.status == "partial" and result.note == "removed 1 of 2 segments"
    assert [s["text"] for s in result.payload["answer"].data["segments"]] == [CLAIM_1]


async def test_nothing_surviving_is_no_answer_and_the_composer_renders_an_empty_block(tmp_path: Path):
    answer = good_answer()
    for segment in answer["segments"]:
        segment["text"] = "Completely invented statement about unrelated astronomy topics."
    ctx, _ = make_ctx(tmp_path, answer)
    result = await check(ctx)
    assert result.status == "partial" and result.note == "no supported claims"
    assert result.payload["answer"] is None
    assert compose_block(ctx).meta.status == "empty"


async def test_there_is_nothing_to_check_when_research_found_no_answer(tmp_path: Path):
    ctx, provider = make_ctx(tmp_path, None)
    result = await check(ctx)
    assert result.status == "ok" and result.payload["answer"] is None
    assert provider.calls == []  # no answer, no judge call, no spend


# ── fail closed ───────────────────────────────────────────────────────────────


def raising_checker() -> Agent:
    async def run(query: str, ctx: TurnContext) -> AgentOutput:
        raise RuntimeError("checker exploded")

    return Agent(name="fact_checker", run=run)


async def test_a_checker_that_raises_never_lets_the_unchecked_answer_through(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, good_answer())
    ctx.roster = Roster([ctx.roster.get("research"), raising_checker()])  # type: ignore[list-item]
    result = await check(ctx)
    assert result.status == "failed" and result.payload == {}
    block = compose_block(ctx)
    assert isinstance(block, CitedSummary)
    assert block.meta.status == "error" and block.data.segments == [] and block.data.citations == []


async def test_a_refused_checker_hop_is_an_error_block_not_an_unchecked_answer(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, good_answer())
    ctx.limits.max_hops = 1  # research uses the only hop; the checker is refused
    result = await check(ctx)
    assert result.status == "refused"
    block = compose_block(ctx)
    assert block.meta.status == "error" and error_of(block).code == "budget_exhausted"


async def test_a_checker_that_never_ran_is_an_error_block(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, good_answer())
    await route_to_agent(ctx, "research", "q")  # the plan stopped before the checker
    block = compose_block(ctx)
    assert block.meta.status == "error" and "checked" in error_of(block).message


async def test_without_a_checker_on_the_roster_the_answer_is_not_gated(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, None)
    ctx.roster = Roster([ctx.roster.get("research")])  # type: ignore[list-item]
    await route_to_agent(ctx, "research", "q")
    assert compose_block(ctx).meta.status == "empty"  # a roster without the checker behaves as in P0


def test_the_checkers_tool_has_no_caller_chosen_inputs():
    assert [t.name for t in FACT_CHECKER.tools] == ["check_claims"]
    assert FACT_CHECKER.tools[0].input_schema["properties"] == {}
