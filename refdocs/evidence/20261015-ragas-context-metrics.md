# RAGAS context metrics (P5 F5): installed, run, and uninformative at chunk granularity

Results: `eval/results/20261015T054853Z-ragas-original.json` (the frozen benchmark re-run on the original 19 questions) and `20261015T055033Z-ragas-extension.json` (the 19 declared extension questions), both at a clean commit with the store hashes equal to the baseline's. RAGAS 0.4.3 with rapidfuzz 3.14.6, installed as the optional `eval` extra (`uv sync --extra eval`); `langchain-community` is pinned below 0.4 because 0.4.x no longer has the module `ragas` imports (`langchain_community.chat_models.vertexai`). Spend: question embeddings only (cached; well under $0.001). The ranking numbers reproduce the earlier runs exactly (hybrid Recall@10 0.2123, nDCG@10 0.208 on the original 19).

## What was measured

The two non-LLM RAGAS context metrics the harness has carried since P0 (`NonLLMContextRecall`, `NonLLMContextPrecisionWithReference`): string similarity (Levenshtein, via rapidfuzz) between each retrieved chunk and each gold passage, with the library's default threshold of 0.5. No model call.

## Result

**Every arm scores 0.0 on both metrics, on both question sets (38 questions).** This is not a bug in the harness and it is not "retrieval found nothing": the same runs have Recall@10 up to 0.555 under the project's own relevance rule.

## Why, and what it means

A chunk is about 1,100 to 1,200 characters and a gold passage is one to three sentences (about 140 to 260 characters). A chunk that fully contains a gold passage has a normalised Levenshtein similarity to it of about 0.22 to 0.36 (measured on three covering chunks of `q-x-s03`), below the 0.5 threshold, so the metric counts it as a miss. The metric is built for contexts of similar length to the reference. It cannot discriminate arms here, and I did not lower the threshold after seeing the result (that would be tuning a metric to a number).

- The frozen relevance rule (30 percent of a passage's 5-word shingles in the chunk, `eval/metrics.py`) remains the primary, and is the one the whole study reports.
- RAGAS is therefore reported as: installed, run, secondary, **uninformative at this granularity**. No model-judged number is reported, and none is called primary (constraint 9).
- LLM-judged RAGAS metrics (faithfulness, answer relevance) were **not** run: they need generated answers and a judge model called through the project's LLM seam so the spend is booked (constraint 8); the library's own clients would bypass the ledger. The limit is recorded in `refdocs/evidence/limits.md`.
