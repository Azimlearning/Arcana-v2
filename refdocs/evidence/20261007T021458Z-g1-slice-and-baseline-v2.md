# G1: the slice the rule chose, and the baseline with the amended measures

Results: `eval/results/20261007T021458Z-graph-quality-baseline-v2.json` (tool `eval/graph_quality.py`, commit `8428a59`, clean tree, pinned hashes verified, no model call, no spend). The slice below is the output of `uv run python eval/graph_variant.py choose --from data/eval-live-live` at the same commit: it reads the gold and the chunk counts only, and no arm was run.

## The slice (the rule written before the choice, D-34)

Rule: greedy by newly answerable frozen questions per chunk, ties to the lower arxiv id, 450-chunk budget.

| Paper | Chunks | Questions it makes answerable (newly, in the order chosen) |
|---|---|---|
| 2312.10997v5 (the RAG survey) | 117 | 14 (14 new) |
| 2408.04948v1 (HybridRAG) | 56 | 11 (4 new) |
| 2310.11511v1 (Self-RAG) | 112 | 2 (1 new) |
| **Slice** | **285** | **19 of 20 questions** (all but the control `q-single-01`, whose gold the corpus does not hold) |

So the retrieval comparison on this slice has **19 answerable questions**, which is more than the ten the protocol requires for the retrieval clause to be evaluated (still one ingestion, one corpus slice, no significance test claimed).

## Cost of the slice (cost auditor's per-chunk range, applied to 285 chunks)

About $1.2 (low), **$1.9 (expected)** and $3.0 (high), plus the one-paper pilot (Ragas, 35 chunks: about $0.23, ceiling $0.40). Pilot plus slice is about $2.1 expected and $3.4 high, against $3.83 left of the $10 cap; the full 16-paper run still needs the cap raised. The pilot's measured cost per chunk replaces these figures before the slice is confirmed.

## The baseline, with the measures the gate rests on (whole pinned graph)

| Measure | Value |
|---|---|
| Chunks that name at least one concept | 98.9 percent |
| Chunks that carry at least one relation | 98.4 percent |
| Edges per node | 1.25 |
| Share of edge ends owned by the ten largest nodes | 9.3 percent |
| Share of node-to-chunk links owned by the largest one percent of nodes | 17.4 percent |
| Nodes whose label occurs in one of their own chunks | 86.5 percent |

The gate compares the variant with the same slice's baseline numbers (`compare` computes both), not with these whole-graph figures. Limits are as in the first baseline record: structure only, a lexical test, one ingestion.
