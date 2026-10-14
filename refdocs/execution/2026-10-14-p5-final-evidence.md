# Execution: P5, the final evidence

> Plan: `refdocs/plans/2026-10-14-p5-final-evidence.md`. Tasks run in order unless marked as waiting. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **In progress (2026-10-14).** F1 done (the evidence index), F6 done (P3-lite), F2 and F7 are free and open; F3 waits for Azim's reading; F4 is **done** (Look 5); F5 (RAGAS) is last and waits for the cap and a projection.

## Before starting

- Read `CLAUDE.md`, preflight, D-26 (the benchmark's protocol), D-35 (the looks ledger and its amendments), `eval/README.md`, `eval/stats.py`, the cost-audit notes in `refdocs/evidence/`.
- Every paid step: `cost-auditor` first, the amount confirmed by Azim, a clean committed tree, run from the repo root, a hard ceiling.

### Task F1: the evidence index (free, now)

`refdocs/evidence/README.md` (or a section in STATUS): one table of every result file, its commit, what it supports and its stated limit; every `Noted, not changed` and open `ASSUMED:` listed with its owner. **Verify:** every file named exists; a test (or a script) checks the links.

### Task F2: the labs and the learning features as evidence (free, now)

E5 and E6: counts from the real vault and corpus: items made per claim, leak count (0 of 1,577), titles hidden, which labs the corpus supports (4 of 4 at present), the mutation rates, the review findings. **Verify:** each figure is produced by a committed script, not typed by hand.

### Task F3: the link audit (waiting on Azim)

Azim reads `eval/results/20261007T060948Z-m2-audit-sample.md`, `20261007T140924Z-m2-audit-sample.md` and the full-corpus `atomic2` sample drawn 2026-10-15 (`20261014T185317Z-m2-audit-sample.md`, 50 asserted and 50 co-mention, seed 20261007); the key is applied by the existing tool; precision of stated and co-mention links with the sample size is recorded. **Verify:** the result file names both samples and keeps the key apart until the labels are in.

### Task F4: the full-corpus `atomic2` build and the compare (**done 2026-10-14**: `refdocs/evidence/20261014-m2-look5-full-corpus.md`; $5.12 build; see D-35 Look 5 and the A9 addendum)

1. Protocol amendment (D-35 A9): **written 2026-10-14** (arms, headline pairs named in advance, the ceiling $7.00, the preconditions, the commands).
2. `cost-auditor`: **done 2026-10-14** (expected $4.92, high $6.92; two free fixes made). Azim confirms the ceiling (**$7.00**) and edits the cap in `.env` (at least about $15.60 now, or $7.10 after 2026-11-01); then the build, the compare and the evidence record.

**Verify:** chunk and vector hashes identical across arms; the frozen arms reproduce the earlier numbers; the spend is within the ceiling and in the ledger.

### Task F5: RAGAS at the end (paid, waiting)

Install RAGAS as a library; run the secondary metrics on the bounded subset; report as secondary. **Verify:** the metrics are filled in the benchmark schema; the cost is in the ledger; no model-judged number is called primary.

### Task F6: P3-lite (done 2026-10-14: not shown to help; `refdocs/evidence/20261014-p3-rerank.md`)

See `2026-10-14-p3-lite-rerank.md`.

### Task F7: the limits chapter (**drafted 2026-10-15**: `refdocs/evidence/limits.md`; living, re-read after RAGAS and the audit)

One document: every open limit and assumption from the ledger, grouped by what it threatens. **Verify:** every item cites its source line.
