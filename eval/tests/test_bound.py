"""The admission-rate study (P2 D2): admission is the catalog's own check, flat never admits a graph component, and the run
is refused on mismatched stores or a dirty tree."""

# ruff: noqa: F811  (the `bench` fixture is imported from test_runner and used by name)

import json
from pathlib import Path

import pytest

from api.stores.doc_store import Document
from eval import bound
from eval.bound import (
    CATALOG,  # the retrieval-supplied components: the Studio's draft is not part of the study
    FLAT_ADMITS,
    admission,
    evidence_for,
    main,
    summarise,
)
from eval.run_ablation import RunInvalid, require_expected_hashes
from eval.tests.test_runner import (  # noqa: F401  (a tiny fake-mode benchmark world)
    bench,
    result_of,
)

DOCS = tuple(Document(f"d{i}", f"Paper {i}", f"d{i}.pdf", "ready", 1, None, "t") for i in (1, 2))
COUNTS = {"d1": 4, "d2": 3}


def edge(src, dst, chunk, doc, quote):
    return {
        "src": src,
        "dst": dst,
        "relation": "builds_on",
        "chunk_id": chunk,
        "doc_id": doc,
        "quote": quote,
        "page": 1,
        "doc_title": f"Paper {doc[-1]}",
    }


def rich_graph(hops: int = 3) -> dict:
    """A path of `hops` grounded hops through concepts A, B, C, D, and an alignment of two papers on two entities."""
    names = ["Alpha Method", "Beta Index", "Gamma Cache", "Delta Store"]
    edges = [
        edge(f"n{i}", f"n{i + 1}", f"c{i}", "d1", f"{names[i]} is described next to {names[i + 1]} in this paper.")
        for i in range(hops)
    ]
    cell = lambda doc, dim, label: {  # noqa: E731
        "doc_id": doc,
        "dimension_id": dim,
        "chunk_id": f"{doc}-{dim}",
        "page": 1,
        "quote": f"{label} is discussed in this paper at some length.",
        "doc_title": f"Paper {doc[-1]}",
    }
    return {
        "traversal": {
            "seeds": [{"id": "n0", "label": "Alpha Method", "match": "exact"}],
            "steps": [{"seed_id": "n0", "src": "n0", "dst": "n1", "relation": "builds_on", "chunk_id": "c0"}],
            "steps_total": 5,
            "left_out": 4,
            "reached": [{"chunk_id": "c0", "via": "mentions", "rank": 1, "seed_ids": ["n0"]}],
        },
        "mode": "path",
        "entities": ["n0", f"n{hops}"],
        "edges": edges,
        "labels": {f"n{i}": names[i] for i in range(4)},
        "alignment": {
            "documents": [{"doc_id": "d1", "title": "Paper 1"}, {"doc_id": "d2", "title": "Paper 2"}],
            "dimensions": [{"id": "a", "label": "Alpha Method"}, {"id": "b", "label": "Beta Index"}],
            "cells": [cell(d, k, lab) for d in ("d1", "d2") for k, lab in (("a", "Alpha Method"), ("b", "Beta Index"))],
        },
    }


def admitted(rows: dict) -> set[str]:
    return {name for name, a in rows.items() if a["admitted"]}


# ── admission, hand-computed on a tiny case ───────────────────────────────────


def test_on_a_rich_graph_the_hybrid_layer_admits_every_component_and_the_counts_are_what_they_should_be():
    rows = admission(evidence_for("hybrid", 8, rich_graph(3), DOCS, COUNTS))
    assert admitted(rows) == set(CATALOG)
    assert rows["GraphView"]["detail"] == {"drawable_edges": 3}
    assert rows["ComparisonGrid"]["detail"] == {"documents": 2, "entities": 2, "cells": 4}
    assert rows["ConceptMap"]["detail"] == {"hops": 3}
    assert rows["TraversalView"]["detail"] == {"seeds": 1, "steps_shown": 1, "steps_followed": 5}
    assert rows["SourceList"]["detail"] == {"ready_documents": 2}


def test_flat_admits_only_the_answer_and_the_source_list_even_when_a_graph_is_at_hand():
    rows = admission(evidence_for("flat", 8, rich_graph(3), DOCS, COUNTS))  # the graph payload must be ignored
    assert admitted(rows) == set(FLAT_ADMITS) == {"CitedSummary", "SourceList"}
    for name in ("GraphView", "ComparisonGrid", "ConceptMap"):
        assert rows[name]["reasons"] == ["no_graph_result"]


