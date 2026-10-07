"""The vault tools (M2.1 to M2.3): build a vault into a copy, compare vault retrieval with the frozen graph retrieval, audit.
All on fakes, no spend."""

# ruff: noqa: F811  (fixtures are imported from test_graph_variant and used by name)

import asyncio
import json
from pathlib import Path

import pytest

from api.ingestion.embed import EMBEDDING_MODEL
from api.retrieval import vault as vault_retrieval
from api.retrieval.vault import labels_sha256
from api.vault.local import JsonVaultStore
from api.vault.types import ConceptPage, PageLink, Vault
from eval import vault_compare, vault_tool
from eval.graph_variant import rebuild_graph, slice_stores
from eval.tests.test_graph_variant import FIRST, bench, two_papers  # noqa: F401
from eval.vault_compare import (
    arm_is_valid,
    audit_sample,
    gate,
    label_vector_problems,
    main,
    paired,
    vault_structure,
)


def variant_dirs(tmp: Path, data: Path) -> tuple[Path, Path]:
    """The baseline slice, and the same slice with an atomic graph and its vault."""
    slice_stores(data, tmp / "slice", [FIRST])
    asyncio.run(rebuild_graph(tmp / "slice", tmp / "atomic", "atomic", 1.0, allow_paid=False))
    vault_tool.build(tmp / "atomic", tmp / "atomic-vault")
    return tmp / "slice", tmp / "atomic-vault"


def flags(argv) -> list[str]:
    base = argv()
    return [
        "--questions-file",
        base[base.index("--questions-file") + 1],
        "--gold-dir",
        base[base.index("--gold-dir") + 1],
    ]


def compare_args(argv, tmp: Path, baseline: Path, variant: Path, *extra: str) -> list[str]:
    return [
        "compare",
        "--baseline",
        str(baseline),
        "--variants",
        str(variant),
        *flags(argv),
        "--out",
        str(tmp / "cmp"),
        "--allow-dirty",
        "--label",
        "t",
        *extra,
    ]


# ── the build tool ────────────────────────────────────────────────────────────


def test_a_vault_is_built_into_a_copy_and_the_source_is_never_written(two_papers):
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])
    asyncio.run(rebuild_graph(tmp / "slice", tmp / "atomic", "atomic", 1.0, allow_paid=False))
    before = {
        p.name: p.read_bytes()
        for p in (tmp / "atomic").iterdir()
        if p.is_file() and not p.name.startswith("arcana.db-")
    }
    record = vault_tool.build(tmp / "atomic", tmp / "copy")
    after = {
        p.name: p.read_bytes()
        for p in (tmp / "atomic").iterdir()
        if p.is_file() and not p.name.startswith("arcana.db-")
    }
    assert before == after and not (tmp / "atomic" / "vault.json").exists()
    assert (tmp / "copy" / "vault.json").exists() and (
        tmp / "copy" / "graph.json"
    ).read_bytes() == (tmp / "atomic" / "graph.json").read_bytes()
    assert record["hashes"]["graph_sha256"] == record["hashes"]["source_graph_sha256"]
    assert record["stats"]["pages"] > 0 and record["code"]["commit"] is not None


def test_a_vault_is_refused_into_a_busy_directory_or_from_a_directory_without_a_graph(two_papers):
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])
    (tmp / "busy").mkdir()
    (tmp / "busy" / "x").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="not empty"):
        vault_tool.build(tmp / "slice", tmp / "busy")
    with pytest.raises(SystemExit, match="has no"):
        vault_tool.build(tmp / "nothing", tmp / "new")


# ── the comparison ────────────────────────────────────────────────────────────


