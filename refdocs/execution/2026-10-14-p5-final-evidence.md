# Execution: P5, the final evidence

> Plan: `refdocs/plans/2026-10-14-p5-final-evidence.md`. Tasks run in order unless marked as waiting. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **In progress (2026-10-14).** F1 and F2 are free and under way; F4 and F5 spend money and wait for the cap and Azim's confirmation of each amount.

## Before starting

- Read `CLAUDE.md`, preflight, D-26 (the benchmark's protocol), D-35 (the looks ledger and its amendments), `eval/README.md`, `eval/stats.py`, the cost-audit notes in `refdocs/evidence/`.
- Every paid step: `cost-auditor` first, the amount confirmed by Azim, a clean committed tree, run from the repo root, a hard ceiling.

### Task F1: the evidence index (free, now)

`refdocs/evidence/README.md` (or a section in STATUS): one table of every result file, its commit, what it supports and its stated limit; every `Noted, not changed` and open `ASSUMED:` listed with its owner. **Verify:** every file named exists; a test (or a script) checks the links.

### Task F2: the labs and the learning features as evidence (free, now)

E5 and E6: counts from the real vault and corpus: items made per claim, leak count (0 of 1,577), titles hidden, which labs the corpus supports (4 of 4 at present), the mutation rates, the review findings. **Verify:** each figure is produced by a committed script, not typed by hand.

### Task F3: the link audit (waiting on Azim)

Azim reads `eval/results/20261007T060948Z-m2-audit-sample.md` and `20261007T140924Z-m2-audit-sample.md`; the key is applied by the existing tool; precision of stated and co-mention links with the sample size is recorded. **Verify:** the result file names both samples and keeps the key apart until the labels are in.

### Task F4: the full-corpus `atomic2` build and the compare (paid, waiting on the cap and Azim's amount)

1. Protocol amendment (D-35 A9): arms, headline pairs named in advance, the ceiling, the preconditions (clean tree, repo root).
2. `cost-auditor`; Azim confirms the ceiling; the build; the compare; the evidence record.

**Verify:** chunk and vector hashes identical across arms; the frozen arms reproduce the earlier numbers; the spend is within the ceiling and in the ledger.

### Task F5: RAGAS at the end (paid, waiting)

Install RAGAS as a library; run the secondary metrics on the bounded subset; report as secondary. **Verify:** the metrics are filled in the benchmark schema; the cost is in the ledger; no model-judged number is called primary.

### Task F6: P3-lite (waiting on Azim's go)

See `2026-10-14-p3-lite-rerank.md`.

### Task F7: the limits chapter (free, last)

One document: every open limit and assumption from the ledger, grouped by what it threatens. **Verify:** every item cites its source line.
