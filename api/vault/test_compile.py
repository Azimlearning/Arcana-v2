"""The vault core (M2.1): every expected value below is worked out by hand from the handmade world.

World (two documents, passages in document order):
    c1 d1/0  "Retrieval-Augmented Generation (RAG) combines retrieval with generation. RAG improves factuality."
    c2 d1/1  "Self-RAG uses reflection tokens. Reflection tokens guide the model."
    c3 d2/0  "Large language models hallucinate. Retrieval- augmented generation cuts it in large language models and RAG helps."
    c4 d2/1  "Alice Smith and Bob Jones wrote this. Nothing else."
    c5 d2/2  "Unrelated text about cooking."
"""

import itertools
import random
from pathlib import Path

import pytest

from api.ingestion.atomic import label_in_text
from api.stores.doc_store import Chunk, Document
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.compile import compile_vault
from api.vault.local import JsonVaultStore
from api.vault.text import fold, looks_bibliographic, occurs, split_sentences
from api.vault.types import MAX_SENTENCE_PAGES, ClaimDraft, Vault

C1 = "Retrieval-Augmented Generation (RAG) combines retrieval with generation. RAG improves factuality."
C2 = "Self-RAG uses reflection tokens. Reflection tokens guide the model."
C3 = "Large language models hallucinate. Retrieval- augmented generation cuts it in large language models and RAG helps."
C4 = "Alice Smith and Bob Jones wrote this. Nothing else."
C5 = "Unrelated text about cooking."
TEXTS = {
    "c1": ("d1", 0, C1),
    "c2": ("d1", 1, C2),
    "c3": ("d2", 0, C3),
    "c4": ("d2", 1, C4),
    "c5": ("d2", 2, C5),
}


def world(
    tmp_path: Path, *, shuffle: int | None = None, extra_chunks=(), extra_nodes=(), extra_edges=()
):
    docs = SqliteDocStore(make_engine(tmp_path / "a.db"))
    for d in ("d1", "d2"):
        docs.put_document(Document(d, d, f"{d}.pdf", "ready", 1, None, "2026-10-07"))
    chunks = [Chunk(cid, d, i, 1, text) for cid, (d, i, text) in TEXTS.items()] + list(extra_chunks)
    docs.put_chunks(chunks)
    nodes = [
        Node(
            "retrieval_augmented_generation",
            "Retrieval-Augmented Generation",
            "concept",
            ("d1",),
            ("c1",),
            "concept",
            C1.split(". ")[0] + ".",
        ),
        Node("rag", "RAG", "concept", ("d1",), ("c1",), "concept", C1.split(". ")[0] + "."),
        Node(
            "self_rag",
            "Self-RAG",
            "method",
            ("d1",),
            ("c2",),
            "method",
            "Self-RAG uses reflection tokens.",
        ),
        Node(
            "reflection_token",
            "reflection tokens",
            "concept",
            ("d1",),
            ("c2",),
            "concept",
            "Self-RAG uses reflection tokens.",
        ),
        Node(
            "large_language_model",
            "large language models",
            "concept",
            ("d2",),
            ("c3",),
            "concept",
            None,
        ),
        Node("alice_smith", "Alice Smith", "person", ("d2",), ("c4",), "person", None),
        Node("bob_jones", "Bob Jones", "person", ("d2",), ("c4",), "person", None),
        *extra_nodes,
    ]
    edges = [
        Edge(
            "rag",
            "retrieval_augmented_generation",
            "alias_of",
            "c1",
            "d1",
            "Retrieval-Augmented Generation (RAG) combines retrieval with generation.",
        ),
        Edge(
            "self_rag", "reflection_token", "uses", "c2", "d1", "Self-RAG uses reflection tokens."
        ),
        Edge("self_rag", "rag", "extends", "c2", "d1", None),
        *extra_edges,
    ]
    if shuffle is not None:
        random.Random(shuffle).shuffle(nodes)
        random.Random(shuffle).shuffle(edges)
    g = NetworkXGraphStore(tmp_path / "g.json")
    for n in nodes:
        g.upsert_node(n)
    for e in edges:
        g.upsert_edge(e)
    return g, docs


def test_aliases_become_one_page_with_the_long_label_and_the_abbreviation_as_an_alias(
    tmp_path: Path,
):
    v = compile_vault(*world(tmp_path))
    page = v.pages["rag"]  # the smaller of the two member ids names the page
    assert page.node_ids == ("rag", "retrieval_augmented_generation")
    assert page.label == "Retrieval-Augmented Generation" and page.aliases == ("RAG",)
    assert page.kind == "concept" and page.doc_ids == ("d1",)
    assert v.page_of_node("retrieval_augmented_generation") == "rag"
    assert "retrieval_augmented_generation" not in v.pages
    assert len(v.pages) == 6  # 7 nodes, two of them one page