def test_a_refused_component_carries_its_reason():
    one_hop = admission(evidence_for("hybrid", 8, rich_graph(1), DOCS, COUNTS))
    assert one_hop["ConceptMap"] == {"admitted": False, "reasons": ["single_hop"], "detail": {"hops": 0}}
    assert one_hop["GraphView"]["admitted"] and one_hop["GraphView"]["detail"] == {"drawable_edges": 1}
    unquoted = rich_graph(3)
    unquoted["edges"][1]["quote"] = None  # an ungrounded middle hop
    assert admission(evidence_for("hybrid", 8, unquoted, DOCS, COUNTS))["ConceptMap"]["reasons"] == ["ungrounded_hop"]
    no_docs = admission(evidence_for("hybrid", 0, None, (), {}))
    assert no_docs["SourceList"]["reasons"] == ["no_ready_document"]
    assert no_docs["CitedSummary"]["reasons"] == ["no_grounded_answer"]  # nothing retrieved: no answer to show


# ── the summary ───────────────────────────────────────────────────────────────


def row(qid: str, graph: dict | None, hit_rate: float | None, entities: int = 1) -> dict:
    layers = {}
    for layer in ("flat", "hybrid"):
        layers[layer] = {
            "retrieved": 8,
            "resolution": {"hit_rate": hit_rate, "entities": [object()] * entities}
            if layer == "hybrid" and hit_rate is not None
            else None,
            "admission": admission(evidence_for(layer, 8, graph, DOCS, COUNTS)),
        }
    return {"question_id": qid, "category": "x", "layers": layers}


def test_the_summary_counts_rates_realised_sets_and_refusals_by_hand():
    rows = [
        row("q1", rich_graph(3), 1.0),
        row("q2", rich_graph(1), 0.5),
        row("q3", None, 0.0, entities=0),
        row("q4", None, None),
    ]
    s = summarise(rows)
    hybrid, flat = s["per_layer"]["hybrid"], s["per_layer"]["flat"]
    assert hybrid["components"]["CitedSummary"] == {"admitted": 4, "rate": 1.0, "refusal_reasons": {}}
    assert hybrid["components"]["GraphView"]["admitted"] == 2 and hybrid["components"]["GraphView"]["rate"] == 0.5
    assert hybrid["components"]["GraphView"]["refusal_reasons"] == {"no_graph_result": 2}
    assert hybrid["components"]["ConceptMap"]["admitted"] == 1
    assert hybrid["components"]["ConceptMap"]["refusal_reasons"] == {"no_graph_result": 2, "single_hop": 1}
    assert hybrid["components"]["ComparisonGrid"]["admitted"] == 2
    assert hybrid["X"] == sorted(CATALOG) and flat["X"] == ["CitedSummary", "SourceList"]
    assert (
        s["hybrid_only"] == ["ComparisonGrid", "ConceptMap", "GraphView", "TraversalView"]
        and s["flat_not_in_hybrid"] == []
    )
    assert s["flat_graph_components_admitted"] == 0
    assert s["entity_resolution"] == {
        "mean_hit_rate": 0.5,
        "questions_with_no_entity": 2,
    }  # q3 resolved none; q4 had no record


def test_the_summary_notices_a_flat_layer_that_admitted_a_graph_component():
    rows = [row("q1", rich_graph(3), 1.0)]
    rows[0]["layers"]["flat"]["admission"]["GraphView"]["admitted"] = True  # as if the invariant were broken
    assert summarise(rows)["flat_graph_components_admitted"] == 1


# ── the guards ────────────────────────────────────────────────────────────────


def test_mismatched_store_hashes_are_refused():
    actual = {"graph_sha256": "a", "vectors_sha256": "b", "chunks_sha256": "c"}
    require_expected_hashes(actual, {"graph_sha256": "a", "vectors_sha256": None, "chunks_sha256": "c"})
    with pytest.raises(RunInvalid, match="graph_sha256"):
        require_expected_hashes(actual, {"graph_sha256": "x", "vectors_sha256": "b", "chunks_sha256": "c"})


