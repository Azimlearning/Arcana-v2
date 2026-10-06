"""Research super tools: balanced cross-document evidence and server-verified quotes (P1 A5)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine

from api.agents.research import _run, compare_documents, research, retrieve_evidence, verified_quote
from api.agents.state import TurnContext
from api.core.budget import TokenBudget
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult, RetrievedChunk

TITLES = {"d1": "Paper One", "d2": "Paper Two"}
TEXTS = {
    "a1": "Dense retrieval embeds queries and passages into one vector space. It ranks by cosine similarity.",
    "a2": "Dense retrieval struggles with rare terms. Exact keywords are often missed by embeddings.",
    "a3": "A third passage from the first paper about index size and memory use in large collections.",
    "b1": "BM25 scores documents by term frequency and inverse document frequency. It needs no training.",
    "b2": "Sparse methods are strong on rare terms. They miss paraphrases that share no vocabulary.",
}
DOC_OF = {"a1": "d1", "a2": "d1", "a3": "d1", "b1": "d2", "b2": "d2"}


def chunk(cid: str) -> RetrievedChunk:
    return RetrievedChunk(cid, DOC_OF[cid], TEXTS[cid], 1, 1.0, ("dense",))


def make_ctx(tmp_path: Path, reply: str, *, fused: list[str], deeper: list[str] | None = None, intent="single"):
    result = RetrievalResult(
        chunks=[chunk(c) for c in fused],
        per_signal={"dense": [chunk(c) for c in fused + (deeper or [])]},  # type: ignore[dict-item]
    )

    async def retrieve(q: str) -> RetrievalResult:
        return result

    docs: Any = SimpleNamespace(get_document=lambda d: SimpleNamespace(title=TITLES[d]))
    provider = FakeProvider(lambda request: reply)
    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'r.db'}"), None)
    ctx = TurnContext(docs, retrieve, LLMService(provider, None, ledger), TokenBudget(), "blk")
    ctx.intent = intent
    return ctx, provider


def reply_of(*segments: tuple[str, list[Any]]) -> str:
    return json.dumps({"segments": [{"text": t, "cites": c} for t, c in segments]})


# ── the tools ─────────────────────────────────────────────────────────────────


async def test_retrieve_evidence_returns_the_fused_ranking(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, "{}", fused=["a1", "b1", "a2"])
    assert [c.id for c in await retrieve_evidence("q", ctx)] == ["a1", "b1", "a2"]


async def test_compare_documents_balances_papers_and_reaches_past_the_fused_top(tmp_path: Path):
    # The fused ranking is all paper one; paper two only appears deeper in a signal's own ranking.
    ctx, _ = make_ctx(tmp_path, "{}", fused=["a1", "a2", "a3"], deeper=["b1", "b2"])
    picked = [c.id for c in await compare_documents("q", ctx)]
    assert picked == ["a1", "b1", "a2", "b2"]  # every paper's best first, at most two each
    assert "a3" not in picked


# ── cross-document answers ────────────────────────────────────────────────────


async def test_a_comparison_cites_both_papers(tmp_path: Path):
    reply = reply_of(
        ("Paper One embeds text.", [{"passage": 1, "quote": "It ranks by cosine similarity."}]),
        ("Paper Two counts terms.", [{"passage": 3, "quote": "It needs no training."}]),
    )
    # Prompt order is grouped by document: [1] a1, [2] a2, [3] b1, [4] b2.
    ctx, _ = make_ctx(tmp_path, reply, fused=["a1", "a2", "a3"], deeper=["b1", "b2"], intent="compare")
    out = await _run("compare them", ctx)
    assert out.status == "ok" and out.note is None
    answer = out.payload["answer"]
    assert {c["docId"] for c in answer.data["citations"]} == {"d1", "d2"}
    assert {c["docTitle"] for c in answer.data["citations"]} == {"Paper One", "Paper Two"}


async def test_a_comparison_citing_one_paper_is_partial_with_a_note(tmp_path: Path):
    reply = reply_of(("Only paper one.", [1]))
    ctx, _ = make_ctx(tmp_path, reply, fused=["a1", "a2"], deeper=["b1"], intent="compare")
    out = await _run("compare them", ctx)
    assert out.status == "partial" and out.note == "comparison cites one document"
    assert out.payload["answer"] is not None  # usable, just flagged


async def test_a_single_document_corpus_is_not_penalised_for_citing_one_paper(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, reply_of(("Only paper one.", [1])), fused=["a1", "a2"], intent="compare")
    out = await _run("compare them", ctx)
    assert out.status == "ok"


async def test_the_prompt_groups_passages_by_document_for_a_comparison(tmp_path: Path):
    ctx, provider = make_ctx(tmp_path, '{"segments": []}', fused=["a1", "b1", "a2"], intent="compare")
    await research("q", ctx)
    prompt = provider.calls[0].prompt
    titles = [line for line in prompt.splitlines() if line.startswith("[")]
    assert [t.split("(")[1].split(",")[0] for t in titles] == ["Paper One", "Paper One", "Paper Two"]
    assert "Several documents" in (provider.calls[0].system or "")


# ── quotes ────────────────────────────────────────────────────────────────────


async def test_a_verbatim_model_quote_is_kept(tmp_path: Path):
    quote = "It ranks by cosine similarity."
    ctx, _ = make_ctx(tmp_path, reply_of(("Ranks by cosine.", [{"passage": 1, "quote": quote}])), fused=["a1"])
    answer, stats = await research("q", ctx)
    assert answer is not None and answer.data["citations"][0]["quote"] == quote
    assert stats["quotes_model"] == 1 and stats["quotes_server"] == 0


async def test_a_quote_differing_only_in_whitespace_is_kept_normalised(tmp_path: Path):
    ctx, _ = make_ctx(
        tmp_path, reply_of(("x", [{"passage": 1, "quote": "It  ranks\nby cosine   similarity."}])), fused=["a1"]
    )
    answer, _ = await research("q", ctx)
    assert answer is not None and answer.data["citations"][0]["quote"] == "It ranks by cosine similarity."


async def test_a_non_verbatim_model_quote_is_replaced_by_the_servers_sentence(tmp_path: Path):
    invented = "Dense retrieval always beats every other method."
    ctx, _ = make_ctx(tmp_path, reply_of(("Cosine ranking.", [{"passage": 1, "quote": invented}])), fused=["a1"])
    answer, stats = await research("q", ctx)
    assert answer is not None
    quote = answer.data["citations"][0]["quote"]
    assert quote != invented and quote in TEXTS["a1"]
    assert stats["quotes_server"] == 1 and stats["quotes_model"] == 0


async def test_a_bare_integer_citation_still_works_with_a_server_chosen_quote(tmp_path: Path):
    ctx, _ = make_ctx(tmp_path, reply_of(("Cosine ranking.", [1])), fused=["a1"])
    answer, stats = await research("q", ctx)
    assert answer is not None and answer.data["citations"][0]["quote"] in TEXTS["a1"]
    assert stats["quotes_server"] == 1


def test_verified_quote_rejects_trivial_and_non_string_quotes():
    text = TEXTS["a1"]
    assert verified_quote(text, "It") is None  # a verbatim but trivial span
    assert verified_quote(text, None) is None
    assert verified_quote(text, 42) is None
    assert verified_quote(text, "") is None
