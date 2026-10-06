"""The turn graph end to end on the ingested fixture: research -> compose, every outcome a block."""

import json

import pytest
from sqlalchemy import create_engine

from api.agents.fakes import fake_research_responder
from api.agents.framework import Roster
from api.agents.graph import build_turn_graph, run_turn
from api.agents.orchestrator import ORCHESTRATOR
from api.agents.research import RESEARCH, best_excerpt
from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.fakes import fake_llm_responder
from api.genui.catalog import Composition
from api.genui.generated import BlockEvent, DoneEvent, LayoutEvent, StreamErrorEvent
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.llm.types import LLMRequest
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever

QUESTION = "How does Dense Retrieval compare with BM25?"
GRAPH = build_turn_graph()


def retrieve_for(deps):
    async def retrieve(q: str):
        return await hybrid_retrieve(
            q,
            dense=DenseRetriever(vectors=deps.vectors, docs=deps.docs, embedder=deps.embedder),
            sparse=SparseRetriever(docs=deps.docs),
            graph=GraphRetriever(graph=deps.graph, docs=deps.docs),
        )

    return retrieve


def make_ctx(deps, tmp_path, responder=fake_llm_responder, *, provider=None, budget=None) -> TurnContext:
    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'turn.db'}"), None)
    llm = LLMService(provider or FakeProvider(responder), None, ledger)
    return TurnContext(deps.docs, retrieve_for(deps), llm, budget or TokenBudget(), "blk", roster=default_roster())


async def run(deps, tmp_path, **kw):
    state = await GRAPH.ainvoke({"question": QUESTION}, context=make_ctx(deps, tmp_path, **kw))
    return state["block"]


def error_of(block):
    assert block.meta.status == "error" and block.meta.error is not None
    return block.meta.error


async def test_a_grounded_answer_becomes_a_ready_block_with_resolvable_citations(ingested, tmp_path):
    deps, result = ingested
    block = await run(deps, tmp_path)
    assert block.meta.status == "ready" and block.meta.error is None
    assert block.data.segments and block.data.citations
    stored = deps.docs.get_chunks([c.chunkId for c in block.data.citations])
    for citation in block.data.citations:
        assert citation.chunkId in stored and citation.docId == result.doc_id
        assert citation.docTitle == "Hybrid Retrieval over Knowledge Graphs"
        assert " ".join(citation.quote.split()) in " ".join(stored[citation.chunkId].text.split())
    ids = {c.id for c in block.data.citations}
    assert all(s.citationIds and set(s.citationIds) <= ids for s in block.data.segments)


async def test_no_evidence_gives_an_empty_block_and_never_calls_the_model(ingested, tmp_path):
    deps, _ = ingested
    for doc in deps.docs.list_documents():  # an empty corpus: nothing to retrieve
        deps.docs.delete_document(doc.id)
    provider = FakeProvider(fake_llm_responder)
    block = await run(deps, tmp_path, provider=provider)
    assert block.meta.status == "empty" and block.data.segments == []
    assert provider.calls == []  # ground before generating: no evidence, no model call


async def test_the_model_saying_the_passages_do_not_answer_gives_an_empty_block(ingested, tmp_path):
    deps, _ = ingested
    block = await run(deps, tmp_path, responder=lambda r: '{"segments": []}')
    assert block.meta.status == "empty"


async def test_a_provider_failure_still_ends_at_the_composer_as_an_error_block(ingested, tmp_path):
    deps, _ = ingested
    block = await run(deps, tmp_path, provider=FakeProvider(fail_with="timeout"))
    error = error_of(block)
    assert error.code == "provider_unavailable" and error.retryable
    assert block.data.segments == [] and block.data.citations == []


async def test_an_exhausted_turn_budget_ends_as_an_error_block(ingested, tmp_path):
    deps, _ = ingested
    block = await run(deps, tmp_path, budget=TokenBudget(limit=10))
    assert error_of(block).code == "budget_exhausted"


