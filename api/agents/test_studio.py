"""The Studio agent's writing tools and the Fact Checker's draft checks (P5 S1, D-42): grounded drafts, server-verified quotes, derived
references, a mutation suite of planted defects the checker must catch, and a write turn through the real graph."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine

from api.agents.fact_checker import (
    ORIGINALITY_MIN_WORDS,
    ORIGINALITY_RUN,
    check_draft,
    longest_shared_run,
    regroup_draft,
    screen_draft,
)
from api.agents.framework import AgentResult, route_to_agent
from api.agents.orchestrator import classify
from api.agents.state import Draft, TurnContext
from api.agents.studio import build_draft, draft_section, format_bibliography
from api.agents.test_agents import GRAPH
from api.agents.test_agents import make_ctx as graph_ctx
from api.core.budget import TokenBudget
from api.core.errors import ModelOutputInvalid
from api.genui.bibliography import arxiv_id, display_title, reference_for
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult, RetrievedChunk
from api.stores.doc_store import Document

DENSE = "Dense retrieval embeds queries and passages into one vector space. It ranks by cosine similarity."
SPARSE = "BM25 scores documents by term frequency and inverse document frequency. It needs no training."
DOCS = {
    "d1": Document("d1", "2310.11511_Dense_Retrieval_Survey", "2310.11511_Dense_Retrieval_Survey.pdf", "ready", 1, None, "2026"),
    "d2": Document("d2", "A Study of BM25", "bm25.pdf", "ready", 1, None, "2026"),
}
CHUNKS = {
    "k1": SimpleNamespace(id="k1", doc_id="d1", text=DENSE, page=1),
    "k2": SimpleNamespace(id="k2", doc_id="d2", text=SPARSE, page=2),
}


def _chunk(cid: str) -> RetrievedChunk:
    c = CHUNKS[cid]
    return RetrievedChunk(cid, c.doc_id, c.text, c.page, 1.0, ("dense",))


def make_ctx(tmp_path: Path, reply: str | None = None, *, fused: list[str] | None = None, judge: str = "{}") -> TurnContext:
    fused = ["k1", "k2"] if fused is None else fused

    async def retrieve(q: str) -> RetrievalResult:
        return RetrievalResult(chunks=[_chunk(c) for c in fused], per_signal={})

    docs: Any = SimpleNamespace(
        get_document=lambda d: DOCS.get(d),
        get_chunks=lambda ids: {i: CHUNKS[i] for i in ids if i in CHUNKS},
    )

    def respond(request) -> str:
        return judge if request.purpose == "check" else (reply or "{}")

    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 's.db'}"), None)
    return TurnContext(docs, retrieve, LLMService(FakeProvider(respond), None, ledger), TokenBudget(), "blk")


def reply_of(*sections: tuple[str, list[tuple[str, list[Any]]]], title: str = "On retrieval") -> str:
    return json.dumps(
        {
            "title": title,
            "sections": [
                {"heading": h, "segments": [{"text": t, "cites": c} for t, c in segs]} for h, segs in sections
            ],
        }
    )


GOOD = reply_of(
    ("Dense methods", [("Dense retrieval maps text into a shared vector space.", [{"passage": 1, "quote": "It ranks by cosine similarity."}])]),
    ("Sparse methods", [("BM25 weighs terms by how often they occur.", [{"passage": 2, "quote": "It needs no training."}])]),
)


# ── references ───────────────────────────────────────────────────────────────


def test_a_reference_is_built_from_the_stored_record_and_invents_nothing():
    ref = reference_for(DOCS["d1"])
    assert arxiv_id(DOCS["d1"]) == "2310.11511" and display_title(DOCS["d1"]) == "Dense Retrieval Survey"
    assert ref["apa"] == "Dense Retrieval Survey. arXiv:2310.11511."
    assert ref["ieee"] == '"Dense Retrieval Survey," arXiv:2310.11511.'
    assert "eprint = {2310.11511}" in ref["bibtex"] and ref["bibtex"].startswith("@misc{arcana")
    plain = reference_for(DOCS["d2"])  # no arXiv id in the file name: the reference says only the title
    assert plain["apa"] == "A Study of BM25." and "eprint" not in plain["bibtex"]
    assert not any(word in ref["apa"] + plain["apa"] for word in ("et al", "(20", "Proceedings", "Journal"))


def test_bibtex_special_characters_are_neutralised():
    doc = Document("x", "Fast & Cheap: 100% {R&D} #1_a", "x.pdf", "ready", 1, None, "2026")
    bib = reference_for(doc)["bibtex"]
    assert "\\&" in bib and "\\%" in bib and "\\#" in bib and "\\_" in bib
    assert "{R" not in bib.split("title = ", 1)[1].split("\n")[0].replace("{", "", 1)  # inner braces dropped


# ── the writing tool ─────────────────────────────────────────────────────────


async def test_a_grounded_draft_has_server_verified_quotes_and_a_derived_bibliography(tmp_path: Path):
    ctx = make_ctx(tmp_path, GOOD)
    draft, stats = await draft_section("retrieval", ctx)
    assert draft is not None and stats["quotes_model"] == 2 and stats["quotes_server"] == 0
    data = draft.data
    assert [s["heading"] for s in data["sections"]] == ["Dense methods", "Sparse methods"]
    assert {c["id"] for c in data["citations"]} == {"c1", "c2"}
    assert {c["quote"] for c in data["citations"]} == {"It ranks by cosine similarity.", "It needs no training."}
    assert [e["docId"] for e in data["bibliography"]] == ["d1", "d2"]
    assert data["bibliography"][0]["apa"] == reference_for(DOCS["d1"])["apa"]


async def test_a_fabricated_quote_is_replaced_by_the_servers_own_sentence(tmp_path: Path):
    reply = reply_of(("Dense", [("Dense retrieval uses vectors.", [{"passage": 1, "quote": "This sentence is not in the passage at all."}])]))
    draft, stats = await draft_section("retrieval", make_ctx(tmp_path, reply))
    assert draft is not None and stats["quotes_server"] == 1
    quote = draft.data["citations"][0]["quote"]
    assert quote in DENSE or " ".join(quote.split()) in " ".join(DENSE.split())


async def test_uncited_passages_and_empty_sections_are_dropped_and_nothing_is_invented(tmp_path: Path):
    reply = reply_of(
        ("Kept", [("Dense retrieval maps text to vectors.", [1]), ("A claim with no citation.", [])]),
        ("Dropped", [("Cites a passage that was never shown.", [{"passage": 9, "quote": "x"}])]),
        ("Kept", [("Same heading again.", [2])]),  # a repeated heading is dropped, not merged
    )
    draft, _ = await draft_section("retrieval", make_ctx(tmp_path, reply))
    assert draft is not None
    assert [s["heading"] for s in draft.data["sections"]] == ["Kept"]
    assert [seg["text"] for seg in draft.data["sections"][0]["segments"]] == ["Dense retrieval maps text to vectors."]


async def test_no_evidence_means_no_draft_and_no_model_call(tmp_path: Path):
    ctx = make_ctx(tmp_path, GOOD, fused=[])
    draft, stats = await draft_section("retrieval", ctx)
    assert draft is None and stats["passages"] == 0 and ctx.budget.used == 0


async def test_the_model_saying_there_is_nothing_to_write_is_no_draft(tmp_path: Path):
    draft, _ = await draft_section("retrieval", make_ctx(tmp_path, json.dumps({"title": "", "sections": []})))
    assert draft is None


async def test_an_unusable_reply_is_a_model_output_error_not_a_draft(tmp_path: Path):
    with pytest.raises(ModelOutputInvalid):
        await draft_section("retrieval", make_ctx(tmp_path, "not json at all"))
    with pytest.raises(ModelOutputInvalid):
        await draft_section("retrieval", make_ctx(tmp_path, json.dumps({"title": "x", "sections": "no"})))


async def test_caps_are_respected(tmp_path: Path):
    many = reply_of(*((f"Section {i}", [("Dense retrieval maps text to vectors.", [1])]) for i in range(12)))
    draft, _ = await draft_section("retrieval", make_ctx(tmp_path, many))
    assert draft is not None and len(draft.data["sections"]) == 6


def test_format_bibliography_skips_a_document_that_is_not_stored(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    assert [e["docId"] for e in format_bibliography(["d2", "ghost", "d2", "d1"], ctx)] == ["d2", "d1"]


def test_build_draft_is_pure_of_the_model(tmp_path: Path):
    ctx = make_ctx(tmp_path)
    passages = [(_chunk("k1"), "Dense"), (_chunk("k2"), "Sparse")]
    stats = {"quotes_model": 0, "quotes_server": 0}
    draft = build_draft(json.loads(GOOD), passages, ctx, stats)
    assert isinstance(draft, Draft) and stats["quotes_model"] == 2


# ── the checker: planted defects it must catch ──────────────────────────────


def _draft_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "On retrieval",
        "sections": [
            {"heading": "Dense", "segments": [{"text": "Dense retrieval embeds text into a shared vector space.", "citationIds": ["c1"]}]},
            {"heading": "Sparse", "segments": [{"text": "BM25 scores documents using term frequency.", "citationIds": ["c2"]}]},
        ],
        "citations": [
            {"id": "c1", "chunkId": "k1", "docId": "d1", "docTitle": "T", "page": 1, "quote": "It ranks by cosine similarity."},
            {"id": "c2", "chunkId": "k2", "docId": "d2", "docTitle": "T", "page": 2, "quote": "It needs no training."},
        ],
        "bibliography": [
            {"docId": "d1", **reference_for(DOCS["d1"])},
            {"docId": "d2", **reference_for(DOCS["d2"])},
        ],
    }
    data.update(changes)
    return data


async def _checked(tmp_path: Path, data: dict[str, Any], judge: str = "{}"):
    ctx = make_ctx(tmp_path, judge=judge)
    ctx.results["studio"] = AgentResult("studio", "ok", {"draft": Draft(data)})
    return await check_draft(ctx)


async def test_a_good_draft_passes_whole(tmp_path: Path):
    outcome = await _checked(tmp_path, _draft_data())
    assert outcome is not None and outcome.data is not None
    assert outcome.passages_in == outcome.passages_kept == 2 and outcome.citations_dropped == 0
    assert [s["heading"] for s in outcome.data["sections"]] == ["Dense", "Sparse"]
    assert outcome.references_rebuilt == 0


def _swap_quote(data: dict[str, Any]) -> dict[str, Any]:
    data["citations"][0]["quote"] = "A sentence that is not in the chunk at all."
    return data


def _wrong_doc(data: dict[str, Any]) -> dict[str, Any]:
    data["citations"][0]["docId"] = "d2"
    return data


def _unknown_chunk(data: dict[str, Any]) -> dict[str, Any]:
    data["citations"][0]["chunkId"] = "nope"
    return data


def _uncited(data: dict[str, Any]) -> dict[str, Any]:
    data["sections"][0]["segments"][0]["citationIds"] = []
    return data


def _cites_missing(data: dict[str, Any]) -> dict[str, Any]:
    data["sections"][0]["segments"][0]["citationIds"] = ["c9"]
    return data


def _short_quote(data: dict[str, Any]) -> dict[str, Any]:
    data["citations"][0]["quote"] = "It"
    return data


PLANTED = {
    "fabricated_quote": _swap_quote,
    "citation_from_another_document": _wrong_doc,
    "citation_to_unknown_chunk": _unknown_chunk,
    "uncited_passage": _uncited,
    "passage_cites_missing_citation": _cites_missing,
    "quote_too_short_to_be_evidence": _short_quote,
}


@pytest.mark.parametrize("name", list(PLANTED))
async def test_every_planted_defect_removes_the_passage_it_damages_and_only_that(tmp_path: Path, name: str):
    outcome = await _checked(tmp_path, PLANTED[name](_draft_data()))
    assert outcome is not None and outcome.data is not None
    assert outcome.passages_kept == 1 and outcome.removed == 1  # the damaged passage is gone, the intact one stays
    assert [s["heading"] for s in outcome.data["sections"]] == ["Sparse"]  # and its section with it
    assert {c["id"] for c in outcome.data["citations"]} == {"c2"}
    assert [e["docId"] for e in outcome.data["bibliography"]] == ["d2"]  # the reference of a removed source goes too


async def test_a_claim_the_judge_calls_unsupported_is_removed_even_with_a_valid_quote(tmp_path: Path):
    verdicts = json.dumps({"verdicts": [{"segment": 1, "supported": False}, {"segment": 2, "supported": True}]})
    outcome = await _checked(tmp_path, _draft_data(), judge=verdicts)
    assert outcome is not None and outcome.data is not None and outcome.unsupported == 1
    assert [s["heading"] for s in outcome.data["sections"]] == ["Sparse"]


async def test_a_wrong_reference_is_rebuilt_from_the_record_not_trusted(tmp_path: Path):
    data = _draft_data()
    data["bibliography"][0]["apa"] = "Invented, A. (2020). A paper that does not exist."
    outcome = await _checked(tmp_path, data)
    assert outcome is not None and outcome.data is not None and outcome.references_rebuilt == 1
    assert outcome.data["bibliography"][0]["apa"] == reference_for(DOCS["d1"])["apa"]


async def test_a_draft_with_nothing_left_is_no_draft(tmp_path: Path):
    data = _draft_data()
    data["citations"][0]["quote"] = "not in the chunk"
    data["citations"][1]["quote"] = "also not in the chunk"
    outcome = await _checked(tmp_path, data)
    assert outcome is not None and outcome.data is None and outcome.passages_kept == 0


async def test_a_passage_that_copies_its_source_is_reported_not_hidden(tmp_path: Path):
    copied = "Dense retrieval embeds queries and passages into one vector space"
    data = _draft_data()
    data["sections"][0]["segments"][0]["text"] = copied + "."
    data["citations"][0]["quote"] = DENSE
    outcome = await _checked(tmp_path, data)
    assert outcome is not None and outcome.too_close == 1 and outcome.passages_kept == 2
    assert longest_shared_run(copied, [DENSE]) == len(copied.split())
    assert len(copied.split()) >= ORIGINALITY_MIN_WORDS and ORIGINALITY_RUN <= 1


def test_longest_shared_run_ignores_case_and_punctuation():
    assert longest_shared_run("It RANKS by cosine similarity!", [DENSE]) == 5
    assert longest_shared_run("Nothing in common here.", [DENSE]) == 0
    assert longest_shared_run("", [DENSE]) == 0


def test_screen_and_regroup_keep_order_and_drop_empty_sections():
    data = _draft_data()
    screened, where = screen_draft(data, CHUNKS)
    assert where == [(0, 0), (1, 0)] and len(screened.candidates) == 2
    outcome = screened.finalize({0: False})  # the first passage fails
    regrouped, _, _ = regroup_draft(data, outcome, where, SimpleNamespace(get_document=lambda d: DOCS.get(d)))
    assert regrouped is not None and [s["heading"] for s in regrouped["sections"]] == ["Sparse"]


# ── a write turn through the real graph ──────────────────────────────────────

WRITE = "Write an outline on how dense retrieval compares with BM25"


def test_the_write_intent_is_recognised_by_rules_and_outranks_the_questions_other_cues():
    assert classify(WRITE) == ("write", True)
    assert classify("Draft a literature review on retrieval")[0] == "write"
    assert classify("Give me a bibliography for these papers")[0] == "write"
    assert classify("What is dense retrieval?") == ("single", True)  # a plain question is not a writing request


@pytest.mark.parametrize(
    "question",
    [
        "What failure modes of vector-only retrieval are identified across the papers? Provide examples and cite the relevant sources.",
        "What is the outline of the method in Self-RAG?",
        "Cite the sources for dense retrieval.",
        "How does the related work section describe BM25?",
        "Which essay-style benchmarks do the papers use?",
        "Is there a bibliography of hybrid retrieval methods in these papers?",
    ],
)
def test_a_question_that_only_mentions_writing_is_not_a_writing_request(question: str):
    assert classify(question)[0] != "write"


def test_no_frozen_benchmark_question_is_rerouted_to_write():
    import yaml

    path = Path(__file__).resolve().parents[2] / "eval" / "questions.yaml"
    questions = yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]
    assert len(questions) == 20 and all(classify(q["question"])[0] != "write" for q in questions)


@pytest.mark.parametrize(
    ("request_text", "topic"),
    [
        ("Write an outline on how dense retrieval compares with BM25", "how dense retrieval compares with BM25"),
        ("Draft a literature review of graph retrieval", "graph retrieval"),
        ("Can you outline hybrid search?", "hybrid search"),
        ("Dense retrieval", "Dense retrieval"),
    ],
)
def test_the_topic_of_a_writing_request_is_what_retrieval_is_searched_with(request_text: str, topic: str):
    from api.agents.studio import topic_of

    assert topic_of(request_text) == topic


async def test_a_write_turn_ends_at_the_composer_with_a_validated_draft(ingested, tmp_path: Path):
    deps, _ = ingested
    ctx = graph_ctx(deps, tmp_path)
    state = await GRAPH.ainvoke({"question": WRITE}, context=ctx)
    composition = state["composition"]
    types = [b.type for b in composition.blocks]
    assert types[0] == "CitedSummary" and "WritingDraft" in types  # the answer first, the draft beside it
    draft = next(b for b in composition.blocks if b.type == "WritingDraft")
    assert draft.meta.status == "ready" and draft.data.sections and draft.data.bibliography  # type: ignore[union-attr]
    stored = deps.docs.get_chunks([c.chunkId for c in draft.data.citations])  # type: ignore[union-attr]
    for citation in draft.data.citations:  # type: ignore[union-attr]
        assert " ".join(citation.quote.split()) in " ".join(stored[citation.chunkId].text.split())
    cited_docs = {c.docId for c in draft.data.citations}  # type: ignore[union-attr]
    assert {e.docId for e in draft.data.bibliography} == cited_docs  # type: ignore[union-attr]
    assert any(r.component == "WritingDraft" and r.outcome == "admitted" for r in composition.records)
    assert ctx.results["studio"].status in ("ok", "partial")
    assert ctx.intent == "write"


async def test_without_a_checker_result_the_draft_is_not_shown(ingested, tmp_path: Path):
    """Fail closed (constraint 1): a checker that did not run means the Composer shows no draft, only the answer's own gate decides."""
    deps, _ = ingested
    ctx = graph_ctx(deps, tmp_path)
    await route_to_agent(ctx, "studio", WRITE)  # the draft exists, but the checker never ran
    from api.agents.compose import _studio_draft

    assert ctx.results["studio"].payload["draft"] is not None
    assert _studio_draft(ctx) is None