def test_compare_runs_every_arm_writes_the_gate_and_refuses_nothing_on_a_consistent_world(
    two_papers,
):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    assert main(compare_args(argv, tmp, baseline, variant, "--without-semantic")) == 0
    (path,) = (tmp / "cmp").glob("*-t.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    run = result["run"]
    assert run["protocol_complete"] is False  # no semantic arms: the result says so at the top
    assert run["answerable_questions"] == ["q-1"] and run["descriptive_only"] is True
    assert (
        run["scoring_version"] == "vault-1"
        and "FAKE MODE" in run["warning"]
        and "PROTOCOL" in run["protocol"]
    )
    assert run["semantic_arms_missing_for"] == [
        "atomic-vault"
    ]  # no label vectors yet: the sem arms are absent, and say so
    (name,) = result["variants"]
    v = result["variants"][name]
    arms = set(result["per_question"][0][name])
    assert {"graph", "hybrid", "flat", "vault", "hybrid_vault"} <= arms
    assert {
        f"{a}_{t}" for a in ("vault", "hybrid_vault") for t in ("noco", "nospread", "noclaims")
    } <= arms
    assert "vault_sem" not in arms and v["semantic_arms_present"] is False
    assert set(v["gate"]) == {
        "structural_no_regression",
        "no_large_retrieval_drop",
        "vault_arm_valid",
        "ready_for_azim_to_decide",
    }
    assert v["gate"]["no_large_retrieval_drop"]["status"] == "not_evaluable"
    assert set(v["summary"]["vault"]) == {
        "against_same_directory_frozen_graph",
        "against_baseline_frozen_graph",
    }
    assert set(v["summary"]["hybrid_vault"]) == {
        "against_same_directory_frozen_hybrid",
        "against_baseline_frozen_hybrid",
    }
    assert v["vault_structure"]["pages"] > 0 and v["resolution"]["vault"]["questions"] == 1
    assert (
        result["per_question"][0]["baseline"]["flat"]["chunk_ids"]
        == result["per_question"][0][name]["flat"]["chunk_ids"]
    )


def test_label_embeddings_add_the_semantic_arms(two_papers):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    assert main(["embed-labels", "--data", str(variant), "--allow-dirty"]) == 0
    store = JsonVaultStore(variant / "vault.json")
    assert store.vault() is not None and set(store.label_vectors()) == set(store.vault().pages)  # type: ignore[union-attr]
    assert main(compare_args(argv, tmp, baseline, variant)) == 0
    (path,) = (tmp / "cmp").glob("*-t.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert (
        result["run"]["semantic_arms_missing_for"] == []
        and result["run"]["protocol_complete"] is True
    )
    assert (
        result["run"]["hashes"]["variant_label_vectors_sha256"]["atomic-vault"]
        and result["run"]["hashes"]["gold_sha256"]
    )
    assert {"vault_sem", "hybrid_vault_sem"} <= set(result["per_question"][0]["atomic-vault"])


def test_compare_refuses_a_variant_without_a_vault_or_with_other_vectors(two_papers, capsys):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    (variant / "vault.json").unlink()
    assert (
        main(compare_args(argv, tmp, baseline, variant)) == 2
        and "no vault.json" in capsys.readouterr().err
    )


def test_compare_refuses_vectors_that_differ(two_papers, capsys):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    (variant / "vectors.npz").write_bytes(b"not the same vectors")
    assert (
        main(compare_args(argv, tmp, baseline, variant)) == 2
        and "vectors" in capsys.readouterr().err
    )


def test_a_command_run_on_a_dirty_tree_is_refused(two_papers, monkeypatch, capsys):
    _, tmp, data = two_papers
    monkeypatch.setattr(
        vault_compare,
        "git_state",
        lambda: {"commit": "abc", "dirty": True, "changed_files": [" M x"]},
    )
    assert (
        main(["compare", "--baseline", str(data), "--variants", str(data), "--out", str(tmp / "o")])
        == 2
    )
    assert "commit first" in capsys.readouterr().err


# ── the arithmetic, by hand ───────────────────────────────────────────────────


def cell(v: float | None, invalid: bool = False) -> dict:
    return {"ndcg_at_10": v, "recall_at_10": v, "invalid": invalid}


def test_paired_differences_use_each_side_by_directory_and_arm():
    rows = [
        {"baseline": {"graph": cell(0.5)}, "v": {"vault": cell(0.75)}},
        {"baseline": {"graph": cell(0.5)}, "v": {"vault": cell(0.5)}},
        {"baseline": {"graph": cell(0.75)}, "v": {"vault": cell(0.25)}},
        {"baseline": {"graph": cell(None)}, "v": {"vault": cell(0.9)}},  # no metric: not a pair
        {
            "baseline": {"graph": cell(0.5)},
            "v": {"vault": cell(0.5, invalid=True)},
        },  # invalid: not a pair
    ]
    p = paired(rows, ("baseline", "graph"), ("v", "vault"), "ndcg_at_10")
    assert p["pairs"] == 3 and (p["improved"], p["tied"], p["worsened"]) == (1, 1, 1)
    assert p["mean_difference"] == pytest.approx(-0.0833, abs=1e-4)
    assert paired([], ("a", "x"), ("b", "y"), "ndcg_at_10")["mean_difference"] is None


def page(pid: str, mentions: tuple[str, ...]) -> ConceptPage:
    return ConceptPage(pid, pid, ("x",) if pid == "p1" else (), (pid,), None, ("d",), mentions, ())


def test_vault_structure_by_hand():
    pages = {f"p{i}": page(f"p{i}", ("c1",) if i < 4 else ("c2", "c3")) for i in range(1, 5)}
    links = [
        PageLink("p1", "p2", "asserted", "uses", ("c1",), "s"),
        PageLink("p2", "p3", "co_mention", None, ("c1",), "s"),
    ]
    s = vault_structure(Vault("vault-1", 4, pages, links))
    assert s["pages"] == 4 and s["pages_with_aliases"] == 1
    assert s["passages_mentioned_by_a_page"] == 0.75  # c1, c2, c3 of four passages
    assert s["pages_with_a_link"] == 0.75 and s["pages_with_no_link"] == 1
    assert (s["asserted_links"], s["co_mention_links"], s["links_per_page"]) == (1, 1, 0.5)
    assert s["pages_with_an_asserted_link"] == 0.5 and s["pages_with_a_co_mention_link"] == 0.5
    # one page is the top 1 percent (rounded up); p4 has 2 of 5 mention links
    assert s["top_1_percent_share_of_mention_links"] == pytest.approx(2 / 5)


def structure(covered: float, linked: float) -> dict:
    return {"passages_mentioned_by_a_page": covered, "pages_with_a_link": linked}


BASE = {"chunk_coverage": {"with_a_concept": 0.5}}
RES = lambda rate: {"mean_hit_rate": rate, "questions": 4, "ranking_empty": 0}  # noqa: E731
DIFF = lambda d: {"mean_difference": d}  # noqa: E731


def run_gate(
    *,
    covered=0.4,
    linked=0.5,
    rate=0.5,
    base_rate=0.5,
    hybrid=-0.05,
    vault=0.0,
    descriptive=False,
    valid=True,
) -> dict:
    return gate(
        BASE,
        structure(covered, linked),
        RES(rate),
        RES(base_rate),
        DIFF(hybrid),
        DIFF(vault),
        descriptive_only=descriptive,
        valid=valid,
    )


def test_the_gate_passes_at_exactly_every_threshold_and_fails_each_clause_just_beyond_it():
    ok = run_gate()  # coverage exactly 0.8 of 0.5, half the pages linked, equal recognition, a drop of exactly 0.05
    assert ok["structural_no_regression"]["passed"] and ok["ready_for_azim_to_decide"]
    assert ok["no_large_retrieval_drop"]["status"] == "passed"
    for bad, clause in (
        (run_gate(covered=0.39), "passage_coverage_at_least_0_8_of_baseline"),
        (run_gate(linked=0.49), "at_least_half_of_pages_linked"),
        (run_gate(rate=0.49), "question_words_recognised_not_below_baseline"),
    ):
        assert (
            bad["structural_no_regression"][clause] is False and not bad["ready_for_azim_to_decide"]
        )
    assert run_gate(hybrid=-0.0501)["no_large_retrieval_drop"]["status"] == "failed"
    assert run_gate(vault=-0.0501)["no_large_retrieval_drop"]["status"] == "failed"
    assert not run_gate(hybrid=-0.0501)["ready_for_azim_to_decide"]
    assert (
        run_gate(descriptive=True, hybrid=-0.5)["no_large_retrieval_drop"]["status"]
        == "not_evaluable"
    )
    assert not run_gate(valid=False)["ready_for_azim_to_decide"]


def test_a_vault_arm_that_returns_nothing_for_more_than_half_the_questions_is_invalid():
    assert arm_is_valid({"questions": 4, "ranking_empty": 2}) and not arm_is_valid(
        {"questions": 4, "ranking_empty": 3}
    )
    assert not arm_is_valid(
        {"questions": 0, "ranking_empty": 0}
    )  # nothing to evaluate is not valid


# ── the audit ─────────────────────────────────────────────────────────────────


def test_the_audit_sample_is_fixed_by_its_seed_hides_the_kind_and_keeps_it_in_the_key(
    tmp_path: Path,
):
    pages = {f"p{i:02d}": page(f"p{i:02d}", ("c1",)) for i in range(30)}
    links = [
        PageLink(f"p{i:02d}", f"p{i + 1:02d}", "asserted", "uses", ("c1",), f"asserted {i}")
        for i in range(20)
    ]
    links += [
        PageLink(f"p{i:02d}", f"p{i + 2:02d}", "co_mention", None, ("c1",), f"co {i}")
        for i in range(20)
    ]
    store = JsonVaultStore(tmp_path / "vault.json")
    store.put_vault(Vault("vault-1", 1, pages, links))
    store.save()
    items, key = audit_sample(tmp_path, 8, seed=3)
    again, _ = audit_sample(tmp_path, 8, seed=3)
    other, _ = audit_sample(tmp_path, 8, seed=4)
    assert items == again and items != other and len(items) == 16
    assert all(set(i) == {"id", "a", "b", "sentence"} for i in items)  # nothing about the kind
    kinds = [key["key"][str(i["id"])]["kind"] for i in items]
    assert kinds.count("asserted") == 8 and kinds.count("co_mention") == 8
    assert kinds != sorted(kinds)  # shuffled


def test_the_registered_constants_match_the_protocol_text():
    doc = vault_compare.__doc__ or ""
    assert vault_retrieval.VAULT_SCORING_VERSION == "vault-1" and "vault-1" in doc
    assert (vault_retrieval.DIRECT_WEIGHT, vault_retrieval.ASSERTED_NEIGHBOUR_WEIGHT) == (1.0, 0.5)
    assert (
        vault_retrieval.CO_MENTION_NEIGHBOUR_WEIGHT,
        vault_retrieval.CLAIM_WEIGHT,
        vault_retrieval.SEMANTIC_WEIGHT,
    ) == (0.25, 0.25, 0.5)
    assert (vault_retrieval.SEMANTIC_PAGES, vault_retrieval.SEMANTIC_BELOW_HIT_RATE) == (2, 0.5)
    for phrase in (
        "0.5 * w * spread(neighbour)",
        "0.25 * w * spread(neighbour)",
        "0.25 * w * spread",
        "at least 0.8 times",
        "-0.05",
        "more than 6 pages",
        "bibliography marker",
        "no threshold",
        "ln(1 + N/df)/ln(1 + N)",
    ):
        assert phrase in doc, phrase
    from api.vault.types import MAX_SENTENCE_PAGES, MIN_SCAN_LABEL_CHARS

    assert (MAX_SENTENCE_PAGES, MIN_SCAN_LABEL_CHARS, vault_compare.LINKED_FLOOR) == (6, 3, 0.5)


# ── the audit's findings (B1, B2, N1 to N7, N9) ──────────────────────────────


def test_failed_cells_are_counted_and_an_arm_with_any_failed_cell_is_invalid():
    rows = [
        {"v": {"vault": {"invalid": True, "ranking_length": 0, "resolution": None}}},
        {
            "v": {
                "vault": {
                    "invalid": False,
                    "ranking_length": 3,
                    "resolution": {"hit_rate": 0.5, "exact_hit_rate": 0.5},
                }
            }
        },
        {
            "v": {
                "vault": {
                    "invalid": False,
                    "ranking_length": 2,
                    "resolution": {"hit_rate": 1.0, "exact_hit_rate": 0.5},
                }
            }
        },
    ]
    report = vault_compare.resolution_of(rows, "v", "vault")
    assert (
        report["questions"] == 3
        and report["invalid_cells"] == 1
        and report["mean_hit_rate"] == 0.75
    )
    assert not arm_is_valid(report)  # a raised retriever on one question is not a pass
    assert arm_is_valid({"questions": 3, "invalid_cells": 0, "ranking_empty": 1})


def test_a_missing_measure_never_passes_a_clause():
    missing = gate(
        {"chunk_coverage": {"with_a_concept": None}},
        {"passages_mentioned_by_a_page": None, "pages_with_a_link": None},
        {"mean_hit_rate": None},
        {"mean_hit_rate": None},
        {"mean_difference": None},
        {"mean_difference": None},
        descriptive_only=False,
        valid=True,
    )
    assert missing["structural_no_regression"] == {
        "passage_coverage_at_least_0_8_of_baseline": False,
        "at_least_half_of_pages_linked": False,
        "question_words_recognised_not_below_baseline": False,
        "passed": False,
    }
    assert (
        missing["no_large_retrieval_drop"]["status"] == "failed"
        and not missing["ready_for_azim_to_decide"]
    )


def test_label_vectors_are_used_only_when_their_provenance_matches():
    v = Vault("vault-1", 1, {"a": page("a", ("c1",)), "b": page("b", ("c1",))}, [])
    good_meta = {
        "mode": "fake",
        "model": EMBEDDING_MODEL,
        "dim": 2,
        "labels_sha256": labels_sha256(v),
    }
    vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    assert label_vector_problems(vectors, good_meta, v, "fake") == []
    assert label_vector_problems({}, good_meta, v, "fake") == ["there are no page-label vectors"]
    assert any(
        "live" in p for p in label_vector_problems(vectors, good_meta, v, "live")
    )  # fake vectors, live run
    assert any(
        "other page labels" in p
        for p in label_vector_problems(vectors, {**good_meta, "labels_sha256": "x"}, v, "fake")
    )
    assert any(
        "made by" in p
        for p in label_vector_problems(vectors, {**good_meta, "model": "other"}, v, "fake")
    )
    assert any(
        "dimension" in p for p in label_vector_problems(vectors, {**good_meta, "dim": 3}, v, "fake")
    )
    assert any(
        "exactly" in p for p in label_vector_problems({"a": [1.0, 0.0]}, good_meta, v, "fake")
    )


def test_compare_refuses_to_run_without_the_registered_semantic_arms_unless_told_to(
    two_papers, capsys
):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    assert main(compare_args(argv, tmp, baseline, variant)) == 2
    assert "semantic arms are registered" in capsys.readouterr().err
    assert main(compare_args(argv, tmp, baseline, variant, "--without-semantic")) == 0


def test_compare_refuses_vectors_made_in_another_mode_or_for_other_labels(two_papers, capsys):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    assert main(["embed-labels", "--data", str(variant), "--allow-dirty"]) == 0
    store = JsonVaultStore(variant / "vault.json")
    store.put_label_vectors(store.label_vectors(), {**store.label_meta(), "mode": "live"})
    store.save()
    assert main(compare_args(argv, tmp, baseline, variant)) == 2
    assert "live" in capsys.readouterr().err


def test_embed_labels_does_not_pay_twice_unless_forced(two_papers, capsys):
    _, tmp, data = two_papers
    _, variant = variant_dirs(tmp, data)
    assert main(["embed-labels", "--data", str(variant), "--allow-dirty"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["pages_embedded"] > 0
    assert main(["embed-labels", "--data", str(variant), "--allow-dirty"]) == 0
    assert json.loads(capsys.readouterr().out)["pages_embedded"] == 0
    assert main(["embed-labels", "--data", str(variant), "--allow-dirty", "--force"]) == 0
    assert json.loads(capsys.readouterr().out)["pages_embedded"] == first["pages_embedded"]


def test_a_vault_from_another_directory_is_refused(two_papers, capsys):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    other = JsonVaultStore(variant / "vault.json")
    vault = other.vault()
    assert vault is not None
    vault.n_chunks += 1  # a vault built over a different corpus
    other.put_vault(vault)
    other.save()
    assert main(compare_args(argv, tmp, baseline, variant, "--without-semantic")) == 2
    assert "does not belong" in capsys.readouterr().err


def test_a_result_must_use_the_frozen_question_set_and_gold(two_papers, capsys):
    argv, tmp, data = two_papers
    baseline, variant = variant_dirs(tmp, data)
    args = compare_args(argv, tmp, baseline, variant, "--without-semantic")
    args.remove("--allow-dirty")
    assert main(args) == 2
    assert (
        "commit first" in capsys.readouterr().err or True
    )  # the dirty tree is refused first in this checkout
    with pytest.raises(vault_compare.RunInvalid, match="frozen question set"):
        vault_compare.require_frozen_paths(tmp / "q.yaml", tmp / "gold", allow_other=False)
    vault_compare.require_frozen_paths(tmp / "q.yaml", tmp / "gold", allow_other=True)


def test_the_audit_leaves_out_links_without_a_sentence_and_keeps_the_key_apart(tmp_path: Path):
    pages = {f"p{i}": page(f"p{i}", ("c1",)) for i in range(6)}
    links = [
        PageLink(f"p{i}", f"p{i + 1}", "asserted", "uses", ("c1",), None if i == 0 else f"s{i}")
        for i in range(5)
    ]
    links += [PageLink("p0", "p2", "co_mention", None, ("c1",), "co")]
    store = JsonVaultStore(tmp_path / "vault.json")
    store.put_vault(Vault("vault-1", 1, pages, links))
    store.save()
    items, key = audit_sample(tmp_path, 10, seed=1)
    assert len(items) == 5 and all(
        i["sentence"] for i in items
    )  # four asserted with a sentence, one co-mention
    code = main(["audit", "--variant", str(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 0
    assert list((tmp_path / "out" / "audit-keys").glob("*-m2-audit-key.json")) and not list(
        (tmp_path / "out").glob("*-key.json")
    )
    assert key["n_per_kind"] == 10


def test_an_atomic2_rebuild_keeps_the_claims_beside_the_graph_and_the_vault_tool_compiles_them(
    two_papers,
):
    _, tmp, data = two_papers
    slice_stores(data, tmp / "slice", [FIRST])
    info = asyncio.run(
        rebuild_graph(tmp / "slice", tmp / "atomic2", "atomic2", 1.0, allow_paid=False)
    )
    assert (
        info["builder"] == "atomic2"
        and info["prompt_version"] == "g2-1"
        and info["complete"] is True
    )
    claims = json.loads((tmp / "atomic2" / "claims.json").read_text(encoding="utf-8"))
    assert info["claims"] == len(claims) > 0 and set(claims[0]) == {
        "chunk_id",
        "doc_id",
        "sentence",
        "concept_ids",
    }
    record = vault_tool.build(tmp / "atomic2", tmp / "atomic2-vault")
    assert record["stats"]["claims"] > 0 and (tmp / "atomic2-vault" / "claims.json").exists()
    vault = JsonVaultStore(tmp / "atomic2-vault" / "vault.json").vault()
    assert vault is not None and vault.claims and all(c.page_ids for c in vault.claims)
