"""Compare vault retrieval with the frozen graph retrieval over the same slice (M2.2 to M2.5, D-35).

    uv run python eval/vault_tool.py build --from data/g1/slice-atomic --to data/m2/slice-atomic-vault1
    uv run python eval/vault_compare.py embed-labels --data data/m2/slice-atomic-vault1 --allow-paid
    uv run python eval/vault_compare.py compare --baseline data/g1/slice-base --variants data/m2/slice-atomic-vault1 --allow-paid
    uv run python eval/vault_compare.py audit --variant data/m2/slice-atomic-vault1

PROTOCOL (fixed in D-35 before any vault run, constraint 9; it changes only by a declared amendment made before a run, never
after seeing results; the same text is in D-35, with amendments A1 and A2):

  Corpus     the Mark 1 slice (3 papers, 285 passages) and the frozen 20 questions, 19 answerable; gold unchanged. `--baseline` is the
             pinned free-form graph restricted to the slice; each `--variants` directory holds the same documents and vectors with
             a graph (g1-3 or `atomic2`) and its vault. Every directory must hold byte-identical chunks and vectors, and the `flat`
             control (dense plus BM25, no graph) must return the same passages for every question in every directory, or the run is
             refused. Retrieval is scored on the questions whose gold has a passage in the slice; fewer than ten means descriptive.
  Vault      pages: union-find over `alias_of` edges and equal compact ids; mentions: a member's chunk list, or a member label of
             3+ characters found as a whole word, blind to hyphenation, anywhere in the corpus; asserted links lifted from edges;
             co-mention links: two pages whose labels occur in one sentence, none from a sentence naming more than 6 pages, none from
             pages of kind person or organisation, and (A1) none from a sentence with a strong bibliography marker (arXiv, preprint,
             proceedings, doi, pp., journal of, conference on, association for computational); spread idf = ln(1 + N/df)/ln(1 + N).
  Arms       over every directory the frozen `graph`, `hybrid` and the control `flat`; over every variant the vault arms `vault`
             (the vault retriever alone), `hybrid_vault` (dense + BM25 + vault, RRF k = 60), `vault_sem` and `hybrid_vault_sem` (the
             same with semantic resolution). Scoring `vault-1`: resolved page weight 1.0 exact, 0.6 approximate, 0.5 semantic;
             direct (mentions and asserted evidence) = w * spread; asserted neighbour's mentions = 0.5 * w * spread(neighbour);
             co-mention neighbour's mentions = 0.25 * w * spread(neighbour), asserted before co-mention, the best neighbour once per
             passage (A2); a passage holding a claim naming the page adds 0.25 * w * spread (A2); ties by asserted-link support,
             document id, position. Semantic resolution (rank-based, no threshold) adds the 2 pages nearest the question embedding
             when the lexical step recognised fewer than half of the content words. Free ablations on the same build, reported
             and never gating: co-mentions off, spread off, claims off, for `vault` and `hybrid_vault`.
  Primary    Recall@10 and nDCG@10 per question and arm, paired differences with improved, tied and worsened counts; the vault arms
             against the SAME directory's frozen arms (the improvement question) and against the BASELINE directory's frozen arms.
             Descriptive only below ten answerable questions; no significance is claimed. Model-judged scores are never primary.
  Gate       a variant's vault passes `no structural regression` if ALL hold: (1) the share of passages that at least one page
             mentions is at least 0.8 times the baseline graph's share of passages naming a concept; (2) at least 0.5 of the pages have
             a link of either kind; (3) the mean fraction of the questions' content words the `vault` arm's resolver recognised is at
             least the baseline `graph` arm's; (4) mean paired nDCG@10 of `hybrid_vault` against the baseline's `hybrid`, and of `vault`
             against the baseline's `graph`, is at least -0.05. The Mark 1 top-1% share of mention links is REPORTED, not gating
             (merging aliases into pages concentrates mentions by design; the spread discount is the mechanism and clause 4 measures
             it); so are links per page, pages with no link, the asserted and co-mention shares and the sem arms.
  Validity   a vault arm is INVALID (flagged at the top) if it returns no passage for more than half of the answerable questions.
  Looks      the same 19 questions have been read by Mark 1 (look 1); `vault-1` over the g1-3 graph is look 2; over an `atomic2` graph
             look 3. A change to any constant after seeing a result is a new version, declared before the next run and counted.
  Spend      `embed-labels` embeds the pages' display labels once (a few thousand tokens); `compare` computes the questions' query
             embeddings; both are paid in live mode and need --allow-paid. No other paid step lives here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)  # so `api` and `eval` import when run as a script

from api.container import Container, build_container
from api.core.logging import configure_logging
from api.ingestion.embed import CachingEmbedder
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.sparse import SparseRetriever
from api.retrieval.vault import VAULT_SCORING_VERSION, VaultRetriever, embed_page_labels
from api.stores.preflight import check_corpus_parity
from api.vault.local import JsonVaultStore
from api.vault.types import Vault
from eval import metrics
from eval.graph_quality import measure
from eval.graph_variant import (
    COVERAGE_FLOOR,
    EMPTY_GRAPH_LIMIT,
    MAX_NDCG_DROP,
    PAIRED_MIN_FOR_SIGNIFICANCE,
    is_live,
    mean,
    settings_for,
)
from eval.run_ablation import (
    ROOT,
    RunInvalid,
    chunks_sha256,
    git_state,
    load_questions,
    run_arm,
    sha256_file,
)

VAULT_FILE = "vault.json"
LINKED_FLOOR = 0.5
FROZEN_ARMS = ("graph", "hybrid", "flat")
VAULT_ARMS = ("vault", "hybrid_vault", "vault_sem", "hybrid_vault_sem")
ABLATIONS = {
    "noco": {"co_mentions": False},
    "nospread": {"spread": False},
    "noclaims": {"claims": False},
}
ABLATED_ARMS = ("vault", "hybrid_vault")
METRICS = ("recall_at_10", "ndcg_at_10")


def vault_structure(vault: Vault) -> dict[str, Any]:
    """Structure of a vault, from the vault alone."""
    pages = len(vault.pages)
    linked: set[str] = set()
    asserted: set[str] = set()
    cowith: set[str] = set()
    for link in vault.links:
        for end in (link.src, link.dst):
            linked.add(end)
            (asserted if link.kind == "asserted" else cowith).add(end)
    covered = {c for p in vault.pages.values() for c in p.mention_chunk_ids}
    mention_links = sum(len(p.mention_chunk_ids) for p in vault.pages.values())
    top = sorted((len(p.mention_chunk_ids) for p in vault.pages.values()), reverse=True)[
        : max(1, math.ceil(pages * 0.01))
    ]
    n_asserted = sum(1 for link in vault.links if link.kind == "asserted")
    return {
        "pages": pages,
        "pages_with_aliases": sum(1 for p in vault.pages.values() if p.aliases),
        "passages": vault.n_chunks,
        "passages_mentioned_by_a_page": round(len(covered) / vault.n_chunks, 4)
        if vault.n_chunks
        else None,
        "pages_with_a_link": round(len(linked) / pages, 4) if pages else None,
        "pages_with_an_asserted_link": round(len(asserted) / pages, 4) if pages else None,
        "pages_with_a_co_mention_link": round(len(cowith) / pages, 4) if pages else None,
        "pages_with_no_link": pages - len(linked),
        "asserted_links": n_asserted,
        "co_mention_links": len(vault.links) - n_asserted,
        "links_per_page": round(len(vault.links) / pages, 4) if pages else None,
        "claims": len(vault.claims),
        "top_1_percent_share_of_mention_links": round(sum(top) / mention_links, 4)
        if mention_links
        else None,
        "vault_sha256": vault.sha256(),
    }


def paired(
    rows: list[dict[str, Any]], a: tuple[str, str], b: tuple[str, str], metric: str
) -> dict[str, Any]:
    """Paired difference b minus a, where each side is (directory name, arm)."""
    diffs, av, bv = [], [], []
    for r in rows:
        x, y = r[a[0]][a[1]], r[b[0]][b[1]]
        if x[metric] is None or y[metric] is None or x["invalid"] or y["invalid"]:
            continue
        av.append(x[metric])
        bv.append(y[metric])
        diffs.append(round(y[metric] - x[metric], 6))
    return {
        "pairs": len(diffs),
        "from_mean": mean(av),
        "to_mean": mean(bv),
        "mean_difference": mean(diffs),
        "improved": sum(d > 0 for d in diffs),
        "tied": sum(d == 0 for d in diffs),
        "worsened": sum(d < 0 for d in diffs),
    }


def resolution_of(rows: list[dict[str, Any]], side: str, arm: str) -> dict[str, Any]:
    cells = [r[side][arm] for r in rows if not r[side][arm]["invalid"]]
    resolved = [c["resolution"] for c in cells if c.get("resolution")]
    return {
        "questions": len(cells),
        "ranking_empty": sum(1 for c in cells if c["ranking_length"] == 0),
        "mean_hit_rate": mean([r["hit_rate"] for r in resolved]),
        "mean_exact_hit_rate": mean([r["exact_hit_rate"] for r in resolved]),
    }


def arm_is_valid(report: dict[str, Any]) -> bool:
    return (
        not report["questions"]
        or report["ranking_empty"] / report["questions"] <= EMPTY_GRAPH_LIMIT
    )


def gate(
    baseline_graph: dict[str, Any],
    structure: dict[str, Any],
    resolution_vault: dict[str, Any],
    resolution_baseline: dict[str, Any],
    hybrid_vs_baseline: dict[str, Any],
    vault_vs_baseline: dict[str, Any],
    *,
    descriptive_only: bool,
    valid: bool,
) -> dict[str, Any]:
    """The Mark 2 gate of D-35, evaluated and reported. It states facts; adopting the vault is Azim's decision."""

    def number(value: float | None) -> float:
        return value if value is not None else 0.0

    coverage = number(structure["passages_mentioned_by_a_page"]) >= COVERAGE_FLOOR * number(
        baseline_graph["chunk_coverage"]["with_a_concept"]
    )
    linked = number(structure["pages_with_a_link"]) >= LINKED_FLOOR
    recognised = number(resolution_vault["mean_hit_rate"]) >= number(
        resolution_baseline["mean_hit_rate"]
    )
    structural = coverage and linked and recognised

    if descriptive_only:
        retrieval: dict[str, Any] = {
            "status": "not_evaluable",
            "reason": "fewer than ten answerable questions: descriptive only",
        }
    else:
        diffs = (hybrid_vs_baseline["mean_difference"], vault_vs_baseline["mean_difference"])
        retrieval = {
            "status": "passed"
            if all(d is None or d >= -MAX_NDCG_DROP for d in diffs)
            else "failed",
            "hybrid_vault_vs_baseline_hybrid_mean_ndcg_difference": diffs[0],
            "vault_vs_baseline_graph_mean_ndcg_difference": diffs[1],
            "threshold": -MAX_NDCG_DROP,
        }
    return {
        "structural_no_regression": {
            "passage_coverage_at_least_0_8_of_baseline": coverage,
            "at_least_half_of_pages_linked": linked,
            "question_words_recognised_not_below_baseline": recognised,
            "passed": structural,
        },
        "no_large_retrieval_drop": retrieval,
        "vault_arm_valid": valid,
        "ready_for_azim_to_decide": structural and valid and retrieval["status"] != "failed",
    }


