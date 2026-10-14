# Plan: extending the question set (declared amendment, D-39)

> Execution doc: `refdocs/execution/2026-10-15-question-set-extension.md`. ADR: D-39 (proposed). Source of the need: every retrieval result so far rests on 19 answerable questions and none has p below 0.09 (Look 5, P3-lite, D-38).
> Status: **Done (2026-10-15).** Gold approved by Azim, registered, run and reported (about $0.0002); see `refdocs/evidence/20261015-question-set-extension.md` and D-40.

## Why this exists

The question set (19 answerable questions) cannot separate effects of the size this project has measured: the graph's +0.039 nDCG@10 (p = 0.15), the vault's +0.034 on its own graph signal (p = 0.52), the candidate depth's +0.093 Recall@10 (p = 0.094). A depth of 30 was chosen **after** seeing those 19, so those 19 cannot confirm it. New questions, drafted before any arm is run on them, are the only free way to (a) test D-38 on data it was not chosen on and (b) double the sample for the other headline pairs.

## What

- **19 new questions** in `eval/questions_ext.yaml` (ids `q-x-s01..08` single-document, `q-x-c01..11` cross-document) and their gold in `eval/gold_ext/`: 59 passages from all 16 papers, copied verbatim.
- **Method (the same as the 2026-10-06 gold):** from the papers' text only, by phrase search of the extracted PDF text, never from retrieval output; checked by `eval/verify_gold.py` (**0 problems**: every passage is a verbatim span of its page and is covered by at least one corpus chunk under the frozen relevance rule).
- **Not included, and why:** no contradiction questions (the corpus passages that disagree were not found by phrase search without reading far more text; a thin contradiction gold would be worse than none). So the extension is weighted to single-paper mechanism questions (8 of 19, against 4 of 20 originally); categories are reported separately.
- **Frozen assets stay byte-identical:** `questions.yaml`, `gold/`, the manifest, the protocol stamp. The extension lives in new files with its own pins, set at approval.

## Protocol (fixed before any arm is run on the new questions)

Arms: the five frozen arms on the baseline directory (`eval/run_ablation.py`, `--questions-file eval/questions_ext.yaml --gold-dir eval/gold_ext`); the vault arms over the free-form and `atomic2` directories (`eval/vault_compare.py compare`, as Look 5); the depth controls `hybrid_n30` and `hybrid_n50` (`eval/rerank_compare.py`, with its `--questions-file` added; the cross-encoder arms run too and stay exploratory).

Headline pairs (the only ones with a verdict; nDCG@10 and Recall@10, exact two-sided Wilcoxon from `eval/stats.py`):

| Pair | Sample | Rule |
|---|---|---|
| **H1: `hybrid_n30` against frozen `hybrid` (confirms or reverses D-38)** | the 19 **new** questions only | D-38 stands if the mean Recall@10 difference is positive; otherwise the candidate depth in `api/retrieval/types.py` returns to 10 by a new ADR. p is reported; no significance is claimed unless p < 0.05 |
| H2: frozen `hybrid` against `flat` | pooled 38, and the new 19 alone | reported; verdict "supported" only if p < 0.05 |
| H3: `hybrid_vault` (atomic2) against the baseline's frozen `hybrid` | pooled 38 | as H2 |
| H4: `vault` against its own directory's frozen `graph` | pooled 38 | as H2 |

Pooling is per-question scores from the earlier result files and the new ones, with the same arms, stores (hashes must equal), gold rule and code; the earlier numbers must reproduce first.

## Cost and spend

The question embeddings for 19 questions, once per tool (about $0.0001 each), ceiling $0.01. Month at $13.94 of the $15 cap.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The assistant drafted both the system and the questions | Medium: the questions may suit the system | Gold from paper text only, not retrieval; Azim approves each file; this limit is stated in the result |
| Many questions are single-paper mechanism questions, close to the paper's own wording | Medium: favours lexical overlap, may flatter `hybrid` and `flat` over `graph` | Categories reported separately; pooled and new-only both shown |
| Gold may be incomplete (a question can have more support than found) | Low to medium | The same limit the original gold states; recall is a floor |
| 38 questions is still small | Medium | Descriptive; verdicts only where p < 0.05 |

## Definition of done

Gold approved and pinned; the extension registered in `eval/frozen.py` with a test; the runs recorded with commit and clean tree; H1 to H4 reported as measured; D-38 confirmed or reversed.
