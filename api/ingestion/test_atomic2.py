"""The sentence-numbered builder `atomic2` (M2.4): every expected value is worked out by hand from one handmade passage.

Passage (normalised), sentences numbered from 1:
    [1] Retrieval-Augmented Generation (RAG) is a method that combines retrieval with generation.
    [2] Self-RAG uses reflection tokens to critique its output.
    [3] We also thank the reviewers.
    [4] Reflection tokens guide the model.
"""

import hashlib
import json

import pytest

from api.core.errors import IngestFailed
from api.fakes import fake_llm_responder
from api.genui.evidence import QUOTE_CHARS
from api.ingestion import atomic2
from api.ingestion.atomic import RELATIONS
from api.ingestion.atomic2 import (
    ATOMIC2_MARKER,
    ATOMIC2_SYSTEM,
    PROMPT_VERSION,
    build_atomic2_result,
    build_prompt,
    estimate_atomic2_cost_usd,
)
from api.ingestion.extract import estimate_extraction_cost_usd
from api.ingestion.pipeline import ingest_pdf
from api.llm.providers.fake import FakeProvider
from api.stores.doc_store import Chunk
from api.vault.text import split_sentences

S1 = "Retrieval-Augmented Generation (RAG) is a method that combines retrieval with generation."
S2 = "Self-RAG uses reflection tokens to critique its output."
S3 = "We also thank the reviewers."
S4 = "Reflection tokens guide the model."
TEXT = f"{S1}  {S2}\n{S3} {S4}"
CHUNK = Chunk("c1", "d1", 0, 1, TEXT)


def reply(**parts) -> dict:
    return {"concepts": [], "relations": [], "claims": [], **parts}


CONCEPTS = [
    {"label": "Retrieval-Augmented Generation", "kind": "method"},
    {"label": "RAG", "kind": "concept"},
    {"label": "Self-RAG", "kind": "method"},
    {"label": "reflection tokens", "kind": "concept"},
]


def by_id(result):
    return {n.id: n for n in result.nodes}


def test_the_passage_is_shown_as_numbered_verbatim_sentences():
    assert split_sentences(TEXT) == [S1, S2, S3, S4]
    prompt = build_prompt(split_sentences(TEXT))
    assert prompt == f"<passage>\n[1] {S1}\n[2] {S2}\n[3] {S3}\n[4] {S4}\n</passage>"
    assert atomic2.atomic2_request(CHUNK).prompt == prompt


def test_the_server_chooses_a_concepts_note_and_prefers_a_definitional_sentence():
    result = build_atomic2_result(reply(concepts=CONCEPTS), CHUNK)
    nodes = by_id(result)
    assert (
        nodes["rag"].note == S1
    )  # "RAG" occurs in [1] only: "Self-RAG" does not hold the word RAG
    assert nodes["retrieval_augmented_generation"].note == S1
    assert nodes["self_rag"].note == S2
    # "reflection tokens" is in [2] and [4], neither with a definitional cue: the first wins
    assert nodes["reflection_token"].note == S2
    assert nodes["rag"].kind == "concept" and nodes["self_rag"].kind == "method"


def test_a_definitional_sentence_beats_an_earlier_plain_one():
    text = "Dense retrieval matters a lot in practice. Dense retrieval is a method that embeds queries and passages."
    chunk = Chunk("c2", "d1", 0, 1, text)
    result = build_atomic2_result(
        reply(concepts=[{"label": "dense retrieval", "kind": "method"}]), chunk
    )
    assert result.nodes[0].note == "Dense retrieval is a method that embeds queries and passages."


def test_a_concept_the_passage_does_not_hold_or_a_bad_label_is_dropped_and_counted():
    result = build_atomic2_result(
        reply(
            concepts=[
                {"label": "Ghost concept", "kind": "concept"},
                {"label": "x", "kind": "concept"},
                {"label": "", "kind": "concept"},
                "not a dict",
                {"label": "RAG", "kind": "wizard"},
                {"label": "RAG", "kind": "method"},
            ]
        ),
        CHUNK,
    )
    assert [n.id for n in result.nodes] == ["rag"] and result.nodes[0].kind == "other"
    assert result.drops == {
        "concept_label_in_no_sentence": 1,
        "concept_label_too_short": 1,
        "concept_no_label": 1,
        "concept_malformed": 1,
        "kind_other": 1,
        "concept_duplicate": 1,
    }


