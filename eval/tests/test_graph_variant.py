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
    assert set(result["gate"]) == {
        "structural_no_regression",
        "no_large_retrieval_drop",
        "graph_arm_valid",
        "ready_for_azim_to_decide",
        "reported_not_gating",
    }
    assert result["gate"]["no_large_retrieval_drop"]["status"] == "not_evaluable"  # one question: descriptive only
    assert set(result["resolution"]) == {"baseline", "variant"} and "graph_arm_valid" in result


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


def metrics_of(coverage: float, top10: float, top_percent: float, **extra) -> dict:
    base = {
        "chunk_coverage": {"with_a_concept": coverage},
        "hub_concentration": {"top10_degree_share": top10, "top_1_percent_share_of_chunk_links": top_percent},
        "edges_stated_in_one_sentence": {"share": 0.35},
        "distinct_relations": 100,
        "nodes_in_two_or_more_documents": {"share": 0.1},
        "edges_per_node": 1.2,
        "nodes_with_no_edge": {"share": 0.2},
        "nodes_label_in_own_chunks": {"share": 0.86},
    }
    return base | extra


def gate(variant: dict, hybrid: float | None = 0.0, graph: float | None = 0.0, **kw) -> dict:
    options = {"descriptive_only": False, "graph_arm_valid": True} | kw
    return registered_gate(
        metrics_of(0.90, 0.20, 0.30), variant, {"mean_difference": hybrid}, {"mean_difference": graph}, **options
    )


def test_the_registered_gate_needs_both_structural_conditions_and_not_the_degree_share_a_sparse_graph_raises():
    ok = gate(metrics_of(0.80, 0.20, 0.30))  # exactly 0.8 of the baseline's coverage, no more concentrated
    assert ok["structural_no_regression"]["passed"] and ok["ready_for_azim_to_decide"]
    for worse in (metrics_of(0.71, 0.20, 0.30), metrics_of(0.90, 0.20, 0.31)):
        got = gate(worse)
        assert not got["structural_no_regression"]["passed"] and not got["ready_for_azim_to_decide"]
    sparse = gate(
        metrics_of(0.90, 0.60, 0.30)
    )  # the ten largest nodes own far more of a graph with few edges: reported only
    assert sparse["structural_no_regression"]["passed"] and sparse["reported_not_gating"]["hub_concentration"]
    assert (
        gate(metrics_of(0.71, 0.20, 0.30))["structural_no_regression"]["concept_coverage_at_least_0_8_of_baseline"]
        is False
    )


def test_the_measures_a_sentence_checking_builder_passes_by_construction_are_reported_but_cannot_pass_or_fail_the_gate():
    easy = metrics_of(0.90, 0.20, 0.30, edges_stated_in_one_sentence={"share": 1.0}, distinct_relations=14)
    hard = metrics_of(0.90, 0.20, 0.30, edges_stated_in_one_sentence={"share": 0.0}, distinct_relations=5000)
    assert gate(easy)["structural_no_regression"]["passed"] and gate(hard)["structural_no_regression"]["passed"]
    reported = gate(easy)["reported_not_gating"]
    assert reported["edges_stated_in_one_sentence"]["variant"] == {"share": 1.0} and "distinct_relations" in reported


def test_the_retrieval_clause_reads_both_arms_is_not_evaluable_when_descriptive_and_never_passes_on_nothing():
    good = metrics_of(0.9, 0.2, 0.3)
    assert (
        gate(good, hybrid=-MAX_NDCG_DROP, graph=0.1)["no_large_retrieval_drop"]["status"] == "passed"
    )  # at the threshold
    below = gate(good, hybrid=0.0, graph=-MAX_NDCG_DROP - 0.01)  # the graph arm alone fell too far
    assert below["no_large_retrieval_drop"]["status"] == "failed" and not below["ready_for_azim_to_decide"]
    assert (
        gate(good, hybrid=-0.5, graph=-0.5, descriptive_only=True)["no_large_retrieval_drop"]["status"]
        == "not_evaluable"
    )
    assert gate(good, hybrid=-0.5, descriptive_only=True)[
        "ready_for_azim_to_decide"
    ]  # the decision does not rest on it
    assert (
        gate(good, hybrid=None, graph=None)["no_large_retrieval_drop"]["status"] == "passed"
    )  # no pairs, nothing worse
    assert not gate(good, graph_arm_valid=False)["ready_for_azim_to_decide"]  # an invalid graph arm is never ready


def cell(ranking: int, hit: float | None = 0.5, entities: int = 1) -> dict:
    resolution = None if hit is None else {"hit_rate": hit, "exact_hit_rate": hit, "entities": [object()] * entities}
    return {"invalid": False, "ranking_length": ranking, "resolution": resolution}


