# Execution: P3-lite, one re-rank engine, measured

> Plan: `refdocs/plans/2026-10-14-p3-trained-tools-deliberation.md`. ADR: D-37 (proposed).
> Status: **Not started. Waiting for Azim's go.** Nothing here spends money except the optional deeper-candidate re-run (about $0.001), which needs his confirmation of the amount first.

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