@pytest.mark.parametrize("reply", ["I cannot do that.", "{broken", '{"segments": "nope"}', "[1,2,3]"])
async def test_an_unusable_model_reply_is_an_error_block_not_a_crash(ingested, tmp_path, reply):
    deps, _ = ingested
    block = await run(deps, tmp_path, responder=lambda r: reply)
    error = error_of(block)
    assert error.code == "provider_unavailable" and error.retryable  # a model fault, not bad input


async def test_a_segment_citing_nothing_real_is_dropped_never_shown(ingested, tmp_path):
    deps, _ = ingested
    reply = json.dumps(
        {
            "segments": [
                {"text": "Uncited claim.", "cites": []},
                {"text": "Cites a passage that was never shown.", "cites": [99, 0, True, "1"]},
                {"text": "Properly cited.", "cites": [1]},
            ]
        }
    )
    # Research drops the two ungrounded segments, so the survivor is segment 1 of the answer the checker sees.
    approve = '{"verdicts": [{"segment": 1, "supported": true}]}'  # this test is about citations, not support
    block = await run(deps, tmp_path, responder=lambda r: reply if r.purpose == "research" else approve)
    assert block.meta.status == "ready"
    assert [s.text for s in block.data.segments] == ["Properly cited."]


async def test_an_answer_with_no_grounded_segment_is_an_error_not_an_ungrounded_answer(ingested, tmp_path):
    deps, _ = ingested
    reply = json.dumps({"segments": [{"text": "Confident but uncited.", "cites": [42]}]})
    block = await run(deps, tmp_path, responder=lambda r: reply)
    assert "grounded" in error_of(block).message


async def test_a_quote_invented_by_the_model_is_ignored(ingested, tmp_path):
    deps, _ = ingested
    reply = json.dumps({"segments": [{"text": "x", "cites": [1], "quote": "INVENTED QUOTE"}]})
    approve = '{"verdicts": [{"segment": 1, "supported": true}]}'
    block = await run(deps, tmp_path, responder=lambda r: reply if r.purpose == "research" else approve)
    assert block.meta.status == "ready"
    assert all("INVENTED" not in c.quote for c in block.data.citations)


async def test_the_composer_replaces_a_block_the_validator_rejects_with_an_error_block(ingested, tmp_path):
    deps, _ = ingested
    real_retrieve = retrieve_for(deps)

    async def retrieve_then_lose_the_chunks(q: str):
        result = await real_retrieve(q)
        for doc in deps.docs.list_documents():  # the evidence disappears before the answer is composed
            deps.docs.delete_document(doc.id)
        return result

    ctx = make_ctx(deps, tmp_path)
    ctx.roster = Roster([ORCHESTRATOR, RESEARCH])  # no Fact Checker: this exercises the validator backstop alone
    ctx.retrieve = retrieve_then_lose_the_chunks
    block = (await GRAPH.ainvoke({"question": QUESTION}, context=ctx))["block"]
    error = error_of(block)
    assert error.code == "validation_failed"
    assert any(i.path.endswith(".chunkId") for i in error.issues)


async def test_run_turn_streams_loading_then_the_final_block_with_the_same_id_then_done(ingested, tmp_path):
    deps, _ = ingested
    events = [e async for e in run_turn(GRAPH, QUESTION, make_ctx(deps, tmp_path))]
    assert [type(e) for e in events] == [BlockEvent, BlockEvent, BlockEvent, LayoutEvent, DoneEvent]
    first, second, third = events[0], events[1], events[2]
    assert isinstance(first, BlockEvent) and isinstance(second, BlockEvent) and isinstance(third, BlockEvent)
    assert first.block.meta.status == "loading" and second.block.meta.status == "ready"
    assert first.block.id == second.block.id == "blk"  # same id: the second replaces the first
    assert third.block.type == "SourceList" and third.block.id != "blk"  # the source list is its own block


