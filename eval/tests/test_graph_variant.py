"""The graph-variant tool (G1.3 to G1.5): slice the baseline, rebuild a graph beside it, compare. All on fakes, no spend."""

# ruff: noqa: F811  (the `bench` fixture is imported from test_runner and used by name)

import asyncio
import json
from pathlib import Path

import pytest

from api.tests.fixtures import make_fixture_pdf
from eval import graph_variant
from eval.graph_variant import (
    MAX_NDCG_DROP,
    main,
    paired,
    rebuild_graph,
    registered_gate,
    slice_stores,
)
from eval.run_ablation import RunInvalid, load_ingestion_report
from eval.run_ablation import main as ingest
from eval.tests.test_runner import bench  # noqa: F401  (a tiny fake-mode benchmark world)

FIRST, SECOND = "0000.00000v1", "0000.00000v2"


@pytest.fixture
def two_papers(bench, monkeypatch):
    """The benchmark world with a second paper added to the corpus and the baseline stores ingested."""
    argv, tmp = bench
    other = tmp / "corpus" / "second.pdf"
    monkeypatch.setattr(make_fixture_pdf, "TITLE", "A Second Paper on Retrieval")
    monkeypatch.setattr(
        make_fixture_pdf,
        "PAGES",
        [
            "Second Paper. Cross Encoders rerank passages that Dense Retrieval returns. Cross Encoders are slow but exact."
        ],
    )
    make_fixture_pdf.build(other)
    manifest = tmp / "MANIFEST.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(
        json.dumps([*entries, {"arxiv_id": SECOND, "title": "Second", "file": "second.pdf"}]), encoding="utf-8"
    )
    assert ingest(argv("--questions", "q-1", "--arms", "hybrid")) == 0
    return argv, tmp, tmp / "data"


def test_a_slice_keeps_only_the_named_papers_and_still_passes_the_parity_check(two_papers):
    _, tmp, data = two_papers
    info = slice_stores(data, tmp / "slice", [FIRST])
    assert (
        info["documents"] == 1
        and info["chunks"] > 0
        and set(info["hashes"])
        == {
            "graph_sha256",
            "vectors_sha256",
            "chunks_sha256",
        }
    )
    assert [d["arxiv_id"] for d in load_ingestion_report(tmp / "slice").values()] == [FIRST]
    from api.container import build_container
    from eval.graph_variant import settings_for

    sliced = build_container(settings_for(tmp / "slice"))
    full = build_container(settings_for(data))
    assert len(sliced.docs.list_documents()) == 1 and len(full.docs.list_documents()) == 2  # the source is untouched
    assert sliced.vectors.count() < full.vectors.count() and sliced.graph.nodes()


def test_a_slice_is_refused_into_a_non_empty_directory_or_for_an_unknown_paper(two_papers):
    _, tmp, data = two_papers
    (tmp / "taken").mkdir()
    (tmp / "taken" / "x").write_text("x", encoding="utf-8")
    with pytest.raises(RunInvalid, match="not empty"):
        slice_stores(data, tmp / "taken", [FIRST])
    with pytest.raises(RunInvalid, match="not in"):
        slice_stores(data, tmp / "other", ["9999.99999v1"])


def build_variant(tmp: Path, data: Path, max_usd: float = 1.0) -> dict:
    slice_stores(data, tmp / "slice", [FIRST])
    return asyncio.run(rebuild_graph(tmp / "slice", tmp / "variant", "atomic", max_usd, allow_paid=False))


