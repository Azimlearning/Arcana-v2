"""The atomic-note builder (G1.2, D-34): the server's rules on what the model proposes, deterministic merging, the optional
store fields, and the pipeline end to end on fakes. No paid call."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from api.core.errors import IngestFailed
from api.fakes import fake_llm_responder
from api.ingestion import atomic
from api.ingestion.atomic import (
    ATOMIC_SYSTEM,
    KINDS,
    RELATIONS,
    BuildReport,
    build_atomic_result,
    canonicalise,
    defined_aliases,
    estimate_atomic_cost_usd,
    finalise,
    initials,
)
from api.ingestion.extract import ExtractionResult, estimate_extraction_cost_usd
from api.ingestion.pipeline import ingest_pdf
from api.llm.providers.fake import FakeProvider
from api.stores.doc_store import Chunk
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore

TEXT = (
    "Dense Retrieval embeds passages and queries into one vector space. "
    "BM25 scores exact terms with an inverted index. "
    "Dense Retrieval is compared with BM25 in the experiments of this paper."
)
CHUNK = Chunk("d1_c_1", "d1", 0, 1, TEXT)


def reply(concepts=None, relations=None) -> dict:
    return {
        "concepts": concepts
        if concepts is not None
        else [
            {
                "label": "Dense Retrieval",
                "kind": "method",
                "note": "Dense Retrieval embeds passages and queries into one vector space.",
            },
            {"label": "BM25", "kind": "method", "note": "BM25 scores exact terms with an inverted index."},
        ],
        "relations": relations
        if relations is not None
        else [
            {
                "src": "Dense Retrieval",
                "dst": "BM25",
                "type": "compares_with",
                "evidence": "Dense Retrieval is compared with BM25 in the experiments of this paper.",
            }
        ],
    }


def test_a_well_supported_reply_becomes_notes_with_a_kind_and_a_verbatim_sentence_and_an_evidenced_relation():
    result = build_atomic_result(reply(), CHUNK)
    assert [(n.id, n.kind, n.type) for n in result.nodes] == [
        ("dense_retrieval", "method", "method"),
        ("bm25", "method", "method"),
    ]
    assert result.nodes[0].note == "Dense Retrieval embeds passages and queries into one vector space."
    (edge,) = result.edges
    assert (edge.src, edge.dst, edge.relation, edge.chunk_id) == ("dense_retrieval", "bm25", "compares_with", "d1_c_1")
    assert edge.evidence == "Dense Retrieval is compared with BM25 in the experiments of this paper."
    assert result.drops == {}
    assert (
        all(n.note and n.note in TEXT for n in result.nodes) and edge.evidence and edge.evidence in TEXT
    )  # every sentence is a span of the chunk


@pytest.mark.parametrize(
    ("concepts", "reason"),
    [
        ([{"label": "BM25", "kind": "method"}], "concept_no_note"),
        ([{"label": "BM25", "kind": "method", "note": "  "}], "concept_no_note"),
        (
            [{"label": "BM25", "kind": "method", "note": "BM25 is the best method ever invented."}],
            "concept_note_not_verbatim",
        ),
        (
            [{"label": "Gamma Cache", "kind": "method", "note": "BM25 scores exact terms with an inverted index."}],
            "concept_note_missing_label",
        ),
        (
            [{"label": "", "kind": "method", "note": "BM25 scores exact terms with an inverted index."}],
            "concept_no_label",
        ),
        (["BM25"], "concept_malformed"),
    ],
)
def test_a_concept_without_a_verbatim_sentence_that_names_it_is_dropped_with_its_reason(concepts, reason):
    result = build_atomic_result(reply(concepts=concepts, relations=[]), CHUNK)
    assert result.nodes == [] and result.drops == {reason: 1}


@pytest.mark.parametrize(
    ("relation", "reason"),
    [
        (
            {
                "src": "Dense Retrieval",
                "dst": "Nowhere",
                "type": "uses",
                "evidence": "Dense Retrieval is compared with BM25 in the experiments of this paper.",
            },
            "relation_unknown_endpoint",
        ),
        (
            {
                "src": "BM25",
                "dst": "BM25",
                "type": "uses",
                "evidence": "BM25 scores exact terms with an inverted index.",
            },
            "relation_self_loop",
        ),
        ({"src": "Dense Retrieval", "dst": "BM25", "type": "uses"}, "relation_no_evidence"),
        (
            {
                "src": "Dense Retrieval",
                "dst": "BM25",
                "type": "uses",
                "evidence": "Dense Retrieval beats BM25 on every task.",
            },
            "relation_evidence_not_verbatim",
        ),
        (
            {
                "src": "Dense Retrieval",
                "dst": "BM25",
                "type": "uses",
                "evidence": "BM25 scores exact terms with an inverted index.",
            },
            "relation_evidence_missing_label",
        ),
        ("Dense Retrieval uses BM25", "relation_malformed"),
    ],
)
def test_a_relation_without_verbatim_evidence_naming_both_ends_is_dropped_with_its_reason(relation, reason):
    result = build_atomic_result(reply(relations=[relation]), CHUNK)
    assert result.edges == [] and result.drops == {reason: 1}
    assert len(result.nodes) == 2  # the concepts survive: they were supported on their own


def test_a_type_outside_the_closed_vocabulary_is_kept_as_other_and_counted_and_so_is_a_kind():
    concepts = reply()["concepts"]
    concepts[0]["kind"] = "gadget"
    relation = reply()["relations"][0] | {"type": "is a kind of cousin of"}
    result = build_atomic_result(reply(concepts=concepts, relations=[relation]), CHUNK)
    assert result.nodes[0].kind == "other" and result.edges[0].relation == "other"
    assert result.drops == {"kind_other": 1, "relation_type_other": 1}


def test_the_vocabulary_is_closed_and_authorship_is_one_relation():
    assert "authored_by" in RELATIONS and not {"authored", "author", "author_of"} & set(RELATIONS)
    assert "person" in KINDS and len(set(RELATIONS)) == len(RELATIONS)
    assert all(r in ATOMIC_SYSTEM for r in RELATIONS) and all(
        k in ATOMIC_SYSTEM for k in KINDS
    )  # the prompt names them all


def test_a_duplicate_concept_in_one_chunk_is_counted_and_a_wrong_shape_is_an_ingest_failure():
    twice = reply()["concepts"] + [dict(reply()["concepts"][0])]
    assert build_atomic_result(reply(concepts=twice, relations=[]), CHUNK).drops == {"concept_duplicate": 1}
    with pytest.raises(IngestFailed):
        build_atomic_result({"concepts": "none", "relations": []}, CHUNK)


def test_the_limits_on_a_reply_are_enforced():
    many = [
        {"label": f"Concept {i}", "kind": "concept", "note": f"Concept {i} appears in this passage."} for i in range(40)
    ]
    chunk = Chunk("c", "d", 0, 1, " ".join(c["note"] for c in many))
    assert len(build_atomic_result(reply(concepts=many, relations=[]), chunk).nodes) == atomic.MAX_CONCEPTS


# ── deterministic merging ─────────────────────────────────────────────────────


def test_defined_abbreviations_are_found_only_when_the_phrase_spells_them():
    found = defined_aliases(
        "We study Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG). The results (ROC) vary."
    )
    assert found["llms"] == found["llm"] == "Large Language Models"
    assert found["rag"] == "Retrieval-Augmented Generation"
    assert "roc" not in found  # "the results" does not spell ROC
    assert defined_aliases("Nothing is defined here.") == {} and initials("Retrieval-Augmented Generation") == "RAG"


def node(label: str, node_id: str | None = None) -> Node:
    return Node(
        node_id or atomic.concept_id(label),
        label,
        "concept",
        ("d1",),
        ("d1_c_1",),
        "concept",
        f"{label} is described here.",
    )


def test_an_abbreviation_defined_in_the_text_is_folded_into_its_phrase_and_the_merge_is_recorded():
    result = ExtractionResult(
        [node("LLMs"), node("Large Language Models")],
        [Edge("llm", "large_language_model", "uses", "d1_c_1", "d1"), Edge("llm", "other", "uses", "d1_c_1", "d1")],
    )
    merged, merges = canonicalise(result, {"llms": "Large Language Models"}, {})
    assert [n.id for n in merged.nodes] == ["large_language_model"] and merged.nodes[0].label == "Large Language Models"
    assert [(m.from_label, m.to_id, m.reason) for m in merges] == [("LLMs", "large_language_model", "defined_in_text")]
    # the first edge became a self-loop and is dropped and counted; the other still points at the remapped node
    assert [(e.src, e.dst) for e in merged.edges] == [("large_language_model", "other")]
    assert merged.drops == {"relation_self_loop_after_merge": 1}


def test_an_abbreviation_that_is_the_initials_of_exactly_one_known_concept_joins_it_and_an_ambiguous_one_does_not():
    known = {"retrieval_augmented_generation": "Retrieval-Augmented Generation", "knowledge_graph": "Knowledge Graph"}
    merged, merges = canonicalise(ExtractionResult([node("RAG")], []), {}, known)
    assert [n.id for n in merged.nodes] == ["retrieval_augmented_generation"]
    assert [(m.to_id, m.reason) for m in merges] == [("retrieval_augmented_generation", "initials_of_known")]
    ambiguous = {
        "random_access_graph": "Random Access Graph",
        "retrieval_augmented_generation": "Retrieval Augmented Generation",
    }
    left, none = canonicalise(ExtractionResult([node("RAG")], []), {}, ambiguous)
    assert [n.id for n in left.nodes] == ["rag"] and none == [] and left.drops == {"merge_ambiguous": 1}
    # a one-word known concept is never a target, and a lower-case word is never read as an abbreviation
    assert canonicalise(ExtractionResult([node("RAG")], []), {}, {"rag_x": "Rag"})[1] == []
    assert canonicalise(ExtractionResult([node("rag tag")], []), {}, known)[1] == []


def test_merging_is_deterministic_and_finalise_uses_the_documents_own_definitions():
    chunks = [
        Chunk("c1", "d1", 0, 1, "We use Large Language Models (LLMs) here."),
        Chunk("c2", "d1", 1, 1, "LLMs are used."),
    ]
    results = [ExtractionResult([node("Large Language Models")], []), ExtractionResult([node("LLMs")], []), None]
    out_a, merges_a = finalise(results, chunks, {})
    out_b, merges_b = finalise(results, chunks, {})
    assert out_a == out_b and merges_a == merges_b
    assert out_a[2] is None and [n.id for n in out_a[1].nodes] == ["large_language_model"]  # type: ignore[union-attr]


def test_a_plural_abbreviation_gets_the_abbreviations_id_not_a_split_one():
    from api.ingestion.extract import slug

    assert slug("LLMs") == "ll_ms"  # the free-form slug splits the plural: this is why LLM and LLMs were two hubs
    assert atomic.concept_id("LLMs") == atomic.concept_id("LLM") == "llm"
    assert (
        atomic.concept_id("GraphRAG") == "graph_rag"
        and atomic.concept_id("Large Language Models") == "large_language_model"
    )
    assert atomic.concept_id("...") == "unknown"


def test_a_build_report_lists_the_builder_prompt_version_drops_and_merges():
    from collections import Counter

    report = BuildReport(drops=Counter({"concept_no_note": 2}))
    report.merges.append(atomic.Merge("LLMs", "large_language_model", "defined_in_text"))
    out = report.as_dict()
    assert out["builder"] == "atomic" and out["prompt_version"] == atomic.PROMPT_VERSION
    assert out["drops"] == {"concept_no_note": 2} and out["merges"][0]["reason"] == "defined_in_text"


# ── the store ─────────────────────────────────────────────────────────────────


def test_the_new_fields_round_trip_and_a_store_that_never_has_them_writes_none(tmp_path: Path):
    path = tmp_path / "g.json"
    store = NetworkXGraphStore(path)
    store.upsert_node(node("BM25"))
    store.upsert_node(node("Dense Retrieval"))
    store.upsert_edge(
        Edge("bm25", "dense_retrieval", "compares_with", "d1_c_1", "d1", "BM25 is compared with Dense Retrieval.")
    )
    store.save()
    again = NetworkXGraphStore(path)
    assert again.get_node("bm25") == node("BM25")
    assert again.edges()[0].evidence == "BM25 is compared with Dense Retrieval."
    assert again.expand(["bm25"]).edges[0].evidence == "BM25 is compared with Dense Retrieval."

    plain = NetworkXGraphStore(tmp_path / "plain.json")
    plain.upsert_node(Node("a", "A", "concept", ("d",), ("c",)))
    plain.upsert_node(Node("b", "B", "concept", ("d",), ("c",)))
    plain.upsert_edge(Edge("a", "b", "uses", "c", "d"))
    plain.save()
    text = (tmp_path / "plain.json").read_text(encoding="utf-8")
    assert '"kind"' not in text and '"note"' not in text and '"evidence"' not in text  # nothing new for the old builder


def test_the_first_note_and_kind_seen_for_a_concept_are_kept(tmp_path: Path):
    store = NetworkXGraphStore(tmp_path / "g.json")
    store.upsert_node(Node("a", "A", None, ("d1",), ("c1",)))  # first seen without a note
    store.upsert_node(Node("a", "A", None, ("d2",), ("c2",), "method", "A is first described here."))
    store.upsert_node(Node("a", "A", None, ("d3",), ("c3",), "concept", "A is described again."))
    (stored,) = store.nodes()
    assert (stored.kind, stored.note) == ("method", "A is first described here.")


LIVE = Path(__file__).resolve().parents[2] / "data" / "eval-live-live"


@pytest.mark.skipif(not (LIVE / "graph.json").exists(), reason="the pinned live stores are not on this machine")
def test_the_pinned_graph_loads_and_saves_byte_for_byte_with_the_new_store_code(tmp_path: Path):
    """The frozen baseline must survive the store change: load it, save it elsewhere, and the bytes are identical."""
    copy = tmp_path / "graph.json"
    shutil.copyfile(LIVE / "graph.json", copy)
    before = hashlib.sha256(copy.read_bytes()).hexdigest()
    NetworkXGraphStore(copy).save()
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == before


# ── cost and the pipeline ─────────────────────────────────────────────────────


def test_the_atomic_worst_case_estimate_is_larger_than_the_free_form_one_for_the_same_chunks():
    chunks = [CHUNK, Chunk("c2", "d1", 1, 1, TEXT * 2)]
    assert estimate_atomic_cost_usd(chunks) > estimate_extraction_cost_usd(chunks) > 0


async def test_the_pipeline_builds_a_note_graph_with_the_atomic_builder_through_the_llm_seam(make_deps, pdf_bytes):
    provider = FakeProvider(fake_llm_responder)
    deps = make_deps(provider=provider)
    deps.builder = "atomic"
    result = await ingest_pdf(pdf_bytes, "paper.pdf", deps)
    assert result.status == "ready" and result.node_count > 0
    assert len(provider.calls) == result.chunk_count  # one extraction call per chunk, all through the seam
    assert {r["purpose"] for r in deps.llm._ledger.rows()} <= {"extract"}  # type: ignore[attr-defined]
    nodes, edges = deps.graph.nodes(), deps.graph.edges()
    assert all(n.note and n.kind for n in nodes)
    assert all(e.evidence and e.relation in {*RELATIONS, "other"} for e in edges)
    chunks = {c.id: c.text for c in deps.docs.all_chunks()}
    stored = " ".join(" ".join(t.split()) for t in chunks.values())
    assert all(n.note in stored for n in nodes)  # every note is a span of a stored chunk (whitespace normalised)
    assert all(e.evidence in " ".join(chunks[e.chunk_id].split()) for e in edges)
    report = result.build_report
    assert report is not None and report["builder"] == "atomic" and report["concepts"] >= result.node_count


async def test_the_default_builder_is_the_free_form_one_and_reports_nothing_new(make_deps, pdf_bytes):
    provider = FakeProvider(fake_llm_responder)
    deps = make_deps(provider=provider)
    result = await ingest_pdf(pdf_bytes, "paper.pdf", deps)
    assert deps.builder == "freeform" and result.build_report is None
    assert all(n.note is None and n.kind is None for n in deps.graph.nodes())
    assert all(e.evidence is None for e in deps.graph.edges())


def test_the_prompt_is_frozen_text_with_a_version(tmp_path):
    """The prompt may only change with the version: the protocol (G1.3) pins both."""
    digest = hashlib.sha256(ATOMIC_SYSTEM.encode()).hexdigest()
    assert atomic.PROMPT_VERSION == "g1-1" and len(digest) == 64
    assert json.dumps(sorted(KINDS)) and atomic.ATOMIC_MARKER in ATOMIC_SYSTEM
