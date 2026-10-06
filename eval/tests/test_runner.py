"""The ablation runner end to end on the fixture PDF, in fake mode, in a temp directory."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from api.retrieval.graph import GraphRetriever
from api.tests.fixtures.make_fixture_pdf import PAGES
from eval import run_ablation
from eval.run_ablation import RunInvalid, main, summarise

FIXTURE = Path(__file__).resolve().parents[2] / "api" / "tests" / "fixtures" / "hybrid_retrieval.pdf"
QUESTION = "How are ranked lists merged with Reciprocal Rank Fusion?"
# A real passage of page 2 of the fixture: the answer to QUESTION.
PASSAGE = (
    "The three rankings are merged with Reciprocal Rank Fusion. A passage at rank r in a list "
    "contributes one over the sum of a constant k and r, and contributions add across lists."
)


@pytest.fixture
def bench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A tiny benchmark: one paper (the fixture), three questions, gold for one."""
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "LLM_MONTHLY_CAP_USD", "ARCANA_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARCANA_LLM_MODE", "fake")
    monkeypatch.setenv("ARCANA_EMBED_MODE", "fake")
    monkeypatch.chdir(tmp_path)  # so no real .env is read

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shutil.copy(FIXTURE, corpus / "paper.pdf")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps([{"arxiv_id": "0000.00000v1", "title": "T", "file": "paper.pdf"}]), encoding="utf-8")
    questions = tmp_path / "questions.yaml"
    questions.write_text(
        yaml.safe_dump(
            {
                "questions": [
                    {"id": "q-1", "category": "single_document", "question": QUESTION},
                    {"id": "q-2", "category": "cross_document", "question": "What does Dense Retrieval do?"},
                    {"id": "q-3", "category": "single_document", "question": "Something with no gold at all?"},
                ]
            }
        ),
        encoding="utf-8",
    )
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "q-1.yaml").write_text(
        yaml.safe_dump(
            {"question_id": "q-1", "status": "smoke", "reference_contexts": [{"doc_id": "0000.00000v1", "page": 2, "text": PASSAGE}]}
        ),
        encoding="utf-8",
    )
    (gold / "q-2.yaml").write_text(
        yaml.safe_dump({"question_id": "q-2", "status": "unanswerable", "reason": "test", "reference_contexts": []}),
        encoding="utf-8",
    )

    def argv(*extra: str) -> list[str]:
        return [
            "--questions-file", str(questions), "--manifest", str(manifest), "--corpus-dir", str(corpus),
            "--gold-dir", str(gold), "--out", str(tmp_path / "results"), "--data-dir", str(tmp_path / "data"),
            "--label", "test", *extra,
        ]

    return argv, tmp_path