# ── V2 (D-43): the kinds of writing, and a script's speakers ─────────────────


DOCS_NS: Any = SimpleNamespace(
    get_document=lambda d: DOCS.get(d),
    get_chunks=lambda ids: {i: CHUNKS[i] for i in ids if i in CHUNKS},
)


@pytest.mark.parametrize(
    ("request_text", "kind"),
    [
        ("Write an outline on dense retrieval", "outline"),
        ("Draft an essay on hybrid search", "outline"),
        ("Write an abstract on dense retrieval", "abstract"),
        ("Draft a literature review of graph retrieval", "literature_review"),
        ("Make an audio overview of dense retrieval", "script"),
        ("Write a podcast script about BM25", "script"),
    ],
)
def test_the_kind_of_writing_is_chosen_by_keyword_and_defaults_to_an_outline(request_text: str, kind: str):
    from api.agents.studio import write_kind

    assert write_kind(request_text) == kind


@pytest.mark.parametrize(
    "question",
    [
        "Write an abstract on dense retrieval",
        "Make an audio overview of dense retrieval",
        "Create a podcast script about BM25",
        "Give me a literature review of hybrid search",
    ],
)
def test_the_new_kinds_are_write_requests(question: str):
    assert classify(question) == ("write", True)


@pytest.mark.parametrize(
    ("request_text", "topic"),
    [
        ("Write an abstract on dense retrieval", "dense retrieval"),
        ("Make an audio overview of dense retrieval", "dense retrieval"),
        ("Write a podcast script about BM25", "BM25"),
    ],
)
def test_the_topic_of_the_new_kinds_is_what_retrieval_is_searched_with(request_text: str, topic: str):
    from api.agents.studio import topic_of

    assert topic_of(request_text) == topic


