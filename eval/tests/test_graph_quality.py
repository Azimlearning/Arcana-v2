"""The structural metrics of a graph (G1.1): hand-computed on a tiny graph, and the guards of the command."""

import json
from pathlib import Path

from api.stores.doc_store import Chunk, Document
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from eval import graph_quality
from eval.graph_quality import MAX_LABEL_CHARS, edge_facts, main, measure, relation_words, sentences

CHUNKS = {
    "d1_c_1": "Alpha Method builds on Beta Index. It was proposed in 2020.",
    "d1_c_2": "Alpha Method is discussed here. Separately, Gamma Cache appears much later in the passage.",
    "d2_c_1": "Delta Store uses Gamma Cache for every query that it receives.",
}


def node(i, label, docs, chunks):
    return Node(i, label, None, tuple(docs), tuple(chunks))


NODES = [
    node("alpha", "Alpha Method", ["d1"], ["d1_c_1", "d1_c_2"]),
    node("beta", "Beta Index", ["d1"], ["d1_c_1"]),
    node("gamma", "Gamma Cache", ["d1", "d2"], ["d1_c_2", "d2_c_1"]),
    node("delta", "Delta Store", ["d2"], ["d2_c_1"]),
    node("lone", "Lonely", ["d2"], []),
]
EDGES = [
    Edge("alpha", "beta", "builds_on", "d1_c_1", "d1"),  # stated in one sentence, a real relation
    Edge("alpha", "gamma", "related_to", "d1_c_2", "d1"),  # generic, and the two are in different sentences
    Edge("delta", "gamma", "uses", "d2_c_1", "d2"),  # stated in one sentence
    Edge("delta", "beta", "uses", "d2_c_1", "d2"),  # beta is not in that chunk
]


def test_sentences_and_relation_words_are_normalised():
    assert sentences("One two.  Three four! Five?") == ["One two.", "Three four!", "Five?"]
    assert relation_words("Builds_On  ") == "builds on"


def test_an_edge_is_stated_when_one_sentence_of_its_chunk_names_both_ends():
    labels = {n.id: n.label for n in NODES}
    stated = edge_facts(EDGES[0], labels, CHUNKS["d1_c_1"])
    assert stated["both_in_chunk"] and stated["in_one_sentence"] and stated["drawable"] and not stated["co_mention"]
    apart = edge_facts(EDGES[1], labels, CHUNKS["d1_c_2"])
    assert apart["both_in_chunk"] and not apart["in_one_sentence"] and apart["generic"] and apart["co_mention"]
    absent = edge_facts(EDGES[3], labels, CHUNKS["d2_c_1"])
    assert not absent["both_in_chunk"] and absent["co_mention"] and not absent["drawable"]
    gone = edge_facts(EDGES[0], labels, None)
    assert gone["chunk_missing"] and not gone["drawable"]


def test_a_label_is_matched_as_a_whole_word_and_a_too_long_label_is_not_drawable():
    labels = {"a": "AI", "b": "Alpha Method"}
    inside_a_word = edge_facts(Edge("a", "b", "uses", "c", "d"), labels, "The chain uses Alpha Method here at length.")
    assert not inside_a_word["both_in_chunk"]
    long_label = {"a": "x" * (MAX_LABEL_CHARS + 1), "b": "Alpha Method"}
    text = f"{long_label['a']} uses Alpha Method in this very sentence."
    facts = edge_facts(Edge("a", "b", "uses", "c", "d"), long_label, text)
    assert facts["in_one_sentence"] and not facts["drawable"]


def test_the_metrics_are_what_they_should_be_on_the_tiny_graph():
    m = measure(NODES, EDGES, CHUNKS)
    assert (m["nodes"], m["edges"]) == (5, 4)
    assert m["edges_stated_in_chunk"] == {"count": 3, "share": 0.75}
    assert m["edges_stated_in_one_sentence"] == {"count": 2, "share": 0.5}
    assert m["edges_generic_relation"]["count"] == 1
    assert m["edges_co_mention"] == {"count": 2, "share": 0.5}
    assert m["edges_drawable"] == {"count": 2, "share": 0.5}
    assert m["nodes_singleton"]["count"] == 3  # beta, delta, lone
    assert m["nodes_in_two_or_more_documents"]["count"] == 1  # gamma
    assert m["nodes_with_no_edge"]["count"] == 1  # lone
    assert m["largest_hubs"][0]["degree"] == 2
    assert m["most_common_relations"][0] == {"relation": "uses", "count": 2}


def test_a_slice_keeps_only_its_documents_and_the_empty_graph_has_no_shares():
    m = measure(NODES, EDGES, CHUNKS, frozenset({"d2"}))
    assert (m["nodes"], m["edges"]) == (3, 2)  # gamma, delta, lone; the two d2 edges
    assert m["nodes_in_two_or_more_documents"]["count"] == 0  # gamma's d1 mention is outside the slice
    empty = measure([], [], {})
    assert empty["edges"] == 0 and empty["edges_drawable"]["share"] is None


def make_store(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    docs = SqliteDocStore(make_engine(tmp / "arcana.db"))
    for d in ("d1", "d2"):
        docs.put_document(Document(d, f"Paper {d}", f"{d}.pdf", "ready", 1, None, "t"))
    docs.put_chunks([Chunk(cid, cid.split("_c_")[0], i, 1, text) for i, (cid, text) in enumerate(CHUNKS.items())])
    graph = NetworkXGraphStore(tmp / "graph.json")
    for n in NODES:
        graph.upsert_node(n)
    for e in EDGES:
        graph.upsert_edge(e)
    graph.save()
    return tmp


def test_the_command_writes_a_result_that_names_its_hashes_and_refuses_a_wrong_hash(tmp_path, capsys):
    store = make_store(tmp_path / "store")
    out = tmp_path / "out"
    assert main(["--data-dir", str(store), "--out", str(out), "--allow-dirty", "--label", "t"]) == 0
    (path,) = out.glob("*-t.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert set(result["run"]["hashes"]) == {"graph_sha256", "chunks_sha256"}
    assert result["run"]["code"]["commit"] and "Structure only" in result["run"]["protocol"]
    assert result["metrics"]["edges"] == 4
    assert main(["--data-dir", str(store), "--out", str(out), "--allow-dirty", "--expect-graph-sha256", "0" * 64]) == 2
    assert "differs from the pinned value" in capsys.readouterr().err


def test_the_command_refuses_a_missing_store_unknown_documents_and_a_dirty_tree(tmp_path, monkeypatch, capsys):
    assert main(["--data-dir", str(tmp_path), "--allow-dirty"]) == 2
    store = make_store(tmp_path / "store")
    assert main(["--data-dir", str(store), "--out", str(tmp_path / "o"), "--allow-dirty", "--docs", "nope"]) == 2
    monkeypatch.setattr(graph_quality, "git_state", lambda: {"commit": "abc", "dirty": True, "changed_files": [" M x"]})
    assert main(["--data-dir", str(store), "--out", str(tmp_path / "o")]) == 2
    assert "commit first" in capsys.readouterr().err