def result_of(tmp_path: Path) -> dict:
    (path,) = list((tmp_path / "results").glob("*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_passage_really_is_in_the_fixture():
    assert PASSAGE in " ".join(PAGES[1].split())


def test_a_run_writes_five_arms_for_every_question(bench):
    argv, tmp = bench
    assert main(argv("--questions", "q-1,q-2", "--arms", "all")) == 0
    out = result_of(tmp)
    assert [r["question_id"] for r in out["results"]] == ["q-1", "q-2"]
    for row in out["results"]:
        assert list(row["arms"]) == ["dense", "sparse", "graph", "flat", "hybrid"]


def test_the_question_with_gold_gets_metrics_and_the_others_get_none_not_zero(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1,q-2,q-3", "--arms", "all"))
    by_id = {r["question_id"]: r for r in result_of(tmp)["results"]}
    answered = by_id["q-1"]["arms"]
    assert by_id["q-1"]["gold_status"] == "smoke" and by_id["q-1"]["n_gold_passages"] == 1
    assert by_id["q-1"]["relevant_chunks_in_corpus"] >= 1
    assert answered["hybrid"]["recall_at_10"] == 1.0  # the passage's chunk is among the four retrieved
    assert 0.0 < answered["hybrid"]["ndcg_at_10"] <= 1.0
    for qid, status in (("q-2", "unanswerable"), ("q-3", "missing")):
        assert by_id[qid]["gold_status"] == status
        for arm in by_id[qid]["arms"].values():
            assert arm["recall_at_10"] is None and arm["ndcg_at_10"] is None  # undefined, never 0.0


def test_every_arm_records_ranking_length_latency_and_the_graph_resolution(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1", "--arms", "all"))
    arms = result_of(tmp)["results"][0]["arms"]
    for name, arm in arms.items():
        assert 0 < arm["ranking_length"] <= 10 and arm["latency_ms"] >= 0 and arm["invalid"] is False
        has_graph = name in {"graph", "hybrid"}
        assert (arm["resolution"] is not None) == has_graph
        assert (arm["graph_ranking_empty"] is not None) == has_graph
    hybrid = arms["hybrid"]["resolution"]
    assert {"hit_rate", "exact_hit_rate", "n_exact", "n_approx", "entities"} <= set(hybrid)


def test_the_run_is_tied_to_what_produced_it(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1", "--arms", "hybrid"))
    run = result_of(tmp)["run"]
    assert run["protocol"]["rrf_k"] == 60 and run["protocol"]["graph"]["scoring_version"]
    assert run["relevance_rule"] == {"shingle_n": 5, "min_coverage": 0.3, "k": 10, "tokenizer": "api.retrieval.sparse.tokenize"}
    for key in ("questions_sha256", "manifest_sha256", "graph_sha256", "vectors_sha256"):
        assert len(run["hashes"][key]) == 64
    assert set(run["hashes"]["gold_sha256"]) == {"q-1"}
    assert run["corpus"]["parity_problems"] == [] and run["corpus"]["chunks"] == 4
    assert run["mode"] == {"llm": "fake", "embed": "fake"} and "FAKE MODE" in run["warning"]
    assert run["extraction_model"] == "fake"


def test_ragas_metrics_are_null_with_a_reason_when_ragas_is_not_installed(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1", "--arms", "hybrid"))
    out = result_of(tmp)
    arm = out["results"][0]["arms"]["hybrid"]
    if out["run"]["ragas"]["available"]:
        pytest.skip("ragas is installed here; the null path does not apply")
    assert out["run"]["ragas"]["reason"].startswith("not installed")
    assert arm["ragas_context_recall"] is None and arm["ragas_context_precision"] is None


def test_each_question_embedding_is_computed_once_however_many_arms_use_it(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1,q-2,q-3", "--arms", "all"))
    # dense, flat and hybrid all embed the query; the cache makes it one embedding per question
    assert result_of(tmp)["run"]["query_embeddings_computed"] == 3


def test_the_second_run_reuses_the_ingested_corpus_and_gives_the_same_ranking(bench):
    argv, tmp = bench
    main(argv("--questions", "q-1", "--arms", "hybrid"))
    first = result_of(tmp)
    for p in (tmp / "results").glob("*.json"):
        p.rename(tmp / "first.json")
    main(argv("--questions", "q-1", "--arms", "hybrid"))
    second = result_of(tmp)
    assert [d["ingested_now"] for d in first["run"]["corpus"]["documents"]] == [True]
    assert [d["ingested_now"] for d in second["run"]["corpus"]["documents"]] == [False]
    assert first["results"][0]["arms"]["hybrid"]["chunk_ids"] == second["results"][0]["arms"]["hybrid"]["chunk_ids"]
    assert first["run"]["hashes"]["graph_sha256"] == second["run"]["hashes"]["graph_sha256"]


# ── failures: invalid, refused, gated ────────────────────────────────────────


def test_a_failed_signal_invalidates_the_question_arm_instead_of_scoring_zero(bench, monkeypatch, capsys):
    argv, tmp = bench

    async def broken(self, query, top_k=10):
        raise RuntimeError("graph index corrupt")

    monkeypatch.setattr(GraphRetriever, "retrieve", broken)
    code = main(argv("--questions", "q-1", "--arms", "all"))
    arms = result_of(tmp)["results"][0]["arms"]
    assert code == 3  # a non-zero exit: invalid runs must not look like success
    for name in ("graph", "hybrid"):
        assert arms[name]["invalid"] and arms[name]["failed_signals"] == ["graph"]
        assert arms[name]["recall_at_10"] is None and arms[name]["ndcg_at_10"] is None  # not 0.0
    for name in ("dense", "sparse", "flat"):
        assert not arms[name]["invalid"]
    assert "INVALID" in capsys.readouterr().err


def test_invalid_runs_are_left_out_of_the_aggregates(bench, monkeypatch):
    argv, tmp = bench

    async def broken(self, query, top_k=10):
        raise RuntimeError("boom")

    monkeypatch.setattr(GraphRetriever, "retrieve", broken)
    main(argv("--questions", "q-1", "--arms", "graph,flat"))
    summary = result_of(tmp)["summary"]["per_arm"]
    assert summary["graph"]["invalid"] == 1 and summary["graph"]["mean_recall_at_10"] is None
    assert summary["flat"]["invalid"] == 0 and summary["flat"]["mean_recall_at_10"] is not None


def test_a_parity_problem_refuses_the_run_and_writes_nothing(bench, monkeypatch, capsys):
    argv, tmp = bench
    monkeypatch.setattr(run_ablation, "check_corpus_parity", lambda *a: ["chunks without a vector: c1"])
    assert main(argv("--questions", "q-1")) == 2
    assert "parity" in capsys.readouterr().err and not (tmp / "results").exists()


@pytest.mark.parametrize(
    ("extra", "fragment"),
    [
        (["--questions", "q-nope"], "unknown question"),
        (["--arms", "dense,telepathy"], "unknown arm"),
    ],
)
def test_bad_arguments_refuse_the_run(bench, capsys, extra, fragment):
    argv, _ = bench
    assert main(argv(*extra)) == 2
    assert fragment in capsys.readouterr().err


def test_a_missing_corpus_pdf_refuses_the_run(bench, capsys):
    argv, tmp = bench
    (tmp / "corpus" / "paper.pdf").unlink()
    assert main(argv("--questions", "q-1")) == 2
    assert "corpus PDF missing" in capsys.readouterr().err


def test_live_mode_is_refused_without_allow_paid_and_before_any_provider_is_built(bench, monkeypatch, capsys):
    argv, tmp = bench
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-not-a-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder-not-a-key")
    monkeypatch.setenv("LLM_MONTHLY_CAP_USD", "5")
    assert main(argv("--questions", "q-1")) == 2
    assert "--allow-paid" in capsys.readouterr().err
    assert not (tmp / "data").exists()  # nothing was ingested or created


def _rows(n: int, empty: int) -> list[dict]:
    row = lambda empty_graph: {"arms": {"hybrid": {  # noqa: E731
        "invalid": False, "recall_at_10": 1.0, "ndcg_at_10": 1.0, "ranking_length": 5, "latency_ms": 1.0,
        "graph_ranking_empty": empty_graph}}}
    return [row(i < empty) for i in range(n)]


def test_the_empty_graph_gate_is_enforced_from_ten_questions_and_only_reported_below():
    ten_bad = summarise(_rows(10, empty=4), ["hybrid"])["empty_graph_gate"]  # 40 percent > 30
    assert ten_bad["enforced"] and ten_bad["passed"] is False and ten_bad["empty_graph_fraction"] == 0.4
    ten_ok = summarise(_rows(10, empty=3), ["hybrid"])["empty_graph_gate"]  # exactly 30 percent
    assert ten_ok["enforced"] and ten_ok["passed"] is True
    smoke = summarise(_rows(2, empty=2), ["hybrid"])["empty_graph_gate"]  # 100 percent, but only 2 questions
    assert smoke["enforced"] is False and smoke["passed"] is True and smoke["empty_graph_fraction"] == 1.0


def test_the_gate_does_not_apply_when_the_graph_arm_was_not_run():
    assert summarise([{"arms": {"dense": {"invalid": False, "recall_at_10": None, "ndcg_at_10": None,
                                          "ranking_length": 1, "latency_ms": 1.0, "graph_ranking_empty": None}}}],
                     ["dense"])["empty_graph_gate"] == {"applicable": False}


def test_run_invalid_is_the_refusal_type():
    with pytest.raises(RunInvalid):
        run_ablation.select_arms("nonsense")


# ── constraint 9: no live benchmark against gold that is not approved ─────────


def _gold(approved_by: str | None, status: str = "benchmark"):
    from eval.metrics import Gold

    return Gold("q", status, (), None, approved_by)


def test_a_live_run_is_refused_while_any_gold_is_a_draft_or_missing():
    from eval.run_ablation import require_approved_gold

    golds = {"q-a": _gold("Azim"), "q-b": _gold(None), "q-c": None}
    with pytest.raises(RunInvalid, match="q-b, q-c"):
        require_approved_gold(golds, live=True)


def test_a_live_run_proceeds_when_every_gold_is_approved():
    from eval.run_ablation import require_approved_gold

    require_approved_gold({"q-a": _gold("Azim"), "q-b": _gold("Azim", "unanswerable")}, live=True)


def test_a_fake_run_may_use_drafts_because_it_only_checks_plumbing():
    from eval.run_ablation import require_approved_gold

    require_approved_gold({"q-a": _gold(None), "q-b": None}, live=False)


def test_gold_files_read_the_approver_and_default_to_a_draft(tmp_path: Path):
    from eval import metrics

    (tmp_path / "q-1.yaml").write_text("question_id: q-1\nstatus: benchmark\nreference_contexts: []\n", encoding="utf-8")
    (tmp_path / "q-2.yaml").write_text("question_id: q-2\nstatus: benchmark\napproved_by: Azim\nreference_contexts: []\n", encoding="utf-8")
    one, two = metrics.load_gold(tmp_path, "q-1"), metrics.load_gold(tmp_path, "q-2")
    assert one is not None and not one.approved and two is not None and two.approved and two.approved_by == "Azim"


# ── cost-audit findings in the runner ─────────────────────────────────────────


def _ingested(chunks: int, failures: int | None, now: bool = True) -> dict:
    return {"arxiv_id": "x", "status": "ready", "chunks": chunks, "extraction_failures": failures, "ingested_now": now}


def test_a_run_where_too_many_chunks_failed_extraction_is_refused():
    from eval.run_ablation import require_extraction_quality

    require_extraction_quality([_ingested(100, 5)])  # exactly 5 percent is allowed
    with pytest.raises(RunInvalid, match="6 of 100"):
        require_extraction_quality([_ingested(100, 6)])


def test_documents_reused_from_an_earlier_ingest_are_not_counted_in_the_failure_rate():
    from eval.run_ablation import require_extraction_quality

    require_extraction_quality([_ingested(500, None, now=False), _ingested(100, 0)])  # reused: failures unknown (None)


async def test_the_corpus_loop_stops_at_the_first_failed_paper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from types import SimpleNamespace

    from api.ingestion.types import IngestResult
    from eval import run_ablation

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = []
    for i in range(3):
        (corpus / f"p{i}.pdf").write_bytes(f"%PDF-{i}".encode())
        manifest.append({"arxiv_id": f"0000.0000{i}v1", "file": f"p{i}.pdf"})
    ingested: list[str] = []

    async def fake_ingest(raw: bytes, name: str, deps):
        ingested.append(name)
        status = "failed" if name == "p1.pdf" else "ready"
        return IngestResult("d", "T", status, 4, 1, 1, 0, "cap" if status == "failed" else None)

    monkeypatch.setattr(run_ablation, "ingest_pdf", fake_ingest)
    container = SimpleNamespace(docs=SimpleNamespace(get_document=lambda _id: None), ingest_deps=None)
    report = await run_ablation.ensure_corpus(container, manifest, corpus, reingest=False)  # pyright: ignore[reportArgumentType]
    assert ingested == ["p0.pdf", "p1.pdf"]  # p2 was never attempted (it would pay for embeddings, then fail)
    assert [r["status"] for r in report] == ["ready", "failed"]