def _script_reply(speakers: list[Any]) -> str:
    segs = [
        {"text": f"Turn {i}.", "cites": [{"passage": 1 if i % 2 == 0 else 2, "quote": "It ranks by cosine similarity." if i % 2 == 0 else "It needs no training."}]}
        | ({"speaker": s} if s is not None else {})
        for i, s in enumerate(speakers)
    ]
    return json.dumps({"title": "Overview", "sections": [{"heading": "Opening", "segments": segs}]})


async def test_a_script_gives_every_line_a_known_speaker_and_a_kind(tmp_path: Path):
    ctx = make_ctx(tmp_path, _script_reply(["host", "guest", "narrator", None]))
    draft, stats = await draft_section("retrieval", ctx, "script")
    assert draft is not None and stats["kind"] == "script"
    assert draft.data["kind"] == "script"
    # a named speaker is kept; an unknown or missing one becomes the voice whose turn it is (the host opens, the voices alternate)
    assert [s["speaker"] for s in draft.data["sections"][0]["segments"]] == ["host", "guest", "host", "guest"]


async def test_an_outline_has_a_kind_and_no_speakers(tmp_path: Path):
    ctx = make_ctx(tmp_path, GOOD)
    draft, _ = await draft_section("retrieval", ctx)
    assert draft is not None and draft.data["kind"] == "outline"
    assert all("speaker" not in seg for sec in draft.data["sections"] for seg in sec["segments"])