async def compare(args: argparse.Namespace) -> dict[str, Any]:
    baseline_dir = Path(args.baseline)
    variant_dirs = [Path(v) for v in args.variants.split(",") if v.strip()]
    if not variant_dirs:
        raise RunInvalid("--variants names no directory")
    names = {"baseline": baseline_dir, **{d.name: d for d in variant_dirs}}
    if len(names) != len(variant_dirs) + 1:
        raise RunInvalid("directory names must be distinct")
    base_settings = settings_for(baseline_dir)
    live = is_live(base_settings)
    if live and not args.allow_paid:
        raise RunInvalid(
            "live (paid) mode is configured; pass --allow-paid (it pays only for query embeddings)"
        )
    configure_logging("WARNING")

    for d in variant_dirs:
        if not (d / VAULT_FILE).exists():
            raise RunInvalid(f"{d} has no {VAULT_FILE}: build it with `vault_tool.py build`")
        if sha256_file(d / "vectors.npz") != sha256_file(baseline_dir / "vectors.npz"):
            raise RunInvalid(
                f"{d} does not hold the baseline's vectors: only the graph and vault may differ"
            )
    containers: dict[str, Container] = {
        n: build_container(settings_for(d)) for n, d in names.items()
    }
    for n, c in containers.items():
        problems = check_corpus_parity(c.docs, c.vectors, c.graph)
        if problems:
            raise RunInvalid(f"{n}: corpus parity check failed: " + "; ".join(problems))
    base_chunks = containers["baseline"].docs.all_chunks()
    base_hash = chunks_sha256(base_chunks)
    for n, c in containers.items():
        if chunks_sha256(c.docs.all_chunks()) != base_hash:
            raise RunInvalid(f"{n} does not hold the baseline's passages")

    stores = {n: JsonVaultStore(names[n] / VAULT_FILE) for n in names if n != "baseline"}
    vaults: dict[str, Vault] = {}
    for n, s in stores.items():
        v = s.vault()
        if v is None:
            raise RunInvalid(f"{n}: the vault file is empty")
        vaults[n] = v

    questions_path, gold_dir = Path(args.questions_file), Path(args.gold_dir)
    questions = load_questions(questions_path)
    corpus_texts = [c.text for c in base_chunks]
    embedder = CachingEmbedder(
        containers["baseline"].embedder
    )  # one query embedding per question, shared by every arm
    base_retrievers: dict[str, dict[str, Any]] = {}
    for n, c in containers.items():
        base_retrievers[n] = {
            "dense": DenseRetriever(vectors=c.vectors, docs=c.docs, embedder=embedder),
            "sparse": SparseRetriever(docs=c.docs),
            "graph": GraphRetriever(graph=c.graph, docs=c.docs),
        }

    def vault_retrievers(n: str, **kwargs: Any) -> dict[str, Any]:
        r = dict(base_retrievers[n])
        r["graph"] = VaultRetriever(vault=vaults[n], docs=containers[n].docs, **kwargs)
        return r

    sem: dict[str, dict[str, Any]] = {}
    for n, s in stores.items():
        vectors = s.label_vectors()
        have = bool(vectors) and set(vectors) >= set(vaults[n].pages)
        sem[n] = {"embedder": embedder, "label_vectors": vectors, "semantic": True} if have else {}
    missing_sem = [n for n in stores if not sem[n]]

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for q in questions:
        gold = metrics.load_gold(gold_dir, q["id"])
        n_rel = metrics.relevant_count(corpus_texts, gold) if gold and gold.passages else 0
        if n_rel == 0:
            skipped.append(
                {"question_id": q["id"], "reason": "no gold passage in this slice's chunks"}
            )
            continue
        text = q["question"].strip()
        row: dict[str, Any] = {
            "question_id": q["id"],
            "category": q["category"],
            "relevant_chunks_in_slice": n_rel,
        }
        for n in names:
            row[n] = {
                arm: await run_arm(arm, text, base_retrievers[n], gold, corpus_texts, n_rel, False)
                for arm in FROZEN_ARMS
            }
        for n in stores:
            row[n]["vault"] = await run_arm(
                "graph", text, vault_retrievers(n), gold, corpus_texts, n_rel, False
            )
            row[n]["hybrid_vault"] = await run_arm(
                "hybrid", text, vault_retrievers(n), gold, corpus_texts, n_rel, False
            )
            if sem[n]:
                row[n]["vault_sem"] = await run_arm(
                    "graph", text, vault_retrievers(n, **sem[n]), gold, corpus_texts, n_rel, False
                )
                row[n]["hybrid_vault_sem"] = await run_arm(
                    "hybrid", text, vault_retrievers(n, **sem[n]), gold, corpus_texts, n_rel, False
                )
            for tag, kwargs in ABLATIONS.items():
                row[n][f"vault_{tag}"] = await run_arm(
                    "graph", text, vault_retrievers(n, **kwargs), gold, corpus_texts, n_rel, False
                )
                row[n][f"hybrid_vault_{tag}"] = await run_arm(
                    "hybrid", text, vault_retrievers(n, **kwargs), gold, corpus_texts, n_rel, False
                )
        rows.append(row)

    for r in rows:
        for n in names:
            if r[n]["flat"]["chunk_ids"] != r["baseline"]["flat"]["chunk_ids"]:
                raise RunInvalid(
                    f"the flat control differs between baseline and {n}: something other than the graph changed"
                )

    texts = {c.id: c.text for c in base_chunks}
    graph_structure = {
        n: measure(c.graph.nodes(), c.graph.edges(), texts) for n, c in containers.items()
    }
    descriptive_only = len(rows) < PAIRED_MIN_FOR_SIGNIFICANCE
    per_variant: dict[str, Any] = {}
    for n in stores:
        arms = [a for a in VAULT_ARMS if a in rows[0][n]] if rows else []
        ablated = [f"{a}_{t}" for a in ABLATED_ARMS for t in ABLATIONS]
        frozen_same = {
            "vault": "graph",
            "hybrid_vault": "hybrid",
            "vault_sem": "graph",
            "hybrid_vault_sem": "hybrid",
        }
        summary = {}
        for arm in arms + ablated:
            ref = frozen_same.get(arm) or ("graph" if arm.startswith("vault_") else "hybrid")
            summary[arm] = {
                "against_same_directory_frozen_" + ref: {
                    m: paired(rows, (n, ref), (n, arm), m) for m in METRICS
                },
                "against_baseline_frozen_" + ref: {
                    m: paired(rows, ("baseline", ref), (n, arm), m) for m in METRICS
                },
            }
        res_vault = resolution_of(rows, n, "vault")
        res_base = resolution_of(rows, "baseline", "graph")
        valid = arm_is_valid(res_vault)
        structure = vault_structure(vaults[n])
        per_variant[n] = {
            "vault_structure": structure,
            "graph_structure": graph_structure[n],
            "resolution": {
                "vault": res_vault,
                "baseline_graph": res_base,
                "same_directory_graph": resolution_of(rows, n, "graph"),
            },
            "summary": summary,
            "semantic_arms_present": bool(sem[n]),
            "gate": gate(
                graph_structure["baseline"],
                structure,
                res_vault,
                res_base,
                summary["hybrid_vault"]["against_baseline_frozen_hybrid"]["ndcg_at_10"],
                summary["vault"]["against_baseline_frozen_graph"]["ndcg_at_10"],
                descriptive_only=descriptive_only,
                valid=valid,
            ),
        }

    started = datetime.now(UTC)
    mode = {"llm": base_settings.arcana_llm_mode, "embed": base_settings.arcana_embed_mode}
    return {
        "run": {
            "timestamp": started.isoformat(),
            "label": args.label,
            "mode": mode,
            "warning": None
            if live
            else "FAKE MODE: this run checks the plumbing; its numbers say nothing about retrieval quality.",
            "code": git_state(),
            "protocol": __doc__,
            "scoring_version": VAULT_SCORING_VERSION,
            "hashes": {
                "questions_sha256": sha256_file(questions_path),
                "baseline_graph_sha256": sha256_file(baseline_dir / "graph.json"),
                "variant_graph_sha256": {n: sha256_file(names[n] / "graph.json") for n in stores},
                "variant_vault_sha256": {n: vaults[n].sha256() for n in stores},
                "vectors_sha256": sha256_file(baseline_dir / "vectors.npz"),
                "chunks_sha256": base_hash,
            },
            "query_embeddings_computed": embedder.inner_calls,
            "answerable_questions": [r["question_id"] for r in rows],
            "skipped_questions": skipped,
            "descriptive_only": descriptive_only,
            "semantic_arms_missing_for": missing_sem,
            "control_arm_flat_differs": False,
        },
        "variants": per_variant,
        "per_question": rows,
    }


