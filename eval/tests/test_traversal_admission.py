"""The TraversalView admission study (P2c T3): the summary arithmetic and the guards of the command."""

import json
from pathlib import Path

from api.stores.doc_store import Chunk, Document
from api.stores.graph_store import Edge, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from eval import traversal_admission
from eval.traversal_admission import main, measure_question, summarise


def row(admitted: bool, reasons: list[str], seeds: int, followed: int, shown: int, via: dict[str, int]):
    return {
        "admitted": admitted,
        "reasons": reasons,
        "seeds": [{"label": f"s{i}", "match": "exact" if i % 2 == 0 else "approximate"} for i in range(seeds)],
        "steps_followed": followed,
        "steps_shown": shown,
        "steps_left_out": followed - shown,
        "reached": sum(via.values()),
        "reached_via": via,
    }


def test_the_summary_counts_admission_refusals_sizes_and_ways_of_being_reached_by_hand():
    rows = [
        row(True, [], 3, 40, 5, {"mentions": 8, "neighbour": 2}),
        row(False, ["nothing_resolved"], 0, 0, 0, {}),
        row(False, ["no_edge_followed"], 2, 6, 0, {"mentions": 10}),
        row(True, [], 1, 2, 2, {"mentions": 6, "edge": 4}),
    ]
    s = summarise(rows)
    assert (s["questions"], s["admitted"], s["rate"]) == (4, 2, 0.5)
    assert s["refusal_reasons"] == {"no_edge_followed": 1, "nothing_resolved": 1}
    assert s["seeds_per_question"] == [0, 1, 2, 3] and s["seeds_total"] == 6 and s["approximate_seeds"] == 2
    assert s["steps_followed_per_question"] == [0, 2, 6, 40] and s["steps_shown_per_question"] == [0, 0, 2, 5]
    assert s["reached_via_total"] == {"mentions": 24, "neighbour": 2, "edge": 4}
    assert summarise([])["rate"] is None


def make_store(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    docs = SqliteDocStore(make_engine(tmp / "arcana.db"))
    docs.put_document(Document("d", "Paper", "d.pdf", "ready", 1, None, "t"))
    docs.put_chunks(
        [
            Chunk("c1", "d", 0, 1, "Alpha Method builds on Beta Index in this paper at length."),
            Chunk("c2", "d", 1, 1, "Beta Index is also compared with Gamma Cache here at length."),
        ]
    )
    graph = NetworkXGraphStore(tmp / "graph.json")
    graph.upsert_node(Node("alpha_method", "Alpha Method", None, ("d",), ("c1",)))
    graph.upsert_node(Node("beta_index", "Beta Index", None, ("d",), ("c1", "c2")))
    graph.upsert_edge(Edge("alpha_method", "beta_index", "builds_on", "c1", "d"))
    graph.save()
    return tmp


async def test_a_question_that_resolves_a_concept_with_an_edge_is_admitted_and_a_nonsense_one_is_not(tmp_path):
    store = make_store(tmp_path / "s")
    graph = NetworkXGraphStore(store / "graph.json")
    docs = SqliteDocStore(make_engine(store / "arcana.db"))
    hit = await measure_question("What does Alpha Method build on?", graph, docs)
    assert hit["admitted"] and [s["label"] for s in hit["seeds"]] == ["Alpha Method"]
    assert hit["steps_followed"] == 1 and hit["steps_shown"] == 1 and hit["reached"] == 2
    miss = await measure_question("zebra giraffe", graph, docs)
    assert not miss["admitted"] and miss["reasons"] == ["nothing_resolved"] and miss["seeds"] == []


def test_the_command_writes_a_result_with_no_model_or_network_call_and_refuses_a_wrong_hash_and_a_dirty_tree(
    tmp_path, monkeypatch, capsys
):
    store = make_store(tmp_path / "s")
    questions = tmp_path / "q.yaml"
    questions.write_text(
        "questions:\n  - id: q1\n    category: x\n    question: What does Alpha Method build on?\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    base = ["--data-dir", str(store), "--questions-file", str(questions), "--out", str(out), "--allow-dirty"]
    assert main([*base, "--label", "t"]) == 0
    (path,) = out.glob("*-t.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["run"]["model_calls"] == 0 and result["run"]["network_calls"] == 0
    assert result["summary"]["admitted"] == 1 and result["results"][0]["question_id"] == "q1"
    try:
        main([*base, "--expect-graph-sha256", "0" * 64])
    except SystemExit as exc:
        assert "differs from the pinned value" in str(exc)
    monkeypatch.setattr(
        traversal_admission, "git_state", lambda: {"commit": "abc", "dirty": True, "changed_files": [" M x"]}
    )
    assert main(["--data-dir", str(store), "--questions-file", str(questions), "--out", str(out)]) == 2
    assert "commit first" in capsys.readouterr().err