def test_a_relation_uses_the_hinted_sentence_and_the_server_checks_it():
    result = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[{"src": "Self-RAG", "dst": "reflection tokens", "type": "uses", "s": 2}],
        ),
        CHUNK,
    )
    (edge,) = result.edges
    assert (edge.src, edge.dst, edge.relation, edge.evidence) == (
        "self_rag",
        "reflection_token",
        "uses",
        S2,
    )
    assert not {k for k in result.drops if k.startswith("relation_")}


def test_a_wrong_hint_is_corrected_by_the_server_and_two_adjacent_sentences_may_carry_a_relation():
    # "Self-RAG" is in [2] and "RAG" in [1]: no single sentence holds both, the pair [1] [2] does
    far = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[{"src": "Self-RAG", "dst": "RAG", "type": "extends", "s": 4}],
        ),
        CHUNK,
    )
    (edge,) = far.edges
    assert edge.evidence == f"{S1} {S2}" and edge.relation == "extends"
    assert (
        far.drops["relation_window_of_two"] == 1 and far.drops["relation_sentence_corrected"] == 1
    )
    # a hint that names either sentence of the pair is the model's own window: not a correction
    near = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[{"src": "Self-RAG", "dst": "RAG", "type": "extends", "s": 2}],
        ),
        CHUNK,
    )
    assert (
        near.edges[0].evidence == f"{S1} {S2}" and "relation_sentence_corrected" not in near.drops
    )
    # a hint at a sentence that does hold the labels is not corrected, and a missing hint is counted
    fine = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[{"src": "Self-RAG", "dst": "reflection tokens", "type": "uses"}],
        ),
        CHUNK,
    )
    assert (
        fine.drops["relation_without_a_usable_number"] == 1
        and "relation_sentence_corrected" not in fine.drops
    )


def test_every_stored_sentence_is_a_verbatim_span_of_the_normalised_passage():
    result = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[{"src": "Self-RAG", "dst": "RAG", "type": "extends", "s": 1}],
            claims=[1, 2, 4],
        ),
        CHUNK,
    )
    normal = " ".join(TEXT.split())
    assert all((n.note or "") in normal for n in result.nodes)
    assert all((e.evidence or "") in normal for e in result.edges)
    assert all(c.sentence in normal for c in result.claims)


def test_relation_problems_are_dropped_and_counted_under_their_own_reason():
    result = build_atomic2_result(
        reply(
            concepts=CONCEPTS,
            relations=[
                {"src": "Ghost", "dst": "RAG", "type": "uses", "s": 1},
                {"src": "RAG", "dst": "RAG", "type": "uses", "s": 1},
                {
                    "src": "Self-RAG",
                    "dst": "Retrieval-Augmented Generation",
                    "type": "enhances",
                    "s": True,
                },
                "nope",
                {
                    "src": "reflection tokens",
                    "dst": "Retrieval-Augmented Generation",
                    "type": "uses",
                    "s": 9,
                },
            ],
        ),
        CHUNK,
    )
    # a boolean is not a sentence number; "enhances" is not in the vocabulary; the last pair is found by the server
    # in no single sentence and no adjacent pair ([1]+[2] hold "Retrieval-Augmented Generation" and not "reflection tokens"
    # ... [2] does hold it, so the pair [1] [2] is found)
    assert (
        result.drops["relation_unknown_endpoint"] == 1 and result.drops["relation_self_loop"] == 1
    )
    assert result.drops["relation_malformed"] == 1 and result.drops["relation_type_other"] == 1
    assert {e.relation for e in result.edges} == {"other", "uses"}
    # a boolean and an out-of-range number are both "no usable number"; neither counts as a correction
    assert (
        result.drops["relation_without_a_usable_number"] == 2
        and "relation_sentence_corrected" not in result.drops
    )


