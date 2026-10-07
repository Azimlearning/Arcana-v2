# ruff: noqa: E402  (an offline command-line tool: the path is set before the imports)
"""Free probes behind the Mark 2 plan (M2, D-35): what server-side sentence anchoring and a co-mention layer would recover.

    uv run python eval/m2_probes.py data/g1

No model call and no network. Reads `diag_replies.json` (four real replies saved during the G1 pilot) and the Mark 1 slice
graph in `<dir>/slice-atomic`. Prints three results; the numbers are recorded in `refdocs/evidence/20261007-m2-brainstorm-probes.md`.
It does not touch any store."""

import json
import re
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, ".")
getattr(sys.stdout, "reconfigure", lambda **_: None)(encoding="utf-8")

from api.ingestion.atomic import label_in_text
from api.llm.json_reply import parse_json_object
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

SCR = Path(sys.argv[1])  # the g1 directory, e.g. data/g1
SENT = re.compile(r"(?<=[.!?])\s+")

# 1. Of the concepts the model proposed in the four saved replies, how many have a label the server could find in the chunk?
replies = json.loads((SCR / "diag_replies.json").read_text(encoding="utf-8"))
proposed = anchored = 0
rel_total = rel_anchor = 0
for item in replies:
    parsed = parse_json_object(item["reply"])
    text = item["chunk"]
    labels = [c.get("label", "") for c in parsed.get("concepts", [])]
    for label in labels:
        proposed += 1
        anchored += bool(label) and label_in_text(text, label)
    sents = [s for s in SENT.split(" ".join(text.split())) if s]
    for rel in parsed.get("relations", []):
        rel_total += 1
        a, b = rel.get("src", ""), rel.get("dst", "")
        rel_anchor += any(label_in_text(s, a) and label_in_text(s, b) for s in sents)
print(
    f"concepts proposed {proposed}, label found in chunk {anchored} ({anchored / max(proposed, 1):.0%})"
)
print(
    f"relations proposed {rel_total}, both labels in one sentence {rel_anchor} ({rel_anchor / max(rel_total, 1):.0%})"
)

# 2. On the Mark 1 slice graph: a deterministic sentence co-mention layer among its own concepts.
variant = SCR / "slice-atomic"
graph = NetworkXGraphStore(variant / "graph.json")
docs = SqliteDocStore(make_engine(variant / "arcana.db"))
nodes = graph.nodes()
by_chunk: dict[str, list] = {}
for n in nodes:
    for c in n.chunk_ids:
        by_chunk.setdefault(c, []).append(n)
chunks = docs.all_chunks()
pairs: set[tuple[str, str]] = set()
chunks_with_pair = 0
for chunk in chunks:
    here = by_chunk.get(chunk.id, [])
    found = False
    for s in SENT.split(" ".join(chunk.text.split())):
        inside = [n for n in here if label_in_text(s, n.label)]
        for a, b in combinations(sorted(inside, key=lambda n: n.id), 2):
            if a.id != b.id:
                pairs.add((a.id, b.id))
                found = True
    chunks_with_pair += found
asserted = {(min(e.src, e.dst), max(e.src, e.dst)) for e in graph.edges()}
edgeless_before = sum(1 for n in nodes if not any(n.id in p for p in asserted))
touched = {x for p in pairs | asserted for x in p}
print(
    f"mark1 slice: {len(nodes)} nodes, {len(asserted)} asserted pairs, {edgeless_before} nodes with no edge"
)
print(
    f"sentence co-mention pairs among the same nodes: {len(pairs)}; chunks with at least one: {chunks_with_pair}/{len(chunks)}"
)
print(f"nodes with no link of either kind: {len(nodes) - len(touched)}")

# 3. Generic concepts: labels whose node is mentioned in many chunks (candidates for a hub penalty)
spread = sorted(((len(n.chunk_ids), n.label) for n in nodes), reverse=True)[:12]
print("most-mentioned notes:", spread)