def study_argv(argv, tmp: Path, *extra: str) -> list[str]:
    """The runner's argument list, re-pointed at the study's own flags and output."""
    base = argv()
    keep = [
        base[i] for i in range(len(base)) if base[i] in ("--questions-file", "--manifest", "--gold-dir", "--data-dir")
    ]
    pairs = []
    for flag in keep:
        pairs += [flag, base[base.index(flag) + 1]]
    return [*pairs, "--out", str(tmp / "bound-results"), *extra]


def test_a_run_on_a_dirty_tree_is_refused(bench, monkeypatch, capsys):
    argv, tmp = bench
    monkeypatch.setattr(bound, "git_state", lambda: {"commit": "abc", "dirty": True, "changed_files": [" M api/x.py"]})
    assert main(study_argv(argv, tmp, "--allow-unpinned", "--allow-unfrozen")) == 2
    assert "committed, clean tree" in capsys.readouterr().err


def test_a_live_configuration_is_refused_without_allow_paid(bench, monkeypatch, capsys):
    argv, tmp = bench
    real = bound.load_settings()
    monkeypatch.setattr(bound, "load_settings", lambda: real.model_copy(update={"arcana_embed_mode": "live"}))
    assert main(study_argv(argv, tmp, "--allow-dirty", "--allow-unpinned", "--allow-unfrozen")) == 2
    assert "--allow-paid" in capsys.readouterr().err
    assert not (tmp / "data").exists() or not list((tmp / "data").glob("*.json"))


def test_a_run_without_pinned_store_hashes_is_refused(bench, capsys):
    argv, tmp = bench
    assert main(study_argv(argv, tmp, "--allow-dirty", "--allow-unfrozen")) == 2
    assert "--expect-graph-sha256" in capsys.readouterr().err


def test_a_run_with_no_stores_is_refused_and_never_ingests(bench, capsys):
    argv, tmp = bench
    assert main(study_argv(argv, tmp, "--allow-dirty", "--allow-unpinned", "--allow-unfrozen")) == 2
    assert "never ingests" in capsys.readouterr().err
    assert not (tmp / "data" / "graph.json").exists()


def test_a_run_with_the_wrong_hash_is_refused(bench, capsys):
    from eval.run_ablation import main as ingest

    argv, tmp = bench
    assert ingest(argv("--questions", "q-1", "--arms", "hybrid")) == 0  # builds the stores in tmp/data
    code = main(
        study_argv(
            argv,
            tmp,
            "--allow-dirty",
            "--allow-unfrozen",
            "--expect-graph-sha256",
            "0" * 64,
            "--expect-vectors-sha256",
            "0" * 64,
            "--expect-chunks-sha256",
            "0" * 64,
        )
    )
    assert code == 2 and "stores differ" in capsys.readouterr().err


# ── a whole run, in fake mode, on the fixture paper ───────────────────────────


def test_a_run_writes_every_question_by_both_layers_and_flat_admits_only_the_two_components(bench):
    from eval.run_ablation import main as ingest

    argv, tmp = bench
    assert ingest(argv("--questions", "q-1,q-2", "--arms", "hybrid")) == 0
    assert main(study_argv(argv, tmp, "--allow-dirty", "--allow-unfrozen", "--allow-unpinned", "--label", "study")) == 0
    (path,) = list((tmp / "bound-results").glob("*.json"))
    out = json.loads(path.read_text(encoding="utf-8"))
    assert [r["question_id"] for r in out["results"]] == ["q-1", "q-2", "q-3"]
    for r in out["results"]:
        assert set(r["layers"]) == {"flat", "hybrid"}
        flat_admitted = {n for n, a in r["layers"]["flat"]["admission"].items() if a["admitted"]}
        assert flat_admitted <= FLAT_ADMITS  # flat admits only the answer and the source list
        for layer in r["layers"].values():
            assert all(isinstance(a["reasons"], list) for a in layer["admission"].values())
    run = out["run"]
    assert run["study"]["research_agent"] is False and run["study"]["model_calls"] == 0
    assert set(run["hashes"]) == {"questions_sha256", "graph_sha256", "vectors_sha256", "chunks_sha256"}
    assert run["code"]["commit"] and "dirty" in run["code"] and run["ledger"]["new_purposes"] == []
    assert out["summary"]["flat_graph_components_admitted"] == 0
    assert "Not a quality score" in run["limits"]
    assert {name for name in run["templates"]} == set(CATALOG)