def test_a_rebuild_changes_only_the_graph_and_records_its_builder_cost_and_hashes(two_papers):
    _, tmp, data = two_papers
    info = build_variant(tmp, data)
    assert (
        info["builder"] == "atomic" and info["prompt_version"] and info["complete"] is True and info["spent_usd"] == 0.0
    )
    base, variant = tmp / "slice", tmp / "variant"
    assert (base / "vectors.npz").read_bytes() == (variant / "vectors.npz").read_bytes()  # identical vectors
    from api.container import build_container

    docs = {d: build_container(graph_variant.settings_for(d)).docs.all_chunks() for d in (base, variant)}
    assert [(c.id, c.text) for c in docs[base]] == [(c.id, c.text) for c in docs[variant]]  # identical documents
    assert (base / "graph.json").read_bytes() != (variant / "graph.json").read_bytes()
    report = json.loads((variant / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report[0]["build_report"]["builder"] == "atomic" and report[0]["extraction_failures"] == 0
    saved = json.loads((variant / "variant.json").read_text(encoding="utf-8"))
    assert saved["max_usd"] == 1.0 and saved["graph_sha256"] and saved["code"]["commit"] is not None
    from api.stores.local.networkx_graph import NetworkXGraphStore

    nodes = NetworkXGraphStore(variant / "graph.json").nodes()
    assert nodes and all(n.note and n.kind for n in nodes)  # the notes are real, every one with its sentence


def test_a_rebuild_is_refused_into_a_non_empty_directory_without_a_ceiling_and_stops_at_the_ceiling(two_papers):
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])
    (tmp / "busy").mkdir()
    (tmp / "busy" / "x").write_text("x", encoding="utf-8")
    with pytest.raises(RunInvalid, match="not empty"):
        asyncio.run(rebuild_graph(tmp / "slice", tmp / "busy", "atomic", 1.0, False))
    with pytest.raises(RunInvalid, match="ceiling"):
        asyncio.run(rebuild_graph(tmp / "slice", tmp / "zero", "atomic", 0.0, False))
    info = asyncio.run(rebuild_graph(tmp / "slice", tmp / "capped", "atomic", 0.000001, False))
    assert (
        info["complete"] is False and info["spent_usd"] == 0.0
    )  # nothing was sent: the next paper would pass the ceiling
    report = json.loads((tmp / "capped" / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report[0]["status"] == "not_built_ceiling"


# ── compare ───────────────────────────────────────────────────────────────────


def test_compare_writes_the_paired_numbers_the_structure_and_the_registered_gate(two_papers):
    argv, tmp, data = two_papers
    build_variant(tmp, data)
    out = tmp / "cmp"
    base = argv()
    flags = [base[i + 1] for i, a in enumerate(base) if a == "--questions-file"] + [
        base[i + 1] for i, a in enumerate(base) if a == "--gold-dir"
    ]
    code = main(
        [
            "compare",
            "--baseline",
            str(tmp / "slice"),
            "--variant",
            str(tmp / "variant"),
            "--questions-file",
            flags[0],
            "--gold-dir",
            flags[1],
            "--out",
            str(out),
            "--allow-dirty",
            "--label",
            "t",
        ]
    )
    assert code == 0
    (path,) = out.glob("*-t.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    run = result["run"]
    assert run["answerable_questions"] == ["q-1"] and run["descriptive_only"] is True
    assert {s["question_id"] for s in run["skipped_questions"]} == {"q-2", "q-3"}
    assert run["control_arm_flat_differs"] is False  # the flat arm has no graph: it must not differ between the two
    assert run["warning"] and "FAKE MODE" in run["warning"] and "Primary" in run["protocol"]
    assert run["hashes"]["baseline_graph_sha256"] != run["hashes"]["variant_graph_sha256"]
    assert set(result["structure"]) == {"baseline", "variant"} and result["structure"]["variant"]["edges"] >= 0
    summary = result["retrieval"]["summary"]
    assert set(summary) == {"graph", "hybrid", "flat"} and summary["flat"]["ndcg_at_10"]["mean_difference"] == 0.0
    assert set(result["gate"]) == {"structural_no_regression", "no_large_retrieval_drop"}


def test_compare_refuses_directories_that_do_not_hold_the_same_corpus_and_vectors(two_papers, capsys):
    argv, tmp, data = two_papers
    build_variant(tmp, data)
    (tmp / "variant" / "vectors.npz").write_bytes(b"not the same vectors")
    base = argv()
    code = main(
        [
            "compare",
            "--baseline",
            str(tmp / "slice"),
            "--variant",
            str(tmp / "variant"),
            "--questions-file",
            base[base.index("--questions-file") + 1],
            "--gold-dir",
            base[base.index("--gold-dir") + 1],
            "--out",
            str(tmp / "cmp"),
            "--allow-dirty",
        ]
    )
    assert code == 2 and "refused" in capsys.readouterr().err


def test_a_command_run_on_a_dirty_tree_is_refused(two_papers, monkeypatch, capsys):
    _, tmp, data = two_papers
    monkeypatch.setattr(graph_variant, "git_state", lambda: {"commit": "abc", "dirty": True, "changed_files": [" M x"]})
    assert main(["compare", "--baseline", str(data), "--variant", str(data), "--out", str(tmp / "o")]) == 2
    assert "commit first" in capsys.readouterr().err


# ── the arithmetic and the registered gate, by hand ───────────────────────────


def row(a: float | None, b: float | None, invalid: bool = False) -> dict:
    cell = lambda v: {"ndcg_at_10": v, "recall_at_10": v, "invalid": invalid}  # noqa: E731
    return {"baseline": {"hybrid": cell(a)}, "variant": {"hybrid": cell(b)}}


def test_paired_differences_counts_and_means_are_what_they_should_be():
    rows = [row(0.5, 0.75), row(0.5, 0.5), row(0.75, 0.25), row(None, 0.9), row(0.5, 0.5, invalid=True)]
    p = paired(rows, "hybrid", "ndcg_at_10")
    assert p["pairs"] == 3  # the missing metric and the invalid arm are not pairs
    assert (p["improved"], p["tied"], p["worsened"]) == (1, 1, 1)
    assert p["mean_difference"] == pytest.approx(-0.0833, abs=1e-4)
    assert paired([], "hybrid", "ndcg_at_10")["mean_difference"] is None


def metrics_of(stated: float, relations: int, shared: float) -> dict:
    return {
        "edges_stated_in_one_sentence": {"share": stated},
        "distinct_relations": relations,
        "nodes_in_two_or_more_documents": {"share": shared},
    }


def test_the_registered_gate_needs_all_three_structural_conditions_and_a_small_enough_retrieval_drop():
    base = metrics_of(0.35, 100, 0.10)
    ok = registered_gate(base, metrics_of(0.60, 40, 0.15), {"mean_difference": 0.0})
    assert ok["structural_no_regression"]["passed"] and ok["no_large_retrieval_drop"]["passed"]
    for worse in (metrics_of(0.30, 40, 0.15), metrics_of(0.60, 120, 0.15), metrics_of(0.60, 40, 0.05)):
        assert not registered_gate(base, worse, {"mean_difference": 0.0})["structural_no_regression"]["passed"]
    edge = registered_gate(base, metrics_of(0.6, 40, 0.15), {"mean_difference": -MAX_NDCG_DROP})
    assert edge["no_large_retrieval_drop"]["passed"]  # exactly at the threshold is allowed
    below = registered_gate(base, metrics_of(0.6, 40, 0.15), {"mean_difference": -MAX_NDCG_DROP - 0.01})
    assert not below["no_large_retrieval_drop"]["passed"]
    assert registered_gate(base, metrics_of(0.6, 40, 0.15), {"mean_difference": None})["no_large_retrieval_drop"][
        "passed"
    ]


def test_the_protocol_is_in_the_module_text_so_it_travels_with_every_result():
    doc = graph_variant.__doc__ or ""
    for phrase in ("PROTOCOL", "Registered", "-0.05", "DESCRIPTIVE", "Spend", "never touched"):
        assert phrase in doc or phrase.lower() in doc.lower()
