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
questions, manifest, gold files, graph, vectors and chunks, per-document ingestion facts, the commit and
whether the code was clean, the selected and excluded questions, and versions of the libraries and parameters
that shape results but are not part of the stamp (embedding model, extraction `max_tokens`, BM25 and parser
versions). The summary adds entity-resolution rates per graph-using arm.

## Declared amendments to the pre-registered protocol (constraint 9)

Every departure from the frozen question set or protocol is declared here and in `DECISIONS.md`.

1. **The first benchmark ran 19 questions, not 20 (ADR D-24), and `q-single-01` is a control (ADR D-26).**
   `q-single-01` ("What is Reciprocal Rank Fusion...") cannot be answered from the 16-paper corpus (ADR D-21);
   its gold is `unanswerable` and its metrics are `null`, so it contributes to no aggregate in any case. It is
   kept in the pre-registered set as a "should find nothing" control, approved and hash-pinned (no question was
   replaced and no paper added, so the frozen question set, manifest and stores are unchanged). The first
   benchmark selected the 19 answerable questions and its results file records `questions_excluded` with the
   reason; a 20-question run would give the same numbers.
2. **Primary metrics are Recall@10 and nDCG@10 only.** The RAGAS context metrics are deferred to the end of the
   project (Azim, 2026-10-06) and stay `null`; no model-judged score is computed (D-15). The primary
   comparison is hybrid against flat, and the two primary metrics are Holm-corrected against each other.
3. **Known limitations the report must state:** 19 questions is a small, non-random sample; gold passages and
   relevant chunks are shared across questions, so questions are not independent; the gold was drafted by
   keyword and phrase search, which may favour lexical retrieval; about 13 of 109 gold passages straddle two
   overlapping chunks (both count as relevant); the graph arm breaks score ties in document order, and across
   papers that order is a hash order, so for a hub entity its ties add question-independent noise to the
   hybrid arm (D-20, an open question for Azim: keep, or amend before the run with a version bump).

## Rules the runner enforces

- **A live run checks the freeze itself** (`eval/frozen.py`), not only pytest: the question set, the manifest,
  every selected question's approved gold and the whole retrieval protocol stamp must match their pinned
  hashes, otherwise the run is refused. It also refuses an uncommitted `api/`, `eval/`, `packages/`,
  `pyproject.toml` or `uv.lock` (`--allow-dirty` overrides, and the result records it), and records the commit.
- **The stores must be the ones the one-shot ingestion made.** Per-document ingestion facts (nodes, edges,
  extraction failures) are saved to `ingestion_report.json` beside the stores and copied into every later
  results file, so a run that merely reuses stored documents still reports them. The stored documents must be
  exactly the manifest's. `--expect-graph-sha256`, `--expect-vectors-sha256` and `--expect-chunks-sha256`
  refuse a run whose stores differ from the hashes recorded at ingestion.
- A run in which more than 5 percent of chunks failed extraction is refused.

- Corpus parity must hold before anything runs; otherwise the run is refused.
- The query embedding is computed once per question and shared by every arm.
- A signal that fails makes that question-arm **invalid**: `null` metrics, never zero, and the process exits
  with code 3.
- A question without gold has `null` metrics and is excluded from aggregates.
- The empty-graph gate: if more than 30 percent of questions resolve to no graph entities, that is an
  entity-resolution defect, not a finding about graphs. Enforced from 10 questions; below that it is reported.
- Live (paid) mode is refused unless `--allow-paid` is passed.

## Recording a live ingestion

`uv run python eval/report_ingestion.py --label <name>` reads the spend ledger and the ingestion report beside
the stores and writes a cost record: totals, the cost of every paper, per-call token and cost distributions, a
CSV of every ledger row with what it was attributed to, and the store hashes for `--expect-*-sha256`. It makes
no paid call and stops rather than guess if the ledger does not line up with the report. The 2026-10-06 record
is `refdocs/evidence/2026-10-06-live-ingestion.md`.

## Fake mode is a plumbing check

With `ARCANA_LLM_MODE=fake` and `ARCANA_EMBED_MODE=fake` the embeddings are hashed bags of words and the
extractor is a stand-in. The results file says so in a `warning` field. Those numbers must never be reported
as retrieval results. Real numbers need live providers (P0 task 10) and the hand-written benchmark gold (P1).

## RAGAS

RAGAS is not installed yet: it adds about 94 packages and the development drive is nearly full. Until it is
installed the two RAGAS metrics are `null` with a reason; nothing substitutes for them. To install:
`uv add ragas rapidfuzz`, then re-run.
