# Evaluation harness

Measures what each retrieval signal contributes (D-15). Automated evaluation only (D-06): no user study.

```bash
uv run python eval/run_ablation.py --questions q-cross-01,q-single-01 --arms all \
    --corpus-dir ../Arcana/eval/corpus
```

| File | What it is |
|---|---|
| `questions.yaml` | v1's 20 pre-registered questions, byte-identical below a provenance header (D-21). Frozen. |
| `corpus/MANIFEST.json` | v1's 16-paper manifest, byte-identical. The PDFs are not in this repo (copyright); point `--corpus-dir` at them. |
| `gold/` | Hand-annotated gold passages and their format. See `gold/README.md`. |
| `metrics.py` | Recall@10 and nDCG@10 against gold passages, with the frozen relevance rule. |
| `ragas_metrics.py` | RAGAS `NonLLMContextRecall` and `NonLLMContextPrecisionWithReference`, imported lazily. |
| `run_ablation.py` | The five-arm runner. Writes one JSON per run to `results/`. |
| `tests/` | Metric, frozen-asset and runner tests (`uv run pytest eval/tests`). |

## The five arms

`dense`, `sparse` (BM25), `graph`, `flat` (dense plus sparse) and `hybrid` (all three). They differ only in
which signals are enabled. `flat` against `hybrid` is the comparison that measures what the graph adds.

## What a results file contains

Per question and arm: Recall@10, nDCG@10, the RAGAS context metrics (or `null` if RAGAS is not installed),
ranking length, latency, the graph entity-resolution report and the chunk ids returned. For the run: the
protocol stamp (every frozen retrieval constant), the relevance rule, the mode, content hashes of the
questions, manifest, gold files, graph and vectors, and per-document ingestion facts.

## Rules the runner enforces

- Corpus parity must hold before anything runs; otherwise the run is refused.
- The query embedding is computed once per question and shared by every arm.
- A signal that fails makes that question-arm **invalid**: `null` metrics, never zero, and the process exits
  with code 3.
- A question without gold has `null` metrics and is excluded from aggregates.
- The empty-graph gate: if more than 30 percent of questions resolve to no graph entities, that is an
  entity-resolution defect, not a finding about graphs. Enforced from 10 questions; below that it is reported.
- Live (paid) mode is refused unless `--allow-paid` is passed.

## Fake mode is a plumbing check

With `ARCANA_LLM_MODE=fake` and `ARCANA_EMBED_MODE=fake` the embeddings are hashed bags of words and the
extractor is a stand-in. The results file says so in a `warning` field. Those numbers must never be reported
as retrieval results. Real numbers need live providers (P0 task 10) and the hand-written benchmark gold (P1).

## RAGAS

RAGAS is not installed yet: it adds about 94 packages and the development drive is nearly full. Until it is
installed the two RAGAS metrics are `null` with a reason; nothing substitutes for them. To install:
`uv add ragas rapidfuzz`, then re-run.