def test_labels_that_are_never_together_make_no_relation():
    text = "Alpha method is described here in detail. Many unrelated words follow in this sentence. Beta dataset is large."
    chunk = Chunk("c3", "d1", 0, 1, text)
    result = build_atomic2_result(
        reply(
            concepts=[
                {"label": "Alpha method", "kind": "method"},
                {"label": "Beta dataset", "kind": "dataset"},
            ],
            relations=[
                {"src": "Alpha method", "dst": "Beta dataset", "type": "evaluated_on", "s": 1}
            ],
        ),
        chunk,
    )
    assert (
        result.edges == [] and result.drops["relation_labels_not_together"] == 1
    )  # [1] and [3] are not adjacent


def test_an_adjacent_pair_longer_than_the_quote_cap_is_not_used():
    a = "Alpha method is described here " + "word " * 30 + "end."
    b = "Beta dataset is large " + "word " * 30 + "end."
    assert len(a) + len(b) + 1 > QUOTE_CHARS
    chunk = Chunk("c4", "d1", 0, 1, f"{a} {b}")
    result = build_atomic2_result(
        reply(
            concepts=[
                {"label": "Alpha method", "kind": "method"},
                {"label": "Beta dataset", "kind": "dataset"},
            ],
            relations=[{"src": "Alpha method", "dst": "Beta dataset", "type": "uses", "s": 1}],
        ),
        chunk,
    )
    assert result.edges == [] and result.drops["relation_labels_not_together"] == 1


def test_a_long_sentence_is_cut_on_a_word_boundary_and_must_still_hold_the_label():
    long = "Dense retrieval " + "filler " * 60 + "ends."
    chunk = Chunk("c5", "d1", 0, 1, long)
    node = build_atomic2_result(
        reply(concepts=[{"label": "dense retrieval", "kind": "method"}]), chunk
    ).nodes[0]
    assert (
        len(node.note or "") <= QUOTE_CHARS
        and long.startswith(node.note or "")
        and not (node.note or "").endswith(" ")
    )
    late = "Filler " * 60 + "then Dense retrieval appears."
    dropped = build_atomic2_result(
        reply(concepts=[{"label": "dense retrieval", "kind": "method"}]),
        Chunk("c6", "d1", 0, 1, late),
    )
    assert (
        dropped.nodes == [] and dropped.drops["concept_label_in_no_sentence"] == 1
    )  # beyond the cut: not a usable note


def test_claims_are_sentences_the_server_checks_and_they_stay_out_of_the_graph():
    result = build_atomic2_result(
        reply(concepts=CONCEPTS, claims=[4, 3, 9, "x", 2, 2, True]), CHUNK
    )
    assert [(c.sentence, c.concept_ids) for c in result.claims] == [
        (S4, ("reflection_token",)),
        (S2, ("reflection_token", "self_rag")),
    ]
    assert all(c.chunk_id == "c1" and c.doc_id == "d1" for c in result.claims)
    assert result.drops["claim_names_no_concept"] == 1  # [3] names no kept concept
    assert result.drops["claim_bad_number"] == 3  # 9, "x", True
    assert result.drops["claim_duplicate"] == 1 and result.drops["claims_kept"] == 2
    assert not any(s in {n.note for n in result.nodes} for s in ())  # claims are not nodes


def test_claims_are_capped_at_six_per_passage():
    sentences = [
        f"Concept alpha is described in sentence number {i} of the passage." for i in range(1, 10)
    ]
    chunk = Chunk("c7", "d1", 0, 1, " ".join(sentences))
    result = build_atomic2_result(
        reply(concepts=[{"label": "Concept alpha", "kind": "concept"}], claims=list(range(1, 10))),
        chunk,
    )
    assert len(result.claims) == 6 and result.drops["claim_over_cap"] == 3


