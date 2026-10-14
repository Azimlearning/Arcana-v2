# The question-set extension: 19 new questions, run and pooled (D-39, D-40)

Results: `eval/results/20261014T191800Z-ext-benchmark.json` (five frozen arms, baseline stores), `20261014T192055Z-ext-rerank.json` (depth controls and cross-encoder arms), `20261014T192526Z-m2-ext.json` (frozen and vault arms over the free-form and `atomic2` directories), `20261014T192628Z-extension-pooled.json` (the pooled pairs, `eval/pooled_extension.py`). Protocol and headline pairs: `refdocs/plans/2026-10-15-question-set-extension.md`, written and committed before any arm was run on the new questions. Gold approved by Azim on 2026-10-15 and pinned; verified verbatim and reachable (0 problems). Stores hash-checked against the baseline's; the run code was committed and the tree clean. Spend: about $0.0002 (question embeddings, three tools).

## Arm means on the 19 new questions

| Arm | nDCG@10 | Recall@10 |
|---|---|---|
| dense | 0.396 | 0.551 |
| flat (control) | 0.394 | 0.555 |
| hybrid (frozen) | 0.352 | 0.516 |
| sparse | 0.243 | 0.400 |
| graph | 0.132 | 0.195 |

The new questions are easier than the original 19 (flat 0.394 against 0.169), as expected from single-paper mechanism questions: single-document 8 questions (flat 0.566, hybrid 0.537, graph 0.252), cross-document 11 (flat 0.268, hybrid 0.217, graph 0.044).

## Headline pairs

| Pair | Sample | From | To | Difference | Better / tied / worse | p |
|---|---|---|---|---|---|---|
| **H1 `hybrid_n30` against frozen `hybrid`, Recall@10 (the rule for D-38)** | new 19 | 0.5158 | 0.5088 | **-0.0070** | 1 / 17 / 1 | 1.0 |
| H1 same, nDCG@10 | new 19 | 0.3519 | 0.3357 | -0.0162 | 5 / 8 / 6 | 0.70 |
| H1 same, the original 19 (where 30 was chosen), Recall@10 | original 19 | 0.2123 | 0.3054 | +0.0931 | 6 / 12 / 1 | 0.094 |
| H1 same, pooled, Recall@10 | pooled 38 | 0.3640 | 0.4071 | +0.0430 | 7 / 29 / 2 | 0.19 |
| H2 `hybrid` against `flat`, nDCG@10 | new 19 | 0.3937 | 0.3519 | -0.0417 | 2 / 6 / 11 | 0.068 |
| H2 same | original 19 | 0.1686 | 0.2080 | +0.0394 | 7 / 8 / 4 | 0.15 |
| **H2 same, pooled** | **pooled 38** | 0.2811 | 0.2800 | **-0.0012** | 9 / 14 / 15 | 0.69 |
| H3 `hybrid_vault` (atomic2) against baseline `hybrid`, nDCG@10 | pooled 38 | 0.2800 | 0.2903 | +0.0103 | 11 / 14 / 13 | 0.86 |
| H4 `vault` against its own frozen `graph` (atomic2), nDCG@10 | pooled 38 | 0.1071 | 0.1483 | +0.0412 | 14 / 15 / 9 | 0.34 |
| H4 same, Recall@10 | pooled 38 | 0.1687 | 0.2361 | +0.0674 | 10 / 24 / 4 | 0.11 |

## What this says

- **D-38 is not confirmed and is reversed by the rule fixed in advance.** On the questions it was not chosen on, 30 candidates per signal changed Recall@10 by -0.007 (one question better, one worse, seventeen unchanged). The original +0.093 does not replicate. Pooled it is +0.043 (p = 0.19), not significant, and the rule was written for the new questions alone. The product path is back at 10 (D-40).
- **The graph signal's gain over flat does not replicate.** The +0.039 over `flat` on the original 19 (p = 0.15) becomes -0.042 on the new 19 (p = 0.068; 2 better, 11 worse) and **-0.001 pooled** (p = 0.69). On this corpus, with these questions, fused hybrid retrieval is not shown to beat dense retrieval alone; the control (`flat`) is at least as good. The new questions are easier and lexically closer to the papers' own wording, which favours flat and dense; the original, harder, cross-document questions are where the graph gave its small, non-significant edge.
- **The vault is at best a small positive, not significant.** Over its own frozen graph signal +0.041 nDCG@10 pooled (p = 0.34, recall +0.067, p = 0.11); fused (`hybrid_vault` over the baseline hybrid) +0.010 (p = 0.86). On the new questions alone the `atomic2` fused arm is +0.046 over the baseline hybrid, and still within noise.
- **The re-ranker is again not shown to help** (rerank_n50 against hybrid_n50 +0.0015, p = 0.97; against hybrid -0.023, p = 0.71).

## Limits

38 questions in two sets drawn differently; the extension was drafted by the system's author and leans to single-paper mechanism questions; no contradiction questions; gold completeness is unproven; the original 19 and the new 19 differ in difficulty, so pooled means mix two populations (the per-sample rows are the honest ones); no p-value in the table is below 0.05, so no pair here is a significant effect.
