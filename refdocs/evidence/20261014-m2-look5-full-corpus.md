# M2 Look 5: the `atomic2` graph and the vault over all 16 papers (1,570 passages)

Result: `eval/results/20261014T151443Z-m2-look5.json` (commit `4d4e5a5`, clean tree). Protocol: D-35 with amendments A1 to A9, A9 written and committed before the run; the prompt `g2-1`, the `vault-1` constants and the gate are unchanged. Baseline: `data/eval-live-live` (the pinned free-form graph and the P1 benchmark's stores; the `flat` control is identical in every directory, checked). Variants: `data/m2/full-freeform-vault1` (the vault over the free-form graph, Look 3's directory) and `data/m2/atomic2-full-vault1` (the new build and its vault). 19 answerable questions; descriptive only.

## Spend and provenance of the build (disclosed in full)

| Item | Amount |
|---|---|
| `atomic2` build, run 1 (14 of 16 papers, then a provider failure, see below) | $4.715877 |
| `atomic2` build, run 2 (`--resume`, the remaining 2 papers) | $0.401459 |
| **The build, total (confirmed range $3 to $6.50; audit expected $4.92)** | **$5.117336** |
| Page-label embeddings (6,551 labels) | $0.003516 |
| Question embeddings (19) and a one-call diagnostic | about $0.0002 |
| Month total after the work: $13.94 of the $15 cap (Azim raised it from $10 on 2026-10-14) | |

**The build was made by two provider routes and in two invocations.** Run 1 started on Anthropic (`claude-haiku-4-5-20251001`). At 22:36 the Anthropic account's own credit balance ran out (HTTP 400, classified since as `status_400_credit_balance_low`; the monthly cap in `.env` is a separate thing) and the seam's fallback served **942 of the build's calls through OpenRouter** (`anthropic/claude-haiku-4.5`, the same model by another route; every call was priced and booked on the ledger). Run 1 then stopped on one chunk that failed on both routes at once (a transient OpenRouter rate limit): 14 papers were built, the 15th was discarded by design and the 16th not attempted. The tool had no resume, so a `--resume` was written (committed before run 2): it keeps the finished papers (graph, claims, cost), builds only the rest and sums the spend. **Consequence:** the graph is one build in two invocations over two routes of the same model; nothing in the prompt, the server's checks or the stored fields depends on the route, but a rebuild would differ (no temperature control) and the route mix is part of the record. Extraction failures: 1 passage in 1,570 (0.06 percent). Claims 4,811.

## What was built

| | free-form (the baseline graph) | `atomic2` (this build) |
|---|---|---|
| Nodes, edges | 11,173, 13,972 | **6,833, 5,646** |
| Edges stated in one sentence | 77.9 percent | 88.0 percent |
| Pages in the vault, linked by either kind | 88.9 percent | 77.6 percent |
| Pages with an asserted link | 79.7 percent | 56.4 percent |
| Claims | 0 | 4,811 |
| Question words the frozen resolver recognises | **0.657** | 0.632 |

The `atomic2` graph is about 60 percent of the nodes and 40 percent of the edges of the free-form one, with a higher share of edges stated in one sentence and a lower share of linked pages.

## Retrieval (19 questions; headline pairs named in A9 before the run; nDCG@10, exact Wilcoxon p)

| Pair | From | To | Difference | Better / tied / worse | p |
|---|---|---|---|---|---|
| **`vault` against its own directory's frozen `graph`** (atomic2) | 0.1028 | 0.1371 | **+0.0344** | 8 / 7 / 4 | 0.52 |
| **`hybrid_vault` against its own frozen `hybrid`** (atomic2) | 0.1823 | 0.1822 | -0.0000 | 7 / 9 / 3 | 0.57 |
| **`hybrid_vault` against the baseline's frozen `hybrid`** | 0.2080 | 0.1822 | **-0.0257** | 3 / 7 / 9 | 0.11 |
| **`hybrid_vault` against the baseline's `flat` control** | 0.1686 | 0.1822 | +0.0137 | 6 / 8 / 5 | 0.41 |

Reference points over the same questions: the baseline's frozen `hybrid` against `flat` is **+0.0394** (7 / 8 / 4, p = 0.15; Look 3's number, reproduced), the frozen `hybrid` over the `atomic2` graph is 0.1823 against `flat` +0.0137, and `vault` against the baseline's free-form frozen `graph` is +0.0239 (7 / 5 / 7, p = 0.95). Recall@10: `vault` +0.058 over its own frozen graph (7 / 9 / 3). The vault over the free-form graph (Look 3's configuration, repeated here): `vault` +0.0111 over the frozen graph, `hybrid_vault` -0.0331 against the frozen hybrid (4 / 8 / 7). Exploratory arms: `hybrid_vault_sem` 0.1811; without co-mentions `vault` 0.1283 (-0.009 from `vault`); without the spread discount `vault` 0.1269 (-0.010) and `hybrid_vault` 0.1964 (**+0.014 over its own frozen hybrid, 8 / 8 / 3**, the only arm to clearly exceed it); without claims `vault` 0.1336 (claims add about +0.004). The semantic variant adds nothing here.

## The gate

Clause 1 (coverage) and clause 2 (links) pass; **clause 3 (question words recognised not below the baseline) fails, and not by construction this time**: 0.632 against 0.657, because the `atomic2` graph has fewer concept nodes to match a question's words against. `ready_for_azim_to_decide` is false. The retrieval clause (no drop worse than -0.05) passes (-0.0257).

## What this look says, and what it does not

- **Azim's hypothesis, graph retrieval gains with corpus size, is supported only for the free-form graph and only descriptively:** the frozen hybrid's gap over `flat` goes from -0.022 at 285 passages to +0.039 at 1,570 (Look 3), not significant (p = 0.15).
- **The new builder and the vault do not improve on it at full scale.** The vault clearly strengthens the *graph signal itself* (+0.034 nDCG@10, +0.058 recall over its own frozen graph, as on the slice: +0.077 there), but that does not carry into the fused result: `hybrid_vault` is level with its own frozen hybrid, and **below the baseline's free-form frozen hybrid by 0.026** (3 better, 9 worse, p = 0.11).
- **Why, by the numbers (not tested as causes):** the `atomic2` graph is smaller (fewer nodes recognise fewer question words: 0.632 against 0.657), so its frozen graph signal is weaker (0.103 against 0.113); the vault repairs part of that and cannot add a node the graph does not have.
- **Against no graph at all:** `hybrid_vault` is +0.014 over `flat`, a smaller margin than the free-form frozen hybrid's +0.039. Neither is significant on 19 questions.
- **What it does not show:** that any difference here is more than noise (every p is 0.11 or above); that the edges are right (the link audit samples are unread); that a different extraction prompt or a larger corpus would not change the ordering. The vault's value in this project is the notes, links, claims, quiz and mastery it supports (all built and exercised), not a retrieval gain: this look is the evidence for that claim and its limit.

## Limits

19 questions, one build per graph, no temperature control (a rebuild would differ), two provider routes of one model in two invocations, descriptive only. The ablations are exploratory. A candidate depth of 30 per signal (P3-lite evidence) was **not** applied to these arms; it raised the frozen hybrid's Recall@10 from 0.212 to 0.305 on its own and is a separate, declared question for a final benchmark amendment.

## Reproduction

`uv run python eval/graph_variant.py rebuild --slice data/eval-live-live --to data/m2/atomic2-full --builder atomic2 --max-usd 6.50 --allow-paid` (then `--resume` with `--max-usd 1.00`), `eval/vault_tool.py build`, `eval/vault_compare.py embed-labels` and `compare` as in D-35 A9.