def test_mentions_are_found_across_the_corpus_blind_to_hyphenation_and_not_inside_other_words(
    tmp_path: Path,
):
    v = compile_vault(*world(tmp_path))
    # c1 by the chunk list; c3 by the label ("Retrieval- augmented generation" folds to the same words, and "RAG" is whole there);
    # c2 holds only "Self-RAG", whose folded form "selfrag" does not contain the word "rag".
    assert v.pages["rag"].mention_chunk_ids == ("c1", "c3")
    assert v.pages["self_rag"].mention_chunk_ids == ("c2",)
    assert v.pages["large_language_model"].mention_chunk_ids == ("c3",)
    assert v.pages["reflection_token"].mention_chunk_ids == (
        "c2",
    )  # "Reflection tokens" in the second sentence too, same passage
    assert v.df("rag") == 2 and v.n_chunks == 5


def test_spread_is_one_for_a_rare_page_and_falls_with_how_many_passages_mention_it(tmp_path: Path):
    import math

    v = compile_vault(*world(tmp_path))
    n = 5
    assert v.idf("rag") == pytest.approx(math.log(1 + n / 2) / math.log(1 + n))
    assert (
        v.idf("self_rag")
        == pytest.approx(math.log(1 + n / 1) / math.log(1 + n))
        == pytest.approx(1.0)
    )
    assert v.idf("rag") < v.idf("self_rag")


def test_an_asserted_link_is_lifted_to_pages_and_an_alias_inside_a_page_is_counted_not_linked(
    tmp_path: Path,
):
    v = compile_vault(*world(tmp_path))
    asserted = {
        (link.src, link.dst, link.relation): link for link in v.links if link.kind == "asserted"
    }
    assert set(asserted) == {
        ("self_rag", "reflection_token", "uses"),
        ("self_rag", "rag", "extends"),
    }
    uses = asserted[("self_rag", "reflection_token", "uses")]
    assert uses.chunk_ids == ("c2",) and uses.evidence == "Self-RAG uses reflection tokens."
    assert (
        asserted[("self_rag", "rag", "extends")].evidence is None
    )  # a free-form edge carries none
    assert v.stats["alias_edges_inside_a_page"] == 1


def test_a_co_mention_needs_two_pages_in_one_sentence(tmp_path: Path):
    v = compile_vault(*world(tmp_path))
    co = [
        (link.src, link.dst, link.chunk_ids, link.evidence)
        for link in v.links
        if link.kind == "co_mention"
    ]
    assert co == [
        (
            "large_language_model",
            "rag",
            ("c3",),
            "Retrieval- augmented generation cuts it in large language models and RAG helps.",
        ),
        (
            "reflection_token",
            "self_rag",
            ("c2",),
            "Self-RAG uses reflection tokens.",
        ),  # the pair is also asserted: both kinds are kept
    ]
    # c1's first sentence names the page twice (long form and abbreviation) and that is one page, not a pair.


def test_people_make_no_co_mention_links(tmp_path: Path):
    v = compile_vault(*world(tmp_path))
    # "Alice Smith and Bob Jones wrote this." names two pages of kind person: no link, though both are mentioned there
    assert v.pages["alice_smith"].mention_chunk_ids == ("c4",) and v.pages[
        "bob_jones"
    ].mention_chunk_ids == ("c4",)
    assert not any({"alice_smith", "bob_jones"} == {link.src, link.dst} for link in v.links)


def test_a_sentence_naming_more_than_the_cap_makes_no_links_and_exactly_the_cap_makes_all_pairs(
    tmp_path: Path,
):
    def run(count: int) -> int:
        d = tmp_path / f"n{count}"
        d.mkdir()
        labels = [f"term{i}" for i in range(count)]
        text = " ".join(labels) + "."
        nodes = [Node(label, label, None, ("d1",), ("c9",), None, None) for label in labels]
        g, docs = world(d, extra_chunks=[Chunk("c9", "d1", 9, 1, text)], extra_nodes=nodes)
        return sum(
            1
            for link in compile_vault(g, docs).links
            if link.kind == "co_mention" and link.chunk_ids == ("c9",)
        )

    assert MAX_SENTENCE_PAGES == 6
    assert run(6) == 15 == len(list(itertools.combinations(range(6), 2)))
    assert run(7) == 0