async def test_the_checker_keeps_a_scripts_speakers_and_kind(tmp_path: Path):
    from api.agents.fact_checker import regroup_draft, screen_draft

    data = _draft_data(kind="script")
    for i, segment in enumerate(s for sec in data["sections"] for s in sec["segments"]):
        segment["speaker"] = ("host", "guest")[i % 2]
    screened, where = screen_draft(data, {c["chunkId"]: CHUNKS[c["chunkId"]] for c in data["citations"]})
    checked, _, _ = regroup_draft(data, screened.finalize({}), where, DOCS_NS)
    assert checked is not None and checked["kind"] == "script"
    assert [s["speaker"] for sec in checked["sections"] for s in sec["segments"]] == ["host", "guest"]


def _valid_script(tmp_path: Path) -> dict[str, Any]:
    """A script the server's own builder made: valid in every respect, so a test that plants one defect is rejected for that defect."""
    passages = [(_chunk("k1"), DOCS["d1"].title), (_chunk("k2"), DOCS["d2"].title)]
    stats = {"quotes_model": 0, "quotes_server": 0}
    draft = build_draft(json.loads(_script_reply(["host", "guest"])), passages, make_ctx(tmp_path), stats, "script")
    assert draft is not None
    return draft.data


def _validate_draft(data: dict[str, Any]):
    from api.genui.builders import BUILDERS
    from api.genui.validate import validate_block

    return validate_block(BUILDERS["WritingDraft"]("b", "ready", data=data), DOCS_NS)


