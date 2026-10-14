# Execution: extending the question set (D-39)

> Plan: `refdocs/plans/2026-10-15-question-set-extension.md`. Status: **Draft (2026-10-15)**, X1 and X2 done; X3 waits for Azim.

### Task X1: draft the questions and gold from the papers' text (done 2026-10-15)

19 questions, 59 passages; the drafting script copies each passage verbatim by start and end phrase from the page text produced by `api.ingestion.parse`. Files: `eval/questions_ext.yaml`, `eval/gold_ext/q-x-*.yaml` (status `benchmark`, `approved_by: null`).

### Task X2: mechanical verification (done 2026-10-15)

`uv run python eval/verify_gold.py --corpus-dir ../Arcana/eval/corpus --gold-dir eval/gold_ext` printed `0 problem(s)` over the 19 drafts (the 20 frozen files verified earlier, unchanged).

### Task X3: Azim's approval (waiting)

A readable review file is sent to Azim; he approves, edits or strikes each question. Edits are made by the assistant before the pin, never after.

### Task X4: register the extension (after X3; the freeze is a guard, so this is a declared change, not a quiet one)

`eval/frozen.py`: `EXT_QUESTIONS_BODY_SHA256` and `APPROVED_EXT_GOLD_SHA256` set, `check_frozen` and `eval/vault_compare.py`'s path guard accept the registered pair only; `eval/rerank_compare.py` gets `--questions-file`/`--gold-dir`; tests in `eval/tests/test_frozen_assets.py` for the extension (shape, pins, no overlap with the frozen ids, a changed file is refused). Frozen files stay byte-identical (the existing hash tests are the proof).

### Task X5: the runs (paid, under $0.01)

As in the plan's protocol, at a clean commit, hashes of the stores equal to the baseline's, then the pooled analysis script `eval/pooled_extension.py` and the evidence record.

### Task X6: docs

Evidence record, D-39 result, D-38 confirmed or reversed, STATUS, CHANGELOG, the evidence ledger.