def test_the_resolution_report_counts_questions_with_an_empty_graph_ranking_and_the_hit_rate():
    rows = [
        {"variant": {"graph": cell(10, 1.0)}},
        {"variant": {"graph": cell(0, 0.0, 0)}},
        {"variant": {"graph": cell(0, None)}},
    ]
    report = graph_variant.resolution_report(rows, "variant")
    assert report["questions"] == 3 and report["graph_ranking_empty"] == 2
    assert report["mean_hit_rate"] == 0.5 and report["fraction_with_any_entity"] == 0.3333


def test_a_graph_arm_is_invalid_when_it_returns_nothing_for_more_than_half_of_the_answerable_questions():
    assert graph_variant.graph_arm_is_valid({"questions": 4, "graph_ranking_empty": 2})  # exactly half is allowed
    assert not graph_variant.graph_arm_is_valid({"questions": 4, "graph_ranking_empty": 3})
    assert graph_variant.graph_arm_is_valid({"questions": 0, "graph_ranking_empty": 0})  # nothing to judge


def test_compare_refuses_a_control_that_differs_between_the_directories(two_papers, monkeypatch, capsys):
    argv, tmp, data = two_papers
    build_variant(tmp, data)
    base = argv()
    args = [
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
    original = graph_variant.run_arm
    flat_calls = {"n": 0}

    async def tampered(arm, question, retrievers, *rest):
        entry = await original(arm, question, retrievers, *rest)
        if arm == "flat":
            flat_calls["n"] += 1
            if flat_calls["n"] % 2 == 0:  # the second flat call of a question is the variant's
                entry["chunk_ids"] = ["tampered", *entry["chunk_ids"]]
        return entry

    monkeypatch.setattr(graph_variant, "run_arm", tampered)
    assert main(args) == 2 and "flat control" in capsys.readouterr().err
    assert not list((tmp / "cmp").glob("*.json")) if (tmp / "cmp").exists() else True  # nothing was written


def test_the_choose_rule_picks_papers_by_newly_answerable_questions_per_chunk_within_the_budget(two_papers):
    argv, _, data = two_papers
    base = argv()
    out = graph_variant.choose_papers(
        data, Path(base[base.index("--questions-file") + 1]), Path(base[base.index("--gold-dir") + 1])
    )
    assert out["papers"] == [FIRST] and out["answerable_questions"] == ["q-1"]  # only the first paper holds gold
    assert out["questions_never_answerable_in_this_budget"] == ["q-2", "q-3"]
    tiny = graph_variant.choose_papers(
        data, Path(base[base.index("--questions-file") + 1]), Path(base[base.index("--gold-dir") + 1]), budget=1
    )
    assert tiny["papers"] == [] and tiny["chunks"] == 0  # nothing fits a one-chunk budget


def test_the_audit_sample_is_seeded_blind_and_keeps_the_key_apart(two_papers):
    _, tmp, data = two_papers
    build_variant(tmp, data)
    items, key = graph_variant.audit_sample(tmp / "slice", tmp / "variant", 3, 7)
    again, key_again = graph_variant.audit_sample(tmp / "slice", tmp / "variant", 3, 7)
    assert items == again and key == key_again  # the same seed gives the same sample
    assert all(
        "graph" not in item and item["relation_supported"] is None for item in items
    )  # the reader cannot see which
    assert set(key.values()) == {"baseline", "variant"} and len(key) == len(items) <= 6
    assert "relation supported" in graph_variant.audit_markdown(items)
    other, _ = graph_variant.audit_sample(tmp / "slice", tmp / "variant", 3, 8)
    assert [i["concept_a"] for i in other] != [i["concept_a"] for i in items] or len(items) < 3


def test_the_protocol_is_in_the_module_text_so_it_travels_with_every_result():
    doc = graph_variant.__doc__ or ""
    for phrase in ("PROTOCOL", "Registered", "-0.05", "DESCRIPTIVE", "Spend", "never touched"):
        assert phrase in doc or phrase.lower() in doc.lower()


def test_the_ceiling_is_enforced_on_every_call_not_only_at_the_start_of_a_document(two_papers, monkeypatch):
    """With the start-of-document projection out of the way, a ceiling below one call's worst case still stops the build
    before the first request is sent: the document is discarded, the record says why, nothing is compared."""
    monkeypatch.setattr(graph_variant, "EXPECTED_PER_CHUNK_USD", 0.0)
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])
    info = asyncio.run(rebuild_graph(tmp / "slice", tmp / "tight", "atomic", 0.01, allow_paid=False))
    assert info["complete"] is False
    report = json.loads((tmp / "tight" / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report[0]["status"] == "not_built_ceiling" and report[0].get("nodes") is None
    from api.stores.local.networkx_graph import NetworkXGraphStore

    assert NetworkXGraphStore(tmp / "tight" / "graph.json").nodes() == []  # the half-built document left nothing behind


def test_the_guard_refuses_a_call_that_could_pass_the_ceiling_and_counts_calls_in_flight():
    from types import SimpleNamespace

    from api.llm.types import LLMRequest

    class Inner:
        def __init__(self):
            self._ledger = SimpleNamespace(month_total=lambda: 0.0)
            self.calls = 0

        def remaining_usd(self):
            return None

        async def complete(self, request, budget=None):
            self.calls += 1
            return "ok"

    request = LLMRequest(prompt="p", system="s", purpose="extract", tier="light", max_tokens=1000)
    inner = Inner()
    guard = graph_variant.CeilingGuard(inner, 0.0, 0.0061)  # type: ignore[arg-type]  # one call is $0.0050 at 1,000 output tokens, plus the input
    assert asyncio.run(guard.complete(request)) == "ok" and inner.calls == 1  # alone it fits
    tight = graph_variant.CeilingGuard(inner, 0.0, 0.004)  # type: ignore[arg-type]
    with pytest.raises(graph_variant.CeilingReached):
        asyncio.run(tight.complete(request))
    assert inner.calls == 1  # refused before sending


def test_compare_refuses_a_variant_with_no_complete_rebuild_record(two_papers, capsys):
    argv, tmp, data = two_papers
    build_variant(tmp, data)
    record = tmp / "variant" / "variant.json"
    info = json.loads(record.read_text(encoding="utf-8"))
    info["complete"] = False
    record.write_text(json.dumps(info), encoding="utf-8")
    base = argv()
    args = [
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
    assert main(args) == 2 and "complete rebuild record" in capsys.readouterr().err
    record.unlink()
    assert main(args) == 2


def test_an_interrupted_rebuild_leaves_a_record_that_says_it_is_not_complete(two_papers, monkeypatch):
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])

    async def boom(*_args, **_kwargs):
        raise KeyboardInterrupt  # a hard stop that the tool does not catch

    monkeypatch.setattr(graph_variant, "build_graph", boom)
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(rebuild_graph(tmp / "slice", tmp / "killed", "atomic", 1.0, allow_paid=False))
    record = json.loads((tmp / "killed" / "variant.json").read_text(encoding="utf-8"))
    assert record["complete"] is False and "did not finish" in record["interrupted"]


def test_a_rebuild_that_stopped_on_a_provider_failure_is_resumed_without_repaying_the_finished_paper(two_papers, monkeypatch):
    """The full-corpus run died on one chunk that failed on both provider routes: 14 papers were built and paid for. `--resume` keeps them,
    builds only the rest, and sums the spend; an unfinished record of another builder, or a record with no spend, is refused."""
    from api.core.errors import ProviderUnavailable

    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST, SECOND])
    real = graph_variant.build_graph
    calls = {"n": 0}

    async def fail_on_the_second_paper(chunks, deps):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ProviderUnavailable("both routes failed")
        return await real(chunks, deps)

    monkeypatch.setattr(graph_variant, "build_graph", fail_on_the_second_paper)
    first = asyncio.run(rebuild_graph(tmp / "slice", tmp / "built", "atomic", 5.0, allow_paid=False))
    assert first["complete"] is False
    report = json.loads((tmp / "built" / "ingestion_report.json").read_text(encoding="utf-8"))
    assert [d["status"] for d in report] == ["ready", "not_built_error"]
    with pytest.raises(RunInvalid):  # not allowed without --resume
        asyncio.run(rebuild_graph(tmp / "slice", tmp / "built", "atomic", 5.0, allow_paid=False))
    with pytest.raises(RunInvalid):  # another builder's unfinished build is not continued
        asyncio.run(rebuild_graph(tmp / "slice", tmp / "built", "atomic2", 5.0, allow_paid=False, resume=True))

    monkeypatch.setattr(graph_variant, "build_graph", real)
    finished = asyncio.run(rebuild_graph(tmp / "slice", tmp / "built", "atomic", 5.0, allow_paid=False, resume=True))
    assert finished["complete"] is True and finished["resumed"] is True and finished["papers_kept_from_earlier_run"] == 1
    done = json.loads((tmp / "built" / "ingestion_report.json").read_text(encoding="utf-8"))
    assert [d["status"] for d in done] == ["ready", "ready"]
    assert done[0] == report[0]  # the finished paper is exactly as the first run left it
    assert finished["spent_usd"] == round(first["spent_usd"] + finished["this_run_spent_usd"], 6)
