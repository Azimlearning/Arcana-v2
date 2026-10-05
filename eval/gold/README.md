# Gold annotations

> Gold is written BEFORE any benchmark arm is run (constraint 9, D-15). Once a question's gold is committed, changing it is a declared amendment, not an edit.

One file per question: `eval/gold/<question-id>.yaml`.

```yaml
question_id: q-cross-01
status: smoke | benchmark | unanswerable
note: free text (smoke files say they are not the benchmark gold)
annotated_on: 2026-10-05
reference_contexts:            # the gold passages: the evidence an answer must be built from
  - doc_id: 2408.04948v1       # the manifest's arxiv_id
    page: 1                    # 1-based, informational
    text: "verbatim passage text, whitespace collapsed"
reason: only for status unanswerable: why no passage exists
```

## Why passages, not chunk ids

Chunk ids change whenever parsing or chunking changes. Passage text does not. The runner decides which
chunks are relevant by comparing text (below), so gold survives a change of chunker.

## The relevance rule (frozen; stamped into every results file)

A chunk **covers** a gold passage if at least 30 percent of the passage's 5-word shingles also occur in
the chunk (lowercase ASCII words, the same tokenizer as the BM25 signal). A chunk is **relevant** if it
covers at least one gold passage. The rule lives in `eval/metrics.py` and is tested at its boundary.

- **Recall@10** = gold passages covered by at least one of the top ten chunks / gold passages.
- **nDCG@10**: binary gain; the ideal ranking puts min(10, R) relevant chunks first, R being the number of
  relevant chunks in the whole corpus.
- A question with no gold passages has **undefined** metrics: `null`, never 0, and it is left out of every
  aggregate.

Annotate passages the way the rule reads them: a passage of one to three sentences that, on its own,
supports part of the answer. Copy the text from the paper; do not paraphrase.

## Status values

| Status | Meaning |
|---|---|
| `smoke` | Written by the assistant to demonstrate the format and exercise the runner. Not the benchmark gold. |
| `benchmark` | Hand-annotated for the real benchmark (P1). Nothing has this status yet. |
| `unanswerable` | No passage in the corpus supports an answer. Has an empty `reference_contexts` and a `reason`. |

## Current files

| Question | Status | Passages |
|---|---|---|
| `q-cross-01` | smoke | 3 (HybridRAG twice, LightRAG once) |
| `q-single-01` | unanswerable | 0: no paper in the corpus defines Reciprocal Rank Fusion (see ADR D-21) |
| `q-single-02` | smoke | 3 (HyDE once, the RAG survey twice) |
