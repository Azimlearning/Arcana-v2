# Gold annotations

> Gold is written BEFORE any benchmark arm is run (constraint 9, D-15). Once a question's gold is committed, changing it is a declared amendment, not an edit.

One file per question: `eval/gold/<question-id>.yaml`.

```yaml
question_id: q-cross-01
status: smoke | benchmark | unanswerable
approved_by: null              # set to the approver's name once the file is approved
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
| `smoke` | Written to demonstrate the format and exercise the runner. Not the benchmark gold. No file has this status now: the two smoke files were replaced by benchmark drafts on 2026-10-06. |
| `benchmark` | Annotated for the real benchmark (P1). A **draft** until `approved_by` is set; a draft is not frozen and no live arm may be run against it. All 19 files were approved by Azim on 2026-10-06 and are pinned by SHA-256 in `eval/tests/test_frozen_assets.py`. |
| `unanswerable` | No passage in the corpus supports an answer. Has an empty `reference_contexts` and a `reason`. |

## Approval and the guard

A file is **approved** when its `approved_by` field is set. The ablation runner refuses a live (paid) run if
any selected question's gold is not approved (`require_approved_gold`, tested); a fake-mode run may use
drafts because it only checks plumbing, and its results record `gold_approved`. Once approved, a file is
frozen: changing it is a declared amendment (constraint 9): the file's hash is pinned, so an edit fails the test until the hash is
updated in the same commit as an ADR. `q-single-01` is the one unapproved file, until its amendment is decided (ADR D-21).

## How the 2026-10-06 drafts were made (method)

By the assistant, from the papers' text only, never from retrieval output (so the gold cannot be shaped by
the system it will judge):

1. Extract every paper's text per page with the pipeline's own PDF parser (`api.ingestion.parse`).
2. For each question, search that text by phrase and keyword (`BM25`, `hybrid`, `chunk size`, `multi-hop`, ...), read the hits in context, and choose passages of one to three sentences that support part of the
   answer. Copy them verbatim, keeping the PDF's hyphenation artefacts ("ben- efit"), whitespace collapsed.
3. Cover several papers for the cross-document and contradiction questions, and include passages that
   qualify a claim, not only ones that support it.
4. Check with `eval/verify_gold.py` (needs the PDFs): every passage is a verbatim span of its paper on the
   stated page, and at least one corpus chunk covers it under the relevance rule above (so every passage is
   reachable by some arm). It prints `0 problem(s)` for all 19 files.

What this does **not** establish: that the passage list is complete (a question can have supporting text
the search did not surface), or that the passages are the best ones. Azim's review (2026-10-06) is the check on both.

## Current files

R is the number of corpus chunks that are relevant under the rule (the benchmark's ideal-ranking size for
nDCG). Questions flagged **review** are ones where the corpus answers only part of the question.

| Question | Status | Passages | Papers | R | Note |
|---|---|---|---|---|---|
| `q-cross-01` | benchmark (approved) | 7 | 4 | 8 | no paper combines dense, BM25 and graph together; evidence is vector+graph, graph vs chunk, sparse+dense |
| `q-cross-02` | benchmark (approved) | 7 | 7 | 9 | |
| `q-cross-03` | benchmark (approved) | 7 | 6 | 9 | |
| `q-cross-04` | benchmark (approved) | 5 | 5 | 7 | |
| `q-cross-05` | benchmark (approved) | 6 | 4 | 5 | |
| `q-cross-06` | benchmark (approved) | 6 | 5 | 6 | |
| `q-cross-07` | benchmark (approved) | 6 | 5 | 7 | |
| `q-cross-08` | benchmark (approved) | 5 | **1** | 5 | **review:** only Self-RAG treats citation accuracy; not really a cross-document question in this corpus |
| `q-cross-09` | benchmark (approved) | 7 | 6 | 7 | |
| `q-cross-10` | benchmark (approved) | 7 | 6 | 8 | the corpus speaks of cost and speed more than production latency |
| `q-cross-11` | benchmark (approved) | 5 | 4 | 6 | |
| `q-cross-12` | benchmark (approved) | 7 | 5 | 7 | |
| `q-single-01` | unanswerable | 0 | 0 | 0 | no paper defines Reciprocal Rank Fusion (ADR D-21); amendment pending |
| `q-single-02` | benchmark (approved) | 5 | 3 | 4 | |
| `q-single-03` | benchmark (approved) | 5 | 3 | 7 | |
| `q-single-04` | benchmark (approved) | 4 | 3 | 3 | **review:** the corpus never gives BM25's scoring formula; passages cover only the word-overlap description and where it does and does not work |
| `q-contra-01` | benchmark (approved) | 5 | 3 | 6 | **review:** no paper compares chunk sizes head to head on retrieval accuracy; passages qualify the claim from different sides |
| `q-contra-02` | benchmark (approved) | 7 | 4 | 6 | |
| `q-contra-03` | benchmark (approved) | 7 | 6 | 8 | |
| `q-contra-04` | benchmark (approved) | 6 | 5 | 7 | |
