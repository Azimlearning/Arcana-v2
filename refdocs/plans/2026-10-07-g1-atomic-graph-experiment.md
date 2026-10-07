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
   - the same concept in different chunks and documents is one node when its canonical form is the same; **nothing is merged by judgement**: an abbreviation the text defines stays its own node and is linked to the long form by an `alias_of` relation whose evidence is the defining sentence (so the frozen resolver, which reads node ids, still finds "RAG" or "LLM"); every note and evidence sentence is cut to one sentence by the server;
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

**Corrected after the second cost audit (2026-10-07, on the built tool).** The $0.0037 per chunk is the free-form prompt's; the atomic prompt returns a sentence for every concept and relation. Using the real prompt size (about 650 tokens in) and a range of output sizes, the cost per chunk is about $0.0042 (700 tokens out), **$0.0067 expected (1,200)** and $0.0107 high (2,000), and the worst-case reservation per call is $0.0162. The table below therefore reads: **G1.5a pilot (Ragas, 35 chunks) about $0.23 (0.15 to 0.37), hard worst case $0.56; G1.5 subset (about 400 chunks) about $2.7 (1.7 to 4.3); G1.6 full (1,570 chunks) about $10.4 (6.5 to 16.7)**, each paying for every chunk again: the tool rebuilds all of a slice's documents and does not reuse an earlier build, so the pilot's paper is paid twice if it is in the subset and the full run pays for all 16. At the high figure the pilot plus the subset ($4.6) does not fit in the $3.83 left; at the expected figure it does ($0.9 to spare). The full run needs the cap raised in every scenario. The pilot's measured cost per chunk replaces these estimates before Azim confirms the subset.

**Cost-audit notes (2026-10-07, `cost-auditor`, read only).** The arithmetic holds: 1,570 chunks at about $0.00366 for extraction is $5.75 ($5.8056 with embeddings, so $5.8 slightly overstates a run that reuses the vectors); 400 chunks is about $1.48; $3.83 is left of the $10 cap. Three things the table above does not say, now stated: (1) **the $12 month figure assumes the full run reuses the four subset papers' graphs**; a full re-ingest of all 16 after the subset would total about $13.5; the plan reuses them. (2) **The measured $0.0037 per chunk is for the free-form extraction prompt** (about 467 tokens in, 638 out, output about 87 percent of the cost). The atomic prompt must return a verbatim sentence for every concept and relation, so output will probably be larger; if it doubles, the subset costs about $2.9 and the full run about $11.5. **A one-paper pilot (35 to 56 chunks, about $0.25 to $0.40) therefore comes first (new task G1.5a), and its measured cost per chunk replaces the estimate before Azim is asked to confirm the subset.** (3) The ledger reserves the worst case per call (about $0.011), so 400 calls would be refused part way if that were all that remained under the cap: expect a partial subset, or raise the cap. The month key is `2026-10`: the cap resets on 2026-11-01, an alternative to raising it, and Azim's call.

**The slice, chosen by the rule (2026-10-07):** three papers, 285 chunks, 19 of the 20 questions answerable (`refdocs/evidence/20261007T021458Z-g1-slice-and-baseline-v2.md`): about $1.2 to $3.0, expected **$1.9**, for the subset instead of the roughly 400 chunks the first draft assumed; the pilot (Ragas) is $0.15 to $0.37 on top.

**The pilot, run (2026-10-07):** measured **$0.00358 per chunk** (35 chunks, $0.1254), about half the auditor's expected figure; the whole pilot including diagnostics and the repeat after the fix was $0.2954 of the $0.40 confirmed. The slice of 285 chunks is therefore about **$1.0 to $1.2**, and a full 16-paper run about $5.6 to $6.0 (still above the $3.53 left; it needs the cap raised or the 2026-11-01 reset). See `refdocs/evidence/20261007-g1-pilot.md`.

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
