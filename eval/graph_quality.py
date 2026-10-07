"""The structure of a knowledge graph, measured with no model call (G1.1).

    uv run python eval/graph_quality.py --data-dir data/eval-live-live [--docs <doc id> ...] [--label baseline]

What it measures, for the whole graph or for the slice that belongs to some documents: how many edges the text of their
source chunk actually states (both endpoint labels in the chunk, and in one sentence of it), how many are bare
co-mentions (a generic relation word, or no chunk text naming both ends), the share a `GraphView` could draw, node
statistics (singletons, nodes shared by several documents, very short or sentence-like labels), the degree distribution
and the largest hubs, and the most common relation strings.

It is a measure of STRUCTURE. It says nothing about answer quality, and the shares below are over the whole graph, not
over the neighbourhoods of the 20 study questions (so they differ from the study's 44 percent drawable share, which was
measured on those neighbourhoods). It reads the stores and writes nothing to them; it makes no network call.

PROTOCOL (fixed before the run): the definitions below, applied unchanged to any graph store, so the current graph and an
experimental one are measured by the same code. A run records the code's commit, whether the tree was clean, and the
hash of the graph file and of the chunk store.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `api` and `eval` import when run as a script

from api.genui.text import MIN_LABEL_CHARS, MIN_QUOTE_CHARS, label_in_quote, normalise
from api.stores.doc_store import Chunk
from api.stores.graph_store import Edge, GraphStore, Node
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from eval.run_ablation import ROOT, chunks_sha256, git_state, sha256_file

# Relations that say only that two things appear together. A relation in this list is a co-mention whatever the text says.
GENERIC_RELATIONS = frozenset(
    {
        "related to",
        "relates to",
        "associated with",
        "connected to",
        "linked to",
        "mentions",
        "co occurs with",
        "cooccurs with",
        "relationship",
        "has relationship with",
    }
)
MAX_LABEL_CHARS = 120  # the GraphView cap on a label
MAX_RELATION_CHARS = 80  # the GraphView cap on a relation
FRAGMENT_WORDS = 8  # a label of more than this many words reads as a sentence fragment, not a concept name
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


def relation_words(relation: str) -> str:
    """The relation as stored, with underscores and runs of space read as single spaces, lower case."""
    return " ".join(relation.replace("_", " ").lower().split())


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCES.split(normalise(text)) if s]


def edge_facts(edge: Edge, labels: Mapping[str, str], chunk_text: str | None) -> dict[str, bool]:
    """What the source chunk's text lets us say about one edge."""
    src, dst = labels.get(edge.src, ""), labels.get(edge.dst, "")
    both_in_chunk = bool(chunk_text) and label_in_quote(chunk_text or "", src) and label_in_quote(chunk_text or "", dst)
    in_one_sentence = False
    sentence_ok = False
    if chunk_text and both_in_chunk:
        for s in sentences(chunk_text):
            if label_in_quote(s, src) and label_in_quote(s, dst):
                in_one_sentence = True
                sentence_ok = len(normalise(s)) >= MIN_QUOTE_CHARS
                break
    relation = relation_words(edge.relation)
    labels_ok = all(MIN_LABEL_CHARS <= len(x.strip()) <= MAX_LABEL_CHARS for x in (src, dst))
    return {
        "chunk_missing": chunk_text is None,
        "both_in_chunk": both_in_chunk,
        "in_one_sentence": in_one_sentence,
        "generic": relation in GENERIC_RELATIONS,
        "co_mention": relation in GENERIC_RELATIONS or not in_one_sentence,
        "drawable": (
            in_one_sentence
            and sentence_ok
            and labels_ok
            and edge.src != edge.dst
            and 0 < len(relation) <= MAX_RELATION_CHARS
        ),
    }


def share(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def distribution(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]  # noqa: E731
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "mean": round(statistics.fmean(ordered), 3),
        "p90": pick(0.9),
        "p99": pick(0.99),
        "max": ordered[-1],
    }


