# Plan: G1 Atomic-note graph (the v2 graph direction), built and measured

> The second part of Azim's message of 2026-10-07 (the first is `2026-10-07-p2c-traversal-view.md`). Execution doc: `refdocs/execution/2026-10-07-g1-atomic-graph-experiment.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.
> **Amended 2026-10-07 (Azim):** "the Obsidian style is not actually an experiment, this is the current direction I want to go." The atomic-note graph is the intended direction of v2's graph, not a hypothesis to be accepted or rejected. It is still **measured against the frozen baseline as additive arms with the protocol written first**, because the thesis needs evidence and the report must say what the change did; but a poor result is a reason to improve the design and measure again, not to drop the direction, and the builder becomes the default for new ingestion once the subset run shows no structural regression and Azim confirms. The file name keeps the word "experiment" only so links do not break.
>
> Status: **Approved by Azim 2026-10-07** as the direction, measured as extra arms, with "actual test results" ("proceed with both"). ADR D-34 accepted with it. **No paid call is made until Azim confirms the spend for the task that makes it** (G1.5 and G1.6 say how much).

## Why this exists

Azim, 2026-10-07: break documents down, Obsidian-style, into small nodes with relations at ingestion; "I think this can improve the graph RAG output". Azim has chosen it as the direction. This project also exists to produce evidence (constraint 9), so the new graph is **measured against the frozen baseline with its protocol written before any arm runs**: the measurement validates and sharpens the design and goes in the report; it is not a gate the direction must pass.

**What the data says about the current graph (measured, 2026-10-06 to 2026-10-07):** 16 papers, 1,570 chunks, 11,173 nodes and 13,972 edges from one free-form extraction call per chunk (relations are free text, nodes are per-chunk labels merged by normalised name). On the 20-question study only 44 percent of edges were drawable (a verbatim quote naming both endpoints), a `ConceptMap` was admitted on 3 of 20 questions (15 refused because a hop had no grounded quote), and some real relations are bare co-mentions. The first graph-versus-flat benchmark (19 questions, one ingestion) was inconclusive about whether the graph helps retrieval. So the graph's *structure* is weak in a way that is measurable, and that is where an atomic-note builder could plausibly help. Whether it helps *retrieval* is unknown.

## What's already covered (no work needed)

- The ingestion pipeline (parse, chunk, embed, one extraction call per chunk), `GraphStore` / `VectorStore` / `DocStore` abstractions (constraint 6), the stores' parity check, the spend ledger and cap, the caching embedder.
- The benchmark: 20 questions (19 approved plus the `q-single-01` control), gold annotation by passage, the five arms, Recall@10 and nDCG@10 as the only primary metrics, a paired Wilcoxon test, pinned store hashes, a refusal to run on a dirty tree (D-24).
- The admission-rate study (`eval/bound.py`) that measures which components the evidence admits.
- The raw per-chunk extraction output is not kept, but the graph store records every edge's chunk id and doc id.

## Scope

**In:**

1. **A baseline of the current graph's structure, free.** `eval/graph_quality.py` computes, with no model call, for any graph store: the share of edges whose source chunk contains both endpoint labels; the share that are bare co-mentions (generic relation words such as "related to"); the drawable share; degree distribution and hub size; how many nodes appear in two or more documents; singleton nodes. Run on the existing pinned graph first. This is a result by itself and it tells us how large the headroom is.
2. **An atomic graph builder, as a variant behind the same interface.** A second extraction mode that writes to its **own store directory** (the pinned stores are never touched): each chunk yields concept notes and typed relations under rules the server enforces, not the model:
   - concepts are named with a short canonical label, and each carries the verbatim sentence in its chunk that introduces or defines it (its "note"), or is dropped;
   - relations use a small closed vocabulary (about twelve types, with an "other" kept separate and counted), and each relation carries the verbatim sentence that states it, which must name both concepts; a relation without such evidence is dropped, not kept as a co-mention;
   - concepts are merged across chunks and documents by a deterministic canonical form (case, punctuation, plural, a short alias table built from the text itself, optional embedding similarity above a fixed threshold, off by default), and every merge is recorded so it can be audited;
   - the existing `Node` and `Edge` shapes gain optional fields (`evidence`, `kind`, `note`) with defaults, so a store written by the current builder still loads and a store written by the new one still loads in the current code.
3. **The arms, additive.** `graph_atomic` and `hybrid_atomic` (the same retrievers over the new store, the scoring constants and the graph signal unchanged). The five existing arms and their results are untouched. The runner takes the variant as a declared argument and the protocol stamp records it.
4. **A pre-registered protocol (an ADR amendment, written and committed before any live run):** the question set and gold unchanged; the comparison is `hybrid` against `hybrid_atomic` (and `graph` against `graph_atomic`) on the same questions; the primary metrics are Recall@10 and nDCG@10; structural metrics from item 1 are secondary and reported for both graphs; what counts as "improved" (a paired difference whose direction is stated in advance, reported with its interval; with the corpus sizes below it is descriptive, not a significance claim, and says so).
5. **A subset run first, then the full run if Azim raises the cap.** G1.5 ingests 4 papers with the new builder (about 400 chunks, about $1.5 at the measured $0.0037 per chunk, within the $3.83 left of the $10 cap). Its structural metrics are compared with the **same 4 papers' slice of the current graph** (free to derive: filter the pinned graph by document). Retrieval on a subset can only be scored on the questions whose gold sits in those papers; that is stated, with the number of such questions. G1.6 (all 16 papers, about $5.8) needs the cap raised by Azim; the plan does not do it.
6. Independent reviews and the usual docs, including an honest results record.

