# Execution: G1 Atomic-note graph (the v2 graph direction), built and measured

> Plan: `refdocs/plans/2026-10-07-g1-atomic-graph-experiment.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07 as the direction (amended: not an experiment to be accepted or rejected); ADR D-34 accepted.** G1.1 is done; G1.2 is next. **G1.5 and G1.6 spend money and each needs Azim's confirmation of the amount first.**

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

**Reality (G1.2 done 2026-10-07):** `api/ingestion/atomic.py` (the builder), `Node.kind`, `Node.note` and `Edge.evidence` (optional, default empty; a store that never has them writes none of the keys, and the pinned graph loads and saves byte for byte, a test on the live store), `ExtractionResult.drops`, `IngestResult.build_report`, `IngestDeps.builder` (default `freeform`, so nothing changes until G1.7), `build_graph(chunks, deps)` extracted from `ingest_pdf` so the same code builds a graph over stored chunks, and a fake atomic extractor. **The rules, enforced by the server and each counted when it drops something:** a concept needs a note that is a verbatim span of the chunk and holds the concept's label as a whole word; a relation needs both ends kept, a verbatim evidence sentence naming both, and a type from the closed list of 13 (anything else is kept as `other` and counted; authorship is the one relation `authored_by`); every kind outside the list is `other`, counted. **Deterministic merging:** an abbreviation the document defines ("Large Language Models (LLMs)", accepted only if the phrase's last words spell it) folds into its phrase, and an abbreviation that is the initials of exactly one known multi-word concept joins it; an ambiguous one is left alone and counted; every merge is recorded and an edge that becomes a self-loop is dropped and counted. **Two findings from writing it:** (1) the free-form `slug("LLMs")` is `ll_ms`, so "LLM" and "LLMs" were two nodes: that is why the baseline shows them as separate hubs; the atomic builder reads a plural abbreviation as the abbreviation (`concept_id`); (2) the worst-case cost estimate is larger for the atomic request (3,072 output tokens against 2,048), a test. The prompt (version `g1-1`) was written from the corpus's general character before any live run and is frozen. Verified: `uv run pytest api` 737 passed, ruff and pyright clean.

**Reality (G1.3 done 2026-10-07):** The plan said to add arms `graph_atomic` and `hybrid_atomic` to the runner. **The build did it differently, on purpose:** the benchmark's protocol stamp pins the arm table and every scoring constant, so adding arm names would have changed a frozen asset. Instead `eval/graph_variant.py` runs the *same* arms (`graph`, `hybrid`, and the control `flat`) over two data directories that differ in the graph only. Three commands: `slice` copies the pinned stores and keeps named papers (documents, vectors and graph, through the store interfaces); `rebuild` copies a slice's documents and vectors unchanged and builds a new graph over the **stored chunks** with the atomic builder (nothing is parsed or embedded, so the vectors are bit-identical and a retrieval difference can only come from the graph; the only paid step, under the cap and a `--max-usd` ceiling that stops the build before the next paper would pass it); `compare` refuses unless both directories hold the same chunks and vectors, scores only the questions whose gold has a passage in the slice, and writes the paired numbers, the structural metrics for both graphs and the registered gate. **The protocol is the module's docstring, committed before any live run, and travels inside every result.** Registered in advance: *no structural regression* means the variant's share of edges stated in one sentence is at least the baseline's, its distinct relation strings are at most the baseline's, and its share of nodes in two or more documents is at least the baseline's; *no large retrieval drop* means the hybrid arm's mean paired nDCG@10 difference is at least -0.05; with fewer than ten answerable questions retrieval is descriptive and no significance is claimed. **Bug found by the tests:** copying `arcana.db` with a plain file copy loses what is still in its write-ahead log (the pinned directory has `-wal` and `-shm` files); the tool copies with SQLite's backup API. 13 tests (slice, rebuild, ceiling, compare, the gate's arithmetic by hand, the protocol present in the module text). Verified: `uv run pytest eval/tests` 136 passed, ruff and pyright clean. The runner `eval/run_ablation.py` and every pinned file are untouched.

### Task G1.3: The variant tool and the declared protocol (the plan's "arms" are the same arms over a variant data directory; see its Reality note)

**Files:** `eval/run_ablation.py` (additive), `eval/protocol` stamp, `refdocs/changelog/DECISIONS.md` (D-34 amended with the protocol), tests.

1. A declared `--graph-variant` argument selecting the graph store; arms `graph_atomic` and `hybrid_atomic`; the variant is part of the protocol stamp and of every result; the five existing arms give byte-identical results (a test that runs them on the fixture world before and after).
2. Write the pre-registration into D-34 (the comparison, the metrics, what counts as improved, the descriptive-only rule for the subset) **and commit it before any live run**; the runner refuses a live variant run without pinned hashes for both stores.

**Verify:** `uv run pytest eval/tests -q` passes; the runner refuses each missing declaration with a stated reason.

### Task G1.4: Review before any spend

1. `retrieval-auditor` on the builder, arms and protocol; `cost-auditor` on the paid path (the extraction call, the cap, the per-run ceiling).
2. Show Azim the exact spend for G1.5 (chunks of the chosen 4 papers times the measured cost per chunk, with a ceiling) and the choice of papers (stated by rule, not by outcome), and wait for confirmation.

**Verify:** both reports are in the changelog; no blocking finding remains; Azim has confirmed the amount in writing.

**Reality (G1.4, second part, 2026-10-07):** the retrieval audit of the builder and the protocol (before any live run) found five blocking items, now fixed with tests, and the plan was amended (D-34). (1) **The structural gate was close to tautological** (a sentence-checking builder passes "stated in one sentence" by construction, a closed vocabulary passes "distinct relations", merging inflated "shared nodes"): replaced by concept coverage, hub concentration and link concentration, with the old measures reported only; `eval/graph_quality.py` gained those measures and the label check. (2) **Resolver risk:** merging an abbreviation into its long form would have removed ids the frozen resolver matches; abbreviations now stay nodes and are linked by an `alias_of` relation from the defining sentence; the result reports resolution hit rates and empty-graph counts for both graphs and flags the graph arm INVALID if it returns nothing for more than half of the answerable questions. The `defined_in_text` and `initials_of_known` merge rules were deleted (the initials rule also depended on the order of the papers); the builder is now prompt version g1-2. (3) **The slice rule is now stated** (greedy, 450 chunks; the `choose` command applies it). (4) **The retrieval clause no longer passes on nothing:** `not_evaluable` when descriptive, and both the hybrid and the graph arm are read. (5) **The `flat` control is enforced:** a difference refuses the run. Also from the audit: notes and evidence are cut to one sentence; a label under two characters is dropped; the pilot may be examined only for declared amendments; unequal caps are declared. Verified: `uv run pytest eval/tests` 148 passed and `api` 738 passed; ruff and pyright clean.

### Task G1.5a: A one-paper pilot (about $0.25 to $0.40, after confirmation)

Rebuild the graph of one paper (the shortest in the manifest by chunk count: 2309.15217v2, Ragas, 35 chunks; the rule was stated before the run) with the ceiling `--max-usd 0.40` (expected spend $0.23, hard worst case $0.56; the ceiling is enforced on every call by `CeilingGuard`) with the atomic builder into its own directory. Record the real cost per chunk, the extraction failure rate, the drop reasons and the structural metrics for that paper against the same paper's slice of the pinned graph. Replace the plan's per-chunk estimate with the measured one and show Azim the cost of the subset before asking him to confirm it.

**Verify:** the ledger delta equals the confirmed ceiling or less; the pinned hashes are unchanged; the pilot's numbers are written to `eval/results/` with the commit.

**Reality (G1.4, first part, 2026-10-07):** the cost audit of the built tool found three blocking items, now fixed with tests: `--max-usd` was only a start-of-document gate (a single document could overshoot it), so `CeilingGuard` now refuses every call before it is sent if the money spent in the build plus the worst case of the calls in flight and of this one would pass the ceiling, the half-built document is discarded and the report is still written (`not_built_ceiling` or `not_built_cap`); the first-document projection uses the expected atomic rate ($0.0067 per chunk) instead of the free-form rate; and `compare` refuses a variant without a complete rebuild record. The plan's cost table was corrected (above).

### Task G1.5: The subset run (spends about $1.5 after confirmation)

1. Ingest 4 papers with the atomic builder into a new directory, reusing the pinned vector store entries for the same chunks (a parity check that the chunk ids and texts equal the pinned ones).
2. Run `eval/graph_quality.py` on the new graph and on the same four papers' slice of the pinned graph; run the study (`eval/bound.py`) on the questions whose gold lies in those papers; run `hybrid` against `hybrid_atomic` on those questions. State how many questions that is and that retrieval numbers are descriptive.
3. Commit the results with the commit, hashes, the ledger delta and the limits.

**Verify:** the ledger delta matches the confirmed estimate within the ceiling; the pinned hashes are unchanged; results files are committed; the evidence record says what was and was not shown.

### Task G1.6: The full run (needs the cap raised by Azim; may not happen in this phase)

Same as G1.5 over all 16 papers and all 20 questions, after Azim raises `LLM_MONTHLY_CAP_USD` and confirms about $5.8. If it is not done, the record says so and why.

### Task G1.7: Make it the default, and wrap up

After G1.5, if the subset shows no structural regression against the same four papers' slice of the pinned graph and Azim confirms, make the atomic builder the default for new ingestion (a setting, the pinned stores untouched and still readable); record the notes view as the next plan. Then:

Update STATUS, CHANGELOG, DECISIONS, the index tables and the plan's definition of done item by item, with the results stated as measured and the limits beside them. Run `/session-end`.

---

## Task order at a glance

`G1.1` free baseline of the current graph → `G1.2` atomic builder on fakes → `G1.3` arms and the declared protocol → `G1.4` reviews and Azim's spend confirmation → `G1.5` subset run → `G1.6` full run (if the cap is raised) → `G1.7` wrap-up.