def measure(
    nodes: Iterable[Node],
    edges: Iterable[Edge],
    chunk_texts: Mapping[str, str],
    doc_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """The structural metrics of a graph, or of its slice for `doc_ids`. Pure: no store, no network."""
    node_list = list(nodes)
    edge_list = list(edges)
    if doc_ids is not None:
        edge_list = [e for e in edge_list if e.doc_id in doc_ids]
        sliced: list[Node] = []
        for n in node_list:
            kept_docs = tuple(d for d in n.doc_ids if d in doc_ids)
            if not kept_docs:
                continue
            kept_chunks = tuple(c for c in n.chunk_ids if c.split("_c_", 1)[0] in doc_ids)
            sliced.append(Node(n.id, n.label, n.type, kept_docs, kept_chunks))
        node_list = sliced
    labels = {n.id: n.label for n in node_list}
    # Endpoints that fall outside the slice (an edge's other end lives in a document outside it) keep their labels.
    for n in nodes if doc_ids is not None else ():
        labels.setdefault(n.id, n.label)

    facts = [edge_facts(e, labels, chunk_texts.get(e.chunk_id)) for e in edge_list]
    total = len(facts)
    count = lambda key: sum(1 for f in facts if f[key])  # noqa: E731

    degree: Counter[str] = Counter()
    for e in edge_list:
        degree[e.src] += 1
        degree[e.dst] += 1
    relation_counts = Counter(relation_words(e.relation) for e in edge_list)
    word_count = lambda label: len(label.split())  # noqa: E731
    node_total = len(node_list)

    # Coverage, concentration and the label check: defined the same for any graph, and not satisfied by construction
    # by a builder that checks sentences (G1.4).
    in_scope = [c for c in chunk_texts if doc_ids is None or c.split("_c_", 1)[0] in doc_ids]
    with_node = {c for n in node_list for c in n.chunk_ids}
    with_edge = {e.chunk_id for e in edge_list}
    chunk_total = len(in_scope)
    total_degree = sum(degree.values())
    top10 = sum(d for _, d in degree.most_common(10))
    links = sorted((len(n.chunk_ids) for n in node_list), reverse=True)
    top_percent = links[: max(1, -(-node_total // 100))] if node_total else []
    own_chunks = sum(1 for n in node_list if any(label_in_quote(chunk_texts.get(c, ""), n.label) for c in n.chunk_ids))

    return {
        "chunk_coverage": {
            "chunks": chunk_total,
            "with_a_concept": share(len(with_node & set(in_scope)), chunk_total),
            "with_a_relation": share(len(with_edge & set(in_scope)), chunk_total),
        },
        "edges_per_node": round(total / node_total, 4) if node_total else None,
        "hub_concentration": {
            "top10_degree_share": share(top10, total_degree),
            "top_1_percent_share_of_chunk_links": share(sum(top_percent), sum(links)),
        },
        "nodes_label_in_own_chunks": {"count": own_chunks, "share": share(own_chunks, node_total)},
        "documents": None if doc_ids is None else sorted(doc_ids),
        "nodes": node_total,
        "edges": total,
        "edges_stated_in_chunk": {"count": count("both_in_chunk"), "share": share(count("both_in_chunk"), total)},
        "edges_stated_in_one_sentence": {
            "count": count("in_one_sentence"),
            "share": share(count("in_one_sentence"), total),
        },
        "edges_generic_relation": {"count": count("generic"), "share": share(count("generic"), total)},
        "edges_co_mention": {"count": count("co_mention"), "share": share(count("co_mention"), total)},
        "edges_drawable": {"count": count("drawable"), "share": share(count("drawable"), total)},
        "edges_with_missing_chunk": count("chunk_missing"),
        "nodes_singleton": {
            "count": sum(1 for n in node_list if len(n.chunk_ids) <= 1),
            "share": share(sum(1 for n in node_list if len(n.chunk_ids) <= 1), node_total),
        },
        "nodes_in_two_or_more_documents": {
            "count": sum(1 for n in node_list if len(n.doc_ids) >= 2),
            "share": share(sum(1 for n in node_list if len(n.doc_ids) >= 2), node_total),
        },
        "nodes_with_no_edge": {
            "count": sum(1 for n in node_list if degree[n.id] == 0),
            "share": share(sum(1 for n in node_list if degree[n.id] == 0), node_total),
        },
        "labels_very_short": sum(1 for n in node_list if len(n.label.strip()) < 3),
        "labels_all_digits": sum(1 for n in node_list if n.label.strip().replace(".", "").isdigit()),
        "labels_sentence_like": sum(1 for n in node_list if word_count(n.label) > FRAGMENT_WORDS),
        "degree": distribution([degree[n.id] for n in node_list]),
        "largest_hubs": [{"label": labels.get(node_id, node_id), "degree": d} for node_id, d in degree.most_common(10)],
        "distinct_relations": len(relation_counts),
        "relation_share_of_top_20": share(sum(c for _, c in relation_counts.most_common(20)), total),
        "most_common_relations": [{"relation": r, "count": c} for r, c in relation_counts.most_common(15)],
        "node_types": dict(Counter((n.type or "(none)") for n in node_list).most_common(10)),
    }


PROTOCOL = (
    "Structure only, no model call. Coverage is the share of the chunks in scope that any node (or any edge) names; hub "
    "concentration is the share of all edge ends owned by the ten largest nodes, and the share of all node-to-chunk links "
    "owned by the largest one percent of nodes; the label check asks whether a node's label occurs as a whole word in "
    "one of its own chunks. Definitions: an edge is 'stated in the chunk' when its source chunk's text contains "
    "both endpoint labels as whole words; 'stated in one sentence' when one sentence of that chunk contains both; a "
    "'generic relation' is one of a fixed list of co-occurrence words; a 'co-mention' is a generic relation or an edge "
    "no single sentence of its chunk states; 'drawable' is stated in one sentence of at least the minimum quote length "
    "with labels and relation within the GraphView caps. Shares are over the whole graph (or the slice), not over the "
    "neighbourhoods of any question."
)


def load(data_dir: Path) -> tuple[GraphStore, list[Chunk], dict[str, str]]:
    graph = NetworkXGraphStore(data_dir / "graph.json")
    docs = SqliteDocStore(make_engine(data_dir / "arcana.db"))
    return graph, docs.all_chunks(), {d.id: d.title for d in docs.list_documents()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The structure of a knowledge graph, measured with no model call (G1.1).")
    ap.add_argument("--data-dir", required=True, help="a data directory holding graph.json and arcana.db")
    ap.add_argument("--docs", nargs="*", default=None, help="measure only the slice for these document ids")
    ap.add_argument("--label", default="graph-quality")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results"))
    ap.add_argument("--expect-graph-sha256", default=None)
    ap.add_argument("--expect-chunks-sha256", default=None)
    ap.add_argument("--allow-dirty", action="store_true", help="for tests only: a result should name committed code")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    if not (data_dir / "graph.json").exists() or not (data_dir / "arcana.db").exists():
        print(f"no graph.json and arcana.db in {data_dir}", file=sys.stderr)
        return 2
    code = git_state()
    if not args.allow_dirty and (code["commit"] is None or code["dirty"] is not False):
        print(f"commit first: the result must name the code it ran on ({code['changed_files']})", file=sys.stderr)
        return 2

    graph, chunks, titles = load(data_dir)
    texts = {c.id: c.text for c in chunks}
    hashes = {"graph_sha256": sha256_file(data_dir / "graph.json"), "chunks_sha256": chunks_sha256(chunks)}
    for key, expected in (("graph_sha256", args.expect_graph_sha256), ("chunks_sha256", args.expect_chunks_sha256)):
        if expected and hashes[key] != expected:
            print(f"{key} differs from the pinned value ({hashes[key]} != {expected})", file=sys.stderr)
            return 2

    doc_ids = frozenset(args.docs) if args.docs else None
    if doc_ids and not doc_ids <= set(titles):
        print(f"unknown document ids: {sorted(doc_ids - set(titles))}", file=sys.stderr)
        return 2
    started = datetime.now(UTC)
    result = {
        "run": {
            "started": started.isoformat(),
            "label": args.label,
            "code": code,
            "data_dir": str(data_dir),
            "hashes": hashes,
            "protocol": PROTOCOL,
            "documents": {d: titles[d] for d in sorted(doc_ids or titles)},
        },
        "metrics": measure(graph.nodes(), graph.edges(), texts, doc_ids),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{started.strftime('%Y%m%dT%H%M%SZ')}-{args.label}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    m = result["metrics"]
    print(f"wrote {path}")
    print(
        f"nodes {m['nodes']}, edges {m['edges']}, stated in one sentence {m['edges_stated_in_one_sentence']['share']}, "
        f"co-mention {m['edges_co_mention']['share']}, drawable {m['edges_drawable']['share']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