def test_definitions_point_at_the_passage_that_holds_the_sentence(tmp_path: Path):
    v = compile_vault(*world(tmp_path))
    defs = v.pages["rag"].definitions
    assert [(d.text, d.chunk_id, d.doc_id) for d in defs] == [
        ("Retrieval-Augmented Generation (RAG) combines retrieval with generation.", "c1", "d1")
    ]  # the two members share one note: one definition
    assert v.pages["large_language_model"].definitions == ()


def test_claims_map_concepts_to_pages_and_unusable_ones_are_counted(tmp_path: Path):
    g, docs = world(tmp_path)
    good = ClaimDraft(
        "c1", "d1", "RAG improves factuality.", ("rag", "retrieval_augmented_generation")
    )
    v = compile_vault(
        g,
        docs,
        claims=[
            good,
            good,  # a duplicate
            ClaimDraft(
                "c2", "d1", "Reflection tokens guide the model.", ("reflection_token", "ghost")
            ),
            ClaimDraft("c9", "d1", "No such passage.", ("rag",)),
            ClaimDraft("c1", "d1", "Names no known concept.", ("ghost",)),
        ],
    )
    assert [(c.chunk_id, c.page_ids) for c in v.claims] == [
        ("c1", ("rag",)),
        ("c2", ("reflection_token",)),
    ]
    assert v.stats["claims"] == 2 and v.stats["claims_dropped"] == 3
    assert [c.sentence for c in v.claims_of("rag")] == ["RAG improves factuality."]


def test_the_vault_does_not_depend_on_the_order_nodes_and_edges_were_stored_in(tmp_path: Path):
    hashes = set()
    for seed in range(5):
        d = tmp_path / f"s{seed}"
        d.mkdir()
        hashes.add(compile_vault(*world(d, shuffle=seed)).sha256())
    assert len(hashes) == 1


def test_a_vault_survives_the_store_round_trip_with_its_label_vectors(tmp_path: Path):
    v = compile_vault(*world(tmp_path))
    store = JsonVaultStore(tmp_path / "vault.json")
    store.put_vault(v)
    store.put_label_vectors({"rag": [0.5, 0.25], "ghost": [1.0]})
    store.put_vault(v)  # a rebuild drops vectors of pages that no longer exist
    assert set(store.label_vectors()) == {"rag"}
    store.save()
    again = JsonVaultStore(tmp_path / "vault.json")
    loaded = again.vault()
    assert isinstance(loaded, Vault) and loaded.sha256() == v.sha256()
    assert again.label_vectors() == {"rag": [0.5, 0.25]}
    assert JsonVaultStore(tmp_path / "none.json").vault() is None


def test_an_empty_graph_gives_an_empty_vault(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "e.db"))
    v = compile_vault(NetworkXGraphStore(tmp_path / "e.json"), docs)
    assert v.pages == {} and v.links == [] and v.claims == [] and v.n_chunks == 0


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Retrieval- augmented generation helps.", "Retrieval-Augmented Generation"),
        ("Self-RAG is a method.", "RAG"),
        ("We use GPT-4 here.", "GPT-4"),
        ("Chain of thought", "AI"),
        ("An AI system", "AI"),
        ("the model's output", "model"),
        ("", "x"),
    ],
)
def test_the_vault_matcher_agrees_with_the_builders_label_test(text: str, label: str):
    assert occurs(fold(text), fold(label)) == label_in_text(text, label)


def test_sentences_are_verbatim_spans_of_the_normalised_passage():
    text = "One sentence.   Two\nsentence? Three!"
    parts = split_sentences(text)
    assert parts == ["One sentence.", "Two sentence?", "Three!"]
    assert all(p in " ".join(text.split()) for p in parts)


def test_a_reference_entry_makes_no_co_mention_but_a_prose_citation_does(tmp_path: Path):
    ref = "Yu, Structure-aware language model pretraining improves dense retrieval, arXiv preprint arXiv:2305.19912, 2023."
    prose = "Lewis et al. combine a language model with dense retrieval."
    nodes = [
        Node("language_model", "language model", None, ("d1",), ("c8", "c9"), None, None),
        Node("dense_retrieval", "dense retrieval", None, ("d1",), ("c8", "c9"), None, None),
    ]
    chunks = [Chunk("c8", "d1", 8, 1, ref), Chunk("c9", "d1", 9, 1, prose)]
    v = compile_vault(*world(tmp_path, extra_chunks=chunks, extra_nodes=nodes))
    pair = [link for link in v.links if link.kind == "co_mention" and link.src == "dense_retrieval"]
    assert [(link.dst, link.chunk_ids) for link in pair] == [("language_model", ("c9",))]
    assert looks_bibliographic(ref) and not looks_bibliographic(prose)
