"""Runner findings of the pre-benchmark retrieval audit (2026-10-06): the paid run checks the freeze, names
its code, keeps ingestion facts across invocations, and refuses stores that are not the expected ones."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.ingestion.types import doc_id_for
from eval import frozen, run_ablation
from eval.run_ablation import (
    RunInvalid,
    chunks_sha256,
    load_ingestion_report,
    require_expected_hashes,
    require_extraction_quality,
    require_store_matches_manifest,
    save_ingestion_report,
)

EVAL = Path(__file__).resolve().parents[1]


def test_a_live_run_on_uncommitted_code_is_refused_but_a_fake_run_is_not(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run_ablation, "git_state", lambda: {"commit": "abc", "dirty": True, "changed_files": [" M api/x.py"]})
    with pytest.raises(RunInvalid, match="committed, clean"):
        run_ablation.require_clean_code(live=True, allow_dirty=False)
    assert run_ablation.require_clean_code(live=True, allow_dirty=True)["dirty"] is True  # allowed, and recorded
    assert run_ablation.require_clean_code(live=False, allow_dirty=False)["commit"] == "abc"
    monkeypatch.setattr(run_ablation, "git_state", lambda: {"commit": None, "dirty": None, "changed_files": []})
    with pytest.raises(RunInvalid):  # no git at all: a live result could not name its code
        run_ablation.require_clean_code(live=True, allow_dirty=False)


def test_git_state_names_a_full_commit_hash_and_lists_changes():
    state = run_ablation.git_state()
    assert state["commit"] is None or len(state["commit"]) == 40
    assert isinstance(state["changed_files"], list)


def test_the_environment_block_records_versions_and_parameters():
    env = run_ablation.environment()
    assert env["embedding_model"] == "text-embedding-3-large" and env["extraction_max_tokens"] == 2048
    assert env["chunk_boundary_lookback"] == 200 and env["python"].startswith("3.")


def test_ingestion_facts_survive_into_a_later_invocation_that_only_reuses_the_documents(tmp_path: Path):
    first = [
        {"arxiv_id": "a", "doc_id": "da", "status": "ready", "chunks": 100, "nodes": 50, "edges": 70,
         "extraction_failures": 2, "ingested_now": True}
    ]
    save_ingestion_report(tmp_path, first, {})
    saved = load_ingestion_report(tmp_path)
    assert saved["a"]["nodes"] == 50 and saved["a"]["extraction_failures"] == 2
    reused = [
        {"arxiv_id": "a", "doc_id": "da", "status": "ready", "chunks": 100, "nodes": saved["a"]["nodes"],
         "edges": saved["a"]["edges"], "extraction_failures": saved["a"]["extraction_failures"], "ingested_now": False}
    ]
    require_extraction_quality(reused)
    save_ingestion_report(tmp_path, reused, saved)
    assert load_ingestion_report(tmp_path)["a"]["edges"] == 70  # not overwritten by a reuse


def test_a_reused_document_with_a_high_earlier_failure_rate_is_still_refused():
    reused = [{"arxiv_id": "a", "status": "ready", "chunks": 100, "extraction_failures": 20, "ingested_now": False}]
    with pytest.raises(RunInvalid, match="failed extraction"):
        require_extraction_quality(reused)


async def test_ensure_corpus_fills_reused_documents_from_the_saved_report(tmp_path: Path):
    corpus = tmp_path / "c"
    corpus.mkdir()
    raw = b"%PDF-1.4 same bytes"
    (corpus / "p.pdf").write_bytes(raw)
    stored = SimpleNamespace(status="ready")
    container = SimpleNamespace(
        docs=SimpleNamespace(get_document=lambda _i: stored, chunks_for_document=lambda _i: [1, 2, 3]), ingest_deps=None
    )
    manifest = [{"arxiv_id": "a", "file": "p.pdf"}]
    saved = {"a": {"doc_id": doc_id_for(raw), "nodes": 9, "edges": 8, "extraction_failures": 1}}
    (report,) = await run_ablation.ensure_corpus(container, manifest, corpus, False, saved)  # pyright: ignore[reportArgumentType]
    assert (report["nodes"], report["edges"], report["extraction_failures"], report["ingested_now"]) == (9, 8, 1, False)
    other = {"a": {"doc_id": "a-different-document", "nodes": 1, "edges": 1, "extraction_failures": 0}}
    (stale,) = await run_ablation.ensure_corpus(container, manifest, corpus, False, other)  # pyright: ignore[reportArgumentType]
    assert stale["nodes"] is None  # saved facts belong to different bytes: not used


def test_stores_must_hold_exactly_the_manifests_documents():
    ingestion = [{"doc_id": "d1"}, {"doc_id": "d2"}]
    require_store_matches_manifest({"d1", "d2"}, ingestion)
    with pytest.raises(RunInvalid, match=r"unexpected.*stale"):
        require_store_matches_manifest({"d1", "d2", "stale"}, ingestion)
    with pytest.raises(RunInvalid, match=r"missing.*d2"):
        require_store_matches_manifest({"d1"}, ingestion)


def test_expected_store_hashes_are_enforced_only_when_given():
    actual = {"graph_sha256": "g1", "vectors_sha256": "v1", "chunks_sha256": "c1"}
    require_expected_hashes(actual, {"graph_sha256": None, "vectors_sha256": "v1", "chunks_sha256": None})
    with pytest.raises(RunInvalid, match="graph_sha256"):
        require_expected_hashes(actual, {"graph_sha256": "other", "vectors_sha256": None, "chunks_sha256": None})


def test_the_chunk_hash_is_content_based_and_order_independent():
    a, b = SimpleNamespace(id="1", text="alpha"), SimpleNamespace(id="2", text="beta")
    assert chunks_sha256([a, b]) == chunks_sha256([b, a])
    assert chunks_sha256([a, b]) != chunks_sha256([a, SimpleNamespace(id="2", text="beta!")])


def test_entity_resolution_is_summarised_per_graph_arm_so_a_hub_only_graph_shows():
    def row(hit: float, exact: int, entities: int) -> dict:
        res = {"hit_rate": hit, "exact_hit_rate": hit, "n_exact": exact, "entities": [None] * entities}
        return {"invalid": False, "resolution": res}

    results = [
        {"arms": {"hybrid": row(0.5, 1, 1), "dense": {"invalid": False}}},
        {"arms": {"hybrid": row(0.0, 0, 0), "dense": {"invalid": False}}},
    ]
    out = run_ablation.resolution_summary(results, ["dense", "hybrid"])
    assert list(out) == ["hybrid"]  # arms without the graph signal have no resolution
    assert out["hybrid"] == {
        "questions": 2, "mean_hit_rate": 0.25, "mean_exact_hit_rate": 0.25,
        "fraction_with_an_exact_entity": 0.5, "fraction_with_any_entity": 0.5,
    }


def test_the_frozen_check_passes_on_the_real_assets_and_names_each_drift(tmp_path: Path):
    ids = ["q-cross-01", "q-single-02"]
    questions, manifest, gold_dir = EVAL / "questions.yaml", EVAL / "corpus" / "MANIFEST.json", EVAL / "gold"
    assert frozen.check_frozen(questions, manifest, gold_dir, ids) == []

    gold = tmp_path / "gold"
    shutil.copytree(gold_dir, gold)
    edited = (gold / "q-cross-01.yaml").read_text(encoding="utf-8").replace("hybrid", "hybrid ")
    (gold / "q-cross-01.yaml").write_text(edited, encoding="utf-8")
    problems = frozen.check_frozen(questions, manifest, gold, ids)
    assert len(problems) == 1 and "q-cross-01" in problems[0] and "edited after approval" in problems[0]

    changed_questions = tmp_path / "questions.yaml"
    changed_questions.write_bytes(questions.read_bytes() + b"\n- extra\n")
    assert any("question set" in p for p in frozen.check_frozen(changed_questions, manifest, gold_dir, ids))

    # an unapproved file is require_approved_gold's to report, not a pin mismatch
    assert frozen.check_frozen(questions, manifest, gold_dir, ["q-single-01"]) == []


def test_the_frozen_check_names_a_changed_protocol_stamp(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(frozen, "stamp_sha256", lambda: "0" * 64)
    problems = frozen.check_frozen(EVAL / "questions.yaml", EVAL / "corpus" / "MANIFEST.json", EVAL / "gold", [])
    assert problems and "protocol stamp changed" in problems[0]