**Out (stated so they are not built by accident):**

- Editing any pinned store, question, gold annotation or scoring constant, or deleting the current graph. The pinned graph stays as the frozen baseline the benchmark rests on (history is not rewritten); the new builder is added beside it, and **becomes the default for new ingestion** once G1.5 shows no structural regression and Azim confirms.
- The user-facing **notes view** (an Obsidian-style whole-corpus graph and a page per concept note, with backlinks) and note editing by the user. **Planned next, after G1** (not conditional on the results): it is what the atomic notes are for. It needs its own plan and a wire type, so it is not built here.
- A second LLM pass for canonicalisation, a trained entity linker, or multi-hop retrieval changes (each is its own experiment).
- RAGAS (installed at the very end of the project, as decided).

## Approach

**Why server-enforced evidence.** The current graph's weakness is relations the text does not state. Making the model's output pass a verbatim-sentence check for every concept note and every relation is the same discipline the answers already use (every claim cites a stored quote) moved to ingestion. It costs recall of edges (many are dropped); the experiment measures whether the edges that survive are worth more than the edges lost.

**Why a closed relation vocabulary.** Free-text relations ("is a type of", "was used with") fragment, so the same relationship has many names and traversal cannot tell them apart. A closed list is what lets a view or a ranker treat relations differently. The "other" bucket is counted so the vocabulary can be judged on the data.

**Why deterministic merging.** An LLM-judged merge is paid, unrepeatable and hard to audit. A deterministic canonical form with a recorded merge list is free, repeatable and inspectable; an embedding merge is available behind a flag as its own later arm, not mixed in.

**Why the baseline first.** If the current graph is already mostly grounded, the headroom is small and the experiment should say so before spending anything.

## Cost estimate

| Step | Paid calls | Estimate |
|---|---|---|
| G1.1 to G1.4 (design, builder on fakes, arms, the free baseline) | none | $0 |
| G1.5 subset ingestion with the new builder (4 papers, about 400 chunks) | extraction through the LLM seam (Haiku tier), embeddings reused from the cache or re-computed (query embeddings only at run time) | about $1.5; the ledger refuses past the cap |
| G1.5 retrieval runs on the subset | query embeddings (cached) | under $0.01 |
| G1.6 full ingestion (16 papers, 1,570 chunks) | extraction | about $5.8 more; **needs the cap raised by Azim**: the month total would be about $12 against $10 |

Embeddings of chunks are the same text as before, so the vector store is reused by reference rather than recomputed (the experiment changes the graph only).

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| The experiment shows no retrieval gain | Medium: a disappointing but valid result | Pre-registered so it is reported as it falls; the structural results stand on their own and feed the traversal view |
| Evidence filtering drops most edges, leaving a sparse graph | Medium | The count of dropped relations is a recorded metric; the "other" bucket and the drop reasons are reported |
| The subset has too few answerable questions to say anything about retrieval | High for the retrieval claim | Stated in the protocol: subset retrieval numbers are descriptive; the structural comparison is the subset's real result; the full run decides |
| The Node and Edge change breaks old stores or the frozen protocol | High | Optional fields with defaults; parity and persistence tests; `eval/tests/test_frozen_assets.py` in every verify; the pinned stores' hashes are checked before and after |
| Spend overruns | Medium | Cost estimate shown to Azim and confirmed before each paid step; `cost-auditor` before G1.5; the ledger's reserve-before-send; a per-run ceiling flag |
| Prompt wording tuned on the evaluation questions | High (constraint 9) | The extraction prompt is written and committed from the corpus's general character only, before any arm runs, and frozen with the protocol; no per-question tuning |

## Definition of done

- [ ] `eval/graph_quality.py` exists with tests; the current graph's structural baseline is run and committed as a dated result with its limits.
- [ ] The atomic builder exists behind the same interface, writes only to its own store directory, and passes tests on fakes: a concept without its introducing sentence and a relation without a verbatim sentence naming both ends are dropped, the closed vocabulary is enforced, merges are recorded, and an old store still loads.
- [ ] The arms `graph_atomic` and `hybrid_atomic` exist and the five old arms' results are byte-identical (`eval/tests` green, pinned hashes unchanged).
- [ ] The protocol amendment (D-34 amended) is committed before any live run, and the runner refuses a live run without the declared variant and pinned hashes.
- [ ] A subset run is done with the spend confirmed by Azim beforehand; its structural comparison against the same slice of the current graph and its retrieval numbers (stated as descriptive) are committed with the commit, hashes and ledger delta.
- [ ] The full 16-paper run is either done after Azim raises the cap, or recorded as not done with why.
- [ ] `retrieval-auditor`, `cost-auditor` and `schema-guardian` (if a wire type changed) have reviewed it; the full suite is green; STATUS, CHANGELOG, DECISIONS and the indexes are current, with results stated as measured and the limits beside them.