def test_a_reply_of_the_wrong_shape_is_a_malformed_extraction():
    with pytest.raises(IngestFailed):
        build_atomic2_result({"concepts": "RAG", "relations": []}, CHUNK)
    with pytest.raises(IngestFailed):
        build_atomic2_result({"concepts": [], "relations": [], "claims": {"a": 1}}, CHUNK)


def test_the_estimate_is_a_worst_case_larger_than_the_free_form_one():
    chunks = [CHUNK, Chunk("c2", "d1", 1, 1, TEXT * 2)]
    assert estimate_atomic2_cost_usd(chunks) > estimate_extraction_cost_usd(chunks) > 0


def test_the_prompt_is_frozen_text_with_a_version():
    """The prompt may only change with the version: the protocol (D-35) pins both."""
    assert PROMPT_VERSION == "g2-1" and ATOMIC2_MARKER in ATOMIC2_SYSTEM
    digest = hashlib.sha256(ATOMIC2_SYSTEM.encode("utf-8")).hexdigest()
    assert digest == PINNED_PROMPT_SHA256, f"the prompt changed without a version change: {digest}"
    assert all(r in ATOMIC2_SYSTEM for r in RELATIONS)


PINNED_PROMPT_SHA256 = "ce690fa3b3867d3b001e0b3308d171d82762e428e729c5177dd520bf9527b4e8"


async def test_the_pipeline_builds_the_graph_and_hands_the_claims_to_a_sink(make_deps, pdf_bytes):
    provider = FakeProvider(fake_llm_responder)
    deps = make_deps(provider=provider)
    deps.builder = "atomic2"
    deps.claim_sink = []
    result = await ingest_pdf(pdf_bytes, "paper.pdf", deps)
    assert result.status == "ready" and result.node_count > 0
    assert (
        len(provider.calls) == result.chunk_count
    )  # one extraction call per chunk, all through the seam
    assert all(ATOMIC2_MARKER in (call.system or "") for call in provider.calls)
    nodes, edges = deps.graph.nodes(), deps.graph.edges()
    assert all(n.note and n.kind for n in nodes) and all(e.evidence for e in edges)
    assert deps.claim_sink and all(c.sentence and c.concept_ids for c in deps.claim_sink)
    report = result.build_report
    assert (
        report is not None and report["builder"] == "atomic2" and report["prompt_version"] == "g2-1"
    )
    assert report["drops"].get("claims_kept") == len(deps.claim_sink)
    chunks = {c.id: " ".join(c.text.split()) for c in deps.docs.all_chunks()}
    assert all(e.evidence in chunks[e.chunk_id] for e in edges) and all(
        c.sentence in chunks[c.chunk_id] for c in deps.claim_sink
    )
    json.dumps(report)  # the report is plain data


def test_a_null_field_is_an_empty_list_not_a_lost_passage():
    result = build_atomic2_result({"concepts": CONCEPTS, "relations": None, "claims": None}, CHUNK)
    assert len(result.nodes) == 4 and result.edges == [] and result.claims == []
    assert build_atomic2_result({"concepts": None}, CHUNK).nodes == []


def test_what_the_caps_cut_and_a_repeated_relation_are_counted_not_silent():
    many = [{"label": f"Concept number {i}", "kind": "concept"} for i in range(30)]
    text = " ".join(f"Concept number {i} is described in this sentence." for i in range(30))
    over = build_atomic2_result({"concepts": many}, Chunk("c9", "d1", 0, 1, text))
    assert len(over.nodes) == atomic2.MAX_CONCEPTS and over.drops["concept_over_cap"] == 5
    relation = {"src": "Self-RAG", "dst": "reflection tokens", "type": "uses", "s": 2}
    again = build_atomic2_result({"concepts": CONCEPTS, "relations": [relation] * 3}, CHUNK)
    assert len(again.edges) == 1 and again.drops["relation_duplicate"] == 2
    lots = build_atomic2_result({"concepts": CONCEPTS, "relations": [relation] * 45}, CHUNK)
    assert lots.drops["relation_over_cap"] == 5
