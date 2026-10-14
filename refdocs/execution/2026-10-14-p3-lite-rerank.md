# Execution: P3-lite, one re-rank engine, measured

> Plan: `refdocs/plans/2026-10-14-p3-trained-tools-deliberation.md`. ADR: D-37 (proposed).
> Status: **Done (2026-10-14).** R1 to R4 built and run; spend $0.000062 of a $0.01 ceiling; verdict: not shown to help.

## Before starting

- Read `CLAUDE.md`, preflight, D-12 (engines are additive), D-20 (the frozen fusion), `api/retrieval/`, `eval/run_ablation.py`, `eval/stats.py`.
- Read the current docs of the chosen runtime (CLAUDE.md rule 6): an ONNX cross-encoder through `fastembed` or `onnxruntime`, or `sentence-transformers`. Do not write against either from memory.
- Write the evaluation protocol (arms, depths, metrics, the paired test, what counts as "helped") **before any run**, as an amendment in the plan.

### Task R1: the `Engine` interface and the heuristic order

`api/engines/base.py`: `Engine` with `predict()` and `is_available()`; a `Reranker` protocol; the null reranker that returns the RRF order. **Verify:** a test that an unavailable or failing engine returns the RRF order unchanged.

### Task R2: the cross-encoder engine

`api/engines/rerank.py`: a pretrained cross-encoder run locally; candidates in, the same candidates re-ordered out; never adds or drops one. **Verify:** by-hand tests on a handmade pair set; a determinism test; failure falls back.

### Task R3: the arm in the ablation

`eval/run_ablation.py`: a new arm `hybrid_rerank` at depths 10, 30, 50, reading the same stored vectors. **Verify:** the frozen arms are byte-identical before and after; the harness refuses a run whose chunk or vector hashes differ.

### Task R4: the run and the report

Run on the 19 questions; paired test against `hybrid` and the vault arm; evidence record; D-37 confirmed or reversed. **Verify:** the result file records the commit, the hashes and the cost.

## Reality

- **R1 and R2.** `api/engines/base.py` (`Engine`, `RerankEngine`, `apply_rerank`: a re-ranker may only re-order; unavailable, failing, wrong-length or non-finite scores leave the heuristic's order, ties keep it, the reason is recorded), `api/engines/rerank.py` (the `fastembed` `TextCrossEncoder`, `Xenova/ms-marco-MiniLM-L-6-v2`, Apache-2.0; the current docs were read first). `fastembed` is the optional `engines` extra (ONNX runtime, no torch). 12 tests, the real model in one of them.
- **R3 (deviation).** The arms were not added to `run_ablation.py` (its protocol is frozen): a separate tool, `eval/rerank_compare.py`, reuses its helpers, refuses unless the stores' hashes and the recomputed frozen `hybrid` top ten equal the baseline's, and adds a **depth control** (`hybrid_nN`) so the engine is credited only for what it adds over a deeper candidate list.
- **R4.** One run, clean tree, 19 question embeddings, $0.000062. The result and what it does and does not say are in `refdocs/evidence/20261014-p3-rerank.md`.
- **Not done:** a domain-adapted or larger cross-encoder; chunk truncation to the best sentences; the engine over the vault arm. A depth-30 hybrid is recorded as a candidate protocol amendment for the final benchmark.
