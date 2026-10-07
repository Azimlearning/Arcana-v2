# Execution: G1 Atomic-note graph builder, as a measured experiment

> Plan: `refdocs/plans/2026-10-07-g1-atomic-graph-experiment.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07; ADR D-34 accepted.** G1.1 is next. **G1.5 and G1.6 spend money and each needs Azim's confirmation of the amount first.**

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, read `refdocs/STATUS.md`, D-20, D-21, D-24, D-25, D-26, `eval/README.md`, `refdocs/evidence/2026-10-06-live-ingestion.md`, `api/ingestion/` and `api/stores/` in full.
- **Frozen, not to be touched:** the pinned stores in `data/eval-live-live`, `eval/questions.yaml`, the manifest, the gold, the scoring constants and `GRAPH_SCORING_VERSION`. `uv run pytest eval/tests/test_frozen_assets.py` runs in every verify, and the pinned store hashes are checked before and after any live run.
- Nothing here edits an existing store. The variant writes to its own directory and is selected by a declared argument.
- Fakes first. G1.1 to G1.4 need no key and spend nothing.
- Read the current Anthropic docs (context7) before writing the extraction call; do not encode an API from memory (CLAUDE.md rule 6).

---

### Task G1.1: The structural baseline of the current graph (free)

**Files:** `eval/graph_quality.py` (new), `eval/tests/test_graph_quality.py`, `eval/results/<stamp>-graph-quality-baseline.json`, `refdocs/evidence/<stamp>-graph-quality-baseline.md`.

1. Metrics, each a pure function of a graph store and a doc store, no model call, no network: edges whose source chunk contains both endpoint labels (whole words), edges that are bare co-mentions (relation in a stated list of generic words) or have no such chunk, the drawable share (the `GraphView` test), nodes in two or more documents, singleton nodes, degree distribution and the ten largest hubs, labels that are one or two characters or all digits, share of nodes whose label is a sentence fragment.
2. The same metrics for an arbitrary subset of documents (a filter over the store), so a subset of the new graph can be compared with the same slice of the old one.
3. Run on the pinned graph; write the JSON and an evidence record with the commit, the store hashes and the limits (a measure of structure, not of answer quality).

**Verify:** tests on hand-built graphs with known values; the run's numbers are reproduced by a second run; the pinned hashes are unchanged.

**Reality (G1.1 done 2026-10-07):** `eval/graph_quality.py` (a pure `measure()` over nodes, edges and chunk texts, plus a command that refuses a dirty tree, a missing store, unknown documents and a hash that differs from the pinned one) and `eval/tests/test_graph_quality.py` (7 tests, hand-computed on a five-node graph, slices, the empty graph, the command's guards). Run on the pinned graph at a clean commit (`da20ed1`): see `refdocs/evidence/20261007T005311Z-graph-quality-baseline.md`. **Headline:** only 34.6 percent of edges are stated in one sentence of their source chunk (co-mention 65.6 percent); 1,604 distinct relation strings (authorship is spelled four ways, about 20 percent of all edges); only 11.6 percent of nodes occur in two or more papers; the same concept is several hubs (LLM, LLMs, Large Language Models); about 3,370 of 11,173 nodes are people from title pages. **What it changes in G1.2:** a `kind` for people and affiliations is now part of the builder's design (recorded, from the corpus's general character and not from any question), and the closed relation vocabulary must cover authorship so it is one relation, not four. The hash check uses the same pinned values as the P2 study. Verified: `uv run pytest eval/tests` 123 passed; ruff and pyright clean.

### Task G1.2: The atomic builder on fakes

**Files:** `api/ingestion/atomic.py` (new), `api/stores/graph_store.py` and `api/stores/local/` (optional fields), tests, a fake extractor for the new output shape.

1. Extend `Node` and `Edge` with optional `kind`, `note` and `evidence` fields with defaults; an old store loads unchanged, a new store loads in the current code (round-trip tests, and the pinned store loads and hashes identically).
2. The extraction prompt and parser: concepts with a canonical label and the verbatim introducing sentence; relations from the closed vocabulary with the verbatim sentence naming both ends; the server verifies every sentence is a substring of the chunk (after the same normalisation the answer citations use) and drops what fails, recording each drop reason.
3. Deterministic merging (canonical form, alias table built from the text, a recorded merge list); an embedding-similarity merge exists behind a flag that is off.
4. The prompt is written from the corpus's general character and committed before any live run; it is not edited after seeing any evaluation result.
5. The builder uses the LLM seam and the ledger like the current extractor and refuses past the cap.

**Verify:** tests for every drop reason, the closed vocabulary, merge audit, an old-store round trip and a call-count and ledger check on the fake provider; the frozen-asset tripwire passes.

### Task G1.3: The arms and the declared protocol

**Files:** `eval/run_ablation.py` (additive), `eval/protocol` stamp, `refdocs/changelog/DECISIONS.md` (D-34 amended with the protocol), tests.

1. A declared `--graph-variant` argument selecting the graph store; arms `graph_atomic` and `hybrid_atomic`; the variant is part of the protocol stamp and of every result; the five existing arms give byte-identical results (a test that runs them on the fixture world before and after).
2. Write the pre-registration into D-34 (the comparison, the metrics, what counts as improved, the descriptive-only rule for the subset) **and commit it before any live run**; the runner refuses a live variant run without pinned hashes for both stores.

**Verify:** `uv run pytest eval/tests -q` passes; the runner refuses each missing declaration with a stated reason.

### Task G1.4: Review before any spend

1. `retrieval-auditor` on the builder, arms and protocol; `cost-auditor` on the paid path (the extraction call, the cap, the per-run ceiling).
2. Show Azim the exact spend for G1.5 (chunks of the chosen 4 papers times the measured cost per chunk, with a ceiling) and the choice of papers (stated by rule, not by outcome), and wait for confirmation.

**Verify:** both reports are in the changelog; no blocking finding remains; Azim has confirmed the amount in writing.

### Task G1.5: The subset run (spends about $1.5 after confirmation)

1. Ingest 4 papers with the atomic builder into a new directory, reusing the pinned vector store entries for the same chunks (a parity check that the chunk ids and texts equal the pinned ones).
2. Run `eval/graph_quality.py` on the new graph and on the same four papers' slice of the pinned graph; run the study (`eval/bound.py`) on the questions whose gold lies in those papers; run `hybrid` against `hybrid_atomic` on those questions. State how many questions that is and that retrieval numbers are descriptive.
3. Commit the results with the commit, hashes, the ledger delta and the limits.

**Verify:** the ledger delta matches the confirmed estimate within the ceiling; the pinned hashes are unchanged; results files are committed; the evidence record says what was and was not shown.

### Task G1.6: The full run (needs the cap raised by Azim; may not happen in this phase)

Same as G1.5 over all 16 papers and all 20 questions, after Azim raises `LLM_MONTHLY_CAP_USD` and confirms about $5.8. If it is not done, the record says so and why.

### Task G1.7: Wrap-up

Update STATUS, CHANGELOG, DECISIONS, the index tables and the plan's definition of done item by item, with the results stated as measured and the limits beside them. Run `/session-end`.

---

## Task order at a glance

`G1.1` free baseline of the current graph → `G1.2` atomic builder on fakes → `G1.3` arms and the declared protocol → `G1.4` reviews and Azim's spend confirmation → `G1.5` subset run → `G1.6` full run (if the cap is raised) → `G1.7` wrap-up.