def _lines(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [seg for sec in data["sections"] for seg in sec["segments"]]


def test_a_well_formed_script_and_a_legacy_draft_without_a_kind_both_validate(tmp_path: Path):
    data = _valid_script(tmp_path)
    assert _validate_draft(data).data.kind == "script"  # type: ignore[union-attr]
    legacy = {k: v for k, v in data.items() if k != "kind"}
    for seg in _lines(legacy):
        seg.pop("speaker")
    assert _validate_draft(legacy).data.kind is None  # type: ignore[union-attr]


@pytest.mark.parametrize("defect", ["script_line_without_speaker", "speaker_on_an_outline", "speaker_on_an_abstract"])
def test_the_validator_refuses_a_speaker_where_there_should_be_none_and_none_where_one_is_needed(tmp_path: Path, defect: str):
    from api.core.errors import ValidationFailed

    data = _valid_script(tmp_path)
    if defect == "script_line_without_speaker":
        _lines(data)[1].pop("speaker")
    else:
        data["kind"] = "outline" if defect == "speaker_on_an_outline" else "abstract"
    with pytest.raises(ValidationFailed) as caught:
        _validate_draft(data)
    assert [i.path for i in caught.value.issues if "speaker" in i.path]


async def test_a_script_turn_ends_at_the_composer_with_a_validated_script(ingested, tmp_path: Path):
    deps, _ = ingested
    ctx = graph_ctx(deps, tmp_path)
    state = await GRAPH.ainvoke({"question": "Make an audio overview of dense retrieval"}, context=ctx)
    draft = next(b for b in state["composition"].blocks if b.type == "WritingDraft")
    assert draft.data.kind == "script"  # type: ignore[union-attr]
    lines = [s for sec in draft.data.sections for s in sec.segments]  # type: ignore[union-attr]
    assert lines and all(s.speaker in ("host", "guest") for s in lines)