async def test_a_failure_of_the_graph_itself_is_a_stream_error_event(ingested, tmp_path):
    deps, _ = ingested

    class Exploding:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")

    events = [e async for e in run_turn(Exploding(), QUESTION, make_ctx(deps, tmp_path))]
    # loading, then an error block with the SAME id (so nothing stays loading), then the error, then done
    assert [type(e) for e in events] == [BlockEvent, BlockEvent, StreamErrorEvent, DoneEvent]
    loading, resolved = events[0], events[1]
    assert isinstance(loading, BlockEvent) and isinstance(resolved, BlockEvent)
    assert loading.block.meta.status == "loading" and resolved.block.meta.status == "error"
    assert loading.block.id == resolved.block.id == "blk"
    err = events[2].error  # pyright: ignore[reportAttributeAccessIssue]
    assert err.code == "internal" and "secret" not in err.message
    assert resolved.block.meta.error == err


def test_best_excerpt_is_a_verbatim_sentence_close_to_the_segment():
    text = "Alpha is first.   Louvain finds communities in graphs. Omega is last."
    assert best_excerpt(text, "communities found by Louvain") == "Louvain finds communities in graphs."
    long = "word " * 200
    excerpt = best_excerpt(long, "word")
    assert len(excerpt) <= 240 and " ".join(long.split()).startswith(excerpt)


def test_the_fake_research_responder_cites_the_leading_passages():
    prompt = "Question: q\n\nPassages:\n[1] (T, p.1)\nFirst sentence. More.\n\n[2] (T, p.2)\nSecond one.\n"
    out = json.loads(fake_research_responder(LLMRequest(prompt=prompt, purpose="research")))
    assert [s["cites"] for s in out["segments"]] == [[1], [2]]


def test_the_fake_research_responder_cites_the_first_passage_of_each_document():
    prompt = (
        "Question: q\n\nPassages:\n[1] (Paper A, p.1)\nA one. More.\n\n[2] (Paper A, p.2)\nA two.\n\n"
        "[3] (Paper B (extended), p.9)\nB one.\n"
    )
    out = json.loads(fake_research_responder(LLMRequest(prompt=prompt, purpose="research")))
    assert [s["cites"] for s in out["segments"]] == [[1], [3]]  # one per document, even with ")" in a title


async def test_a_block_built_around_the_validator_is_never_streamed(ingested, tmp_path):
    """Fail closed by structure: whatever the graph hands back is re-validated before it can leave."""
    from api.genui.generated import (
        BlockMeta,
        CitedSummary,
        CitedSummaryData,
        SummarySegment,
    )

    deps, _ = ingested
    # model_construct skips validation entirely: a "ready" block citing an id that does not exist.
    sneaky = CitedSummary.model_construct(
        type="CitedSummary",
        id="blk",
        meta=BlockMeta.model_construct(status="ready", error=None),
        data=CitedSummaryData.model_construct(
            segments=[SummarySegment.model_construct(text="Unsupported claim.", citationIds=["zz"])],
            citations=[],
        ),
    )

    class Sneaky:
        async def ainvoke(self, *args, **kwargs):
            return {"block": sneaky, "composition": Composition((sneaky,))}

    events = [e async for e in run_turn(Sneaky(), QUESTION, make_ctx(deps, tmp_path))]
    streamed = [e.block for e in events if isinstance(e, BlockEvent)]
    assert all(b.meta.status != "ready" for b in streamed)  # the unsupported claim never left
    assert streamed[-1].meta.status == "error" and streamed[-1].meta.error.code == "validation_failed"  # pyright: ignore[reportOptionalMemberAccess]
    assert any(i.path == "data.segments.0.citationIds.0" for i in streamed[-1].meta.error.issues)  # pyright: ignore[reportOptionalMemberAccess]
    assert isinstance(events[-2], StreamErrorEvent) and isinstance(events[-1], DoneEvent)


def test_only_the_composer_may_build_blocks():
    """Constraint 4: no other production module imports the block builders, so only the Composer makes blocks."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if not p.name.startswith("test_")  # tests may build raw dicts to probe the validator
        and "api.genui.builders" in p.read_text(encoding="utf-8")
        and p.name not in {"compose.py", "builders.py", "templates.py"}
    ]
    assert offenders == []