async def embed_labels(args: argparse.Namespace) -> dict[str, Any]:
    data = Path(args.data)
    settings = settings_for(data)
    if is_live(settings) and not args.allow_paid:
        raise RunInvalid(
            "live (paid) mode is configured; pass --allow-paid to embed the page labels"
        )
    configure_logging("WARNING")
    store = JsonVaultStore(data / VAULT_FILE)
    vault = store.vault()
    if vault is None:
        raise RunInvalid(f"{data} has no {VAULT_FILE}")
    container = build_container(settings)
    before = container.ledger.month_total()
    vectors = await embed_page_labels(vault, container.embedder)
    store.put_label_vectors(vectors)
    store.save()
    return {
        "pages_embedded": len(vectors),
        "spent_usd": round(container.ledger.month_total() - before, 6),
        "mode": {"embed": settings.arcana_embed_mode},
    }


def audit_sample(variant: Path, n: int, seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """`n` asserted and `n` co-mention links, a fixed-seed sample, shuffled so a reader cannot tell the kind. The reader judges
    only whether the two concepts are related as the sentence shows; the key (kept apart) holds the kind and relation."""
    store = JsonVaultStore(variant / VAULT_FILE)
    vault = store.vault()
    if vault is None:
        raise RunInvalid(f"{variant} has no {VAULT_FILE}")
    rng = random.Random(seed)
    asserted = sorted(
        (x for x in vault.links if x.kind == "asserted"),
        key=lambda x: (x.src, x.dst, x.relation or ""),
    )
    co = sorted((x for x in vault.links if x.kind == "co_mention"), key=lambda x: (x.src, x.dst))
    picked = rng.sample(asserted, min(n, len(asserted))) + rng.sample(co, min(n, len(co)))
    rng.shuffle(picked)
    items, key = [], {}
    for i, link in enumerate(picked, 1):
        items.append(
            {
                "id": i,
                "a": vault.pages[link.src].label,
                "b": vault.pages[link.dst].label,
                "sentence": link.evidence or "(no sentence stored)",
            }
        )
        key[str(i)] = {
            "kind": link.kind,
            "relation": link.relation,
            "passages": len(link.chunk_ids),
        }
    return items, {"seed": seed, "n_per_kind": n, "key": key}


def audit_markdown(items: list[dict[str, Any]]) -> str:
    lines = [
        "# Link audit sample",
        "",
        "For each item: do the two concepts relate as the sentence shows? Mark yes, weak or no. The kind of link is hidden on purpose.",
        "",
    ]
    for it in items:
        lines += [
            f"**{it['id']}.** {it['a']}  /  {it['b']}",
            f"> {it['sentence']}",
            "",
            "yes / weak / no",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compare vault retrieval with the frozen graph retrieval (D-35)."
    )
    sub = ap.add_subparsers(dest="command", required=True)
    e = sub.add_parser(
        "embed-labels", help="embed the pages' display labels once, into the vault file"
    )
    e.add_argument("--data", required=True)
    e.add_argument("--allow-paid", action="store_true")
    e.add_argument("--allow-dirty", action="store_true", help="for tests only")
    c = sub.add_parser("compare", help="run the frozen and the vault arms over every directory")
    c.add_argument("--baseline", required=True)
    c.add_argument(
        "--variants", required=True, help="comma-separated directories, each with a vault.json"
    )
    c.add_argument("--questions-file", default=str(ROOT / "eval" / "questions.yaml"))
    c.add_argument("--gold-dir", default=str(ROOT / "eval" / "gold"))
    c.add_argument("--out", default=str(ROOT / "eval" / "results"))
    c.add_argument("--label", default="m2-vault")
    c.add_argument("--allow-paid", action="store_true")
    c.add_argument(
        "--allow-dirty",
        action="store_true",
        help="for tests only: a result should name committed code",
    )
    a = sub.add_parser("audit", help="draw the fixed-seed link sample for a person to read")
    a.add_argument("--variant", required=True)
    a.add_argument("--n", type=int, default=50)
    a.add_argument("--seed", type=int, default=20261007)
    a.add_argument("--out", default=str(ROOT / "eval" / "results"))
    args = ap.parse_args(argv)

    try:
        if args.command == "audit":
            items, key = audit_sample(Path(args.variant), args.n, args.seed)
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            (out / f"{stamp}-m2-audit-sample.json").write_text(
                json.dumps(items, indent=2), encoding="utf-8"
            )
            (out / f"{stamp}-m2-audit-sample.md").write_text(
                audit_markdown(items), encoding="utf-8"
            )
            (out / f"{stamp}-m2-audit-key.json").write_text(
                json.dumps(key, indent=2), encoding="utf-8"
            )
            print(f"wrote {len(items)} items to {out}")
            return 0
        state = git_state()
        if not args.allow_dirty and (state["commit"] is None or state["dirty"] is not False):
            print(
                f"commit first: a result must name the code it ran on ({state['changed_files']})",
                file=sys.stderr,
            )
            return 2
        if args.command == "embed-labels":
            print(json.dumps(asyncio.run(embed_labels(args)), indent=2))
            return 0
        result = asyncio.run(compare(args))
    except RunInvalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{args.label}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {path}")
    print(json.dumps({n: v["gate"] for n, v in result["variants"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
