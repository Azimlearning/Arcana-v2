# Architectural Decisions: Arcana v2

> Record decisions here so they aren't re-debated in future sessions.
> Format: **Decision** → **Why** → **Trade-offs / what was rejected**.
> Canonical one-line list lives in `refdocs/arcana-v2-PRD.md` §7; this file expands the load-bearing ones under the same id.

An ADR is worth writing when the decision (a) is expensive to reverse, (b) will look arbitrary to a future reader, or (c) had a real alternative someone will propose again. Everything else is just a commit message.

---

## D-01: Ground-up rebuild, v1 as reference (2026-10-05)

**Decision.** v2 starts from an empty repo. Arcana v1 (`Azimlearning/Arcana`, tag `v1.0`) is read
for design, lessons and evaluation assets. A file copied from v1 or Synapse starts with a provenance
header naming the source repo, path and commit.

**Why.** Azim's call: v1 was shaped around a 25-agent vision and a five-mode UI; v2's emphasis
(GraphRAG core, two pillars, governed GenUI) is different enough that continuing v1 would carry its
shape forward. v1 is frozen as the system the paper cites.

**Rejected.** Continuing in a clone of v1 (briefly created, then reset on 2026-10-05). Rejected
because it inherits v1's structure by default rather than by choice.

## D-02: GraphRAG core, two pillars, models as tools (2026-10-05)

**Decision.** Architecture is layered: the GraphRAG core; agentic AI and generative UI as the two
pillars; trained models as tools serving them.

**Why.** Azim's framing. It also matches the MCAIT paper, whose argument is that retrieval structure
bounds what the interface can honestly show; GraphRAG and GenUI are one argument, not two features.

**Trade-off.** Trained models were a graded objective in the FYP proposal (Objective 03). Calling
them tools changes the framing, not the deliverable: P3 still trains and evaluates them.

## D-03: Stack, same shape at current versions (2026-10-05)

**Decision.** Backend: FastAPI + LangGraph in Python, managed with uv. Frontend: Next.js + React +
Tailwind, managed with pnpm. Wire types defined once in `packages/schema` (TypeScript) and generated
into Python. Exact versions are set in P0 task 1 after reading current docs.

**Why.** Azim chose "same shape, current versions". It is the shape v1 and Synapse both proved, so
v1 components and Synapse modules port without a translation layer, without starting on v1's dated
pins (Next 14, React 18, LangGraph `<0.3`).

**Rejected.** Exactly v1's versions: maximal copy-paste compatibility, but dated on day one.

## D-04: Single user, no auth (2026-10-05)

**Decision.** No accounts, sessions or isolation. The app runs for one user on one machine.

**Why.** Azim: no user study, no public testing.

**Trade-off.** If v2 is ever deployed for others, auth and isolation become a new phase with its own
ADR. Config stays environment-driven so that door stays open.

## D-05: Fewer, deeper agents with super tools (2026-10-05)

**Decision.** A small roster (around eight, settled in the P1 plan) whose tools do substantial work.
Agent count is not a success measure.

**Why.** Azim: "fewer but more advanced ... deeper, more functional and more useful with super
tools", with more development time spent here.

**Rejected.** v1's "15+ agents" release bar. It encouraged agents that were prompt variants of each
other (compare/timeline/annotate reused other agents' block types).

## D-06: Automated evaluation only (2026-10-05)

**Decision.** Evidence comes from the retrieval benchmark (graph vs flat, five-arm ablation), the
extraction audit, and the verifier mutation suite. No user study, no public testing.

**Why.** Azim's decision. On 2026-10-05 he first said "no ... benchmarking", which conflicted with
his earlier agreement to the RAGAS benchmark; asked directly, he chose automated evals only.

**Trade-off.** No usability evidence (v1's SUS ≥ 70 target is dropped). The MCAIT paper promised an
interface study; the FYP report must state that it was not run, and why.

## D-07: Build order P0 to P5 (2026-10-05)

**Decision.** P0 walking skeleton + eval harness → P1 agent core with super tools (exit: first full
graph-vs-flat benchmark) → P2 GenUI catalog + adaptive dashboard → P3 trained tools → P4 VerifiedLab
+ governed lifecycle → P5 learning/writing depth + final evidence.

**Why.** Accepted by Azim. The skeleton proves the wire contract, storage seams and retrieval
toggles before anything depends on them. The eval harness sits in P0 because v1's evidence gap came
from treating evaluation as a final step. Agents precede the catalog because the catalog's bound
needs agents that actually fill payloads from evidence.

**Rejected.** GenUI straight after the skeleton: components without producing agents would be
filled by fixtures, which hides whether the bound holds.

## D-08: LLM providers, tiers and a spend cap (2026-10-05)

**Decision.** One LLM seam. Anthropic API is primary; OpenRouter is the fallback. Model tier is
chosen per task (heavy, standard, light). A per-turn token budget and a monthly spend cap are
enforced in code, and every call is written to a spend ledger.

**Why.** Azim's choice. v1's full benchmark died when a provider quota ran out (HTTP 402); a cap
that is checked before calls fail is better than one discovered after.

**Resolved (2026-10-06, D-21).** The cap starts at $5 per month (Q-01).

## D-09: Local storage behind abstractions (2026-10-05)

**Decision.** Graph: NetworkX persisted to disk behind `GraphStore`. Metadata, lifecycle and review
state: SQLite via SQLAlchemy behind `DocStore`. Vectors: a local, serverless store behind
`VectorStore` (library chosen in P0, Q-02).

**Why.** Single user (D-04); the development machine has no Docker or Postgres; v1's cloud stores
(Pinecone, Firestore) added quota and account dependencies a single-user build does not need.
Synapse v4 reached the same conclusion (its D3: SQLite locally).

**Rejected.** Pinecone + Firestore (v1): cloud dependency without a multi-user reason. Neo4j now:
needs a server; the `GraphStore` interface keeps it possible later.

## D-10: Three GenUI levels; data-only wire (2026-10-05)

**Decision.** Level 1 typed blocks, level 2 `LayoutSpec`, level 3 `VerifiedLab`. The wire carries
data only. Generated code exists only as a verifier-minted, hash-addressed artifact rendered in an
iframe with `sandbox="allow-scripts"` (never `allow-same-origin`), with libraries from a local vendor
directory and no runtime CDN fetches.

**Why.** Keeps the MCAIT paper's safety argument intact while removing its stated limitation ("the
catalogue is a ceiling"). The level 3 rules come from Synapse's hard rules 1 to 3.

**Rejected.** Letting agents emit HTML directly (the regime the paper calls unverifiable at scale).

## D-11: Governed component lifecycle (2026-10-05)

**Decision.** Every generated artifact carries a state: generated → verified → cached → audited →
promoted. A user flag evicts; a model or prompt version change marks it stale for re-verification. A
pattern promoted repeatedly may be crystallised into a level 1 component, admitted only if retrieval
can satisfy the component's structural precondition.

**Why.** Azim asked for this concept to be elevated for both Synapse v4 and Arcana v2. It answers
the paper's own future work ("the component vocabulary should grow under the same discipline").

## D-12: Trained tools are additive (2026-10-05)

**Decision.** Every trained model sits behind `Engine` (`predict()`, `is_available()`) and downstream
of a heuristic it falls back to: RRF order, an LLM routing call, or a fixed schedule.

**Why.** Carried from v1 (§12A). It keeps the primary graph-vs-flat ablation interpretable with or
without any engine attached.

## D-13: Deploy target deferred; local first (2026-10-05)

**Decision.** No host is chosen. Everything runs locally; configuration is environment-driven so a
host can be added without code changes.

**Why.** Azim: decide later. With a single user and no study (D-04, D-06), nothing currently needs
a public URL.

**Open.** Q-07. Revisit if a live demo outside this machine is needed.

## D-14: Embeddings stay `text-embedding-3-large` (2026-10-05)

**Decision.** 3,072-dimensional OpenAI embeddings, as in v1.

**Why.** Benchmark continuity with v1 and the paper's settings table. Changing the embedding model
would make v2's retrieval numbers incomparable with the published pilot.

**Trade-off.** A third API key (OpenAI) in addition to Anthropic and OpenRouter.

## D-15: Evaluation metrics (2026-10-05)

**Decision.** Primary: non-LLM context recall and precision (RAGAS `NonLLMContextRecall`,
`NonLLMContextPrecisionWithReference`) and Recall@10 / nDCG@10, all against gold passages annotated
before any arm is run. Hybrid vs flat compared by paired Wilcoxon. Secondary: RAGAS faithfulness
with a judge model different from the generator. RAGAS is used as a library inside `eval/`.

**Why.** Model-judged answer scores would confound retrieval with generation, which the paper
itself argued; gold annotation answers the reviewers' request for annotation procedures.

## D-16: Port by copying with provenance (2026-10-05)

**Decision.** Code from v1 or Synapse is copied in with a provenance header. No git submodules and no
shared package for now.

**Why.** The two projects use different storage stacks and evolve on different schedules; solo work
makes submodules costly. Revisit if the lifecycle code stabilises in both projects.

## D-17: Exact numpy vector store (2026-10-05, resolves Q-02)

**Decision.** The local `VectorStore` implementation is exact cosine search over a normalised
float32 numpy matrix, persisted as one `.npz` file (written to a temp file, then atomically
replaced). No vector-database library.

**Why.** Spike: `scripts/vector_store_spike.py`, 2,000 random 3,072-dim vectors, 20 cosine top-10
queries, recall measured against exact brute force, then close, reopen from disk and re-query.
Windows 10, Python 3.13.14, one run each, 2026-10-05.

| Candidate | Installs | Insert 2k | 20 queries (warm) | Recall@10 | On disk |
|---|---|---|---|---|---|
| numpy (exact) | yes, no extra dependency | 0.16 s | 0.035 s | 1.00 | 24.6 MB |
| faiss-cpu (flat) | yes | 0.11 s | 0.034 s | 1.00 | 24.6 MB |
| lancedb | yes | 0.27 s | 1.20 s | 1.00 | 24.6 MB |
| sqlite-vec | yes (extension loads) | 8.12 s | 1.23 s | 1.00 | 25.3 MB |
| chromadb | yes (80 packages) | 3.38 s | 0.11 s | 0.745 | 38.2 MB |
| usearch | yes | 5.29 s | 0.05 s | 0.665 | 12.6 MB |
| hnswlib | no: no Windows 3.13 wheel, needs MSVC Build Tools | n/a | n/a | n/a | n/a |

At this project's scale (one user, a corpus of low thousands of chunks, tens of thousands at most)
exact search is milliseconds, so an index buys nothing. Exactness also keeps approximate-index
error out of the graph-vs-flat comparison (D-15): a gap between arms cannot be an index artefact.

**Trade-off.** The whole matrix lives in memory (about 12 KB per chunk: 10k chunks is 123 MB, 50k
is 614 MB) and every query scans it; `save()` rewrites the file. Past roughly 50k chunks, swap an
indexed store in behind `VectorStore`. The approximate stores' recall is from random vectors, which
is a worst case for them (real embeddings cluster); that was not measured, because it does not
change the choice.

**Rejected.** faiss-cpu: equally exact and fast, but a dependency for no gain at this size, and
delete-by-id needs an ID map. lancedb and sqlite-vec: exact but 30 to 35 times slower per query.
chromadb and usearch: approximate. hnswlib: does not install here.

## D-18: Python 3.13 (2026-10-05, resolves Q-03)

**Decision.** Python 3.13 (3.13.14), pinned in `.python-version` and `requires-python = ">=3.13,<3.14"`.

**Why.** The whole P0 dependency set installs and imports on 3.13: FastAPI 0.142, LangGraph 1.2.12,
NetworkX 3.7, PyMuPDF 1.28, rank-bm25, SQLAlchemy 2.1, structlog, anthropic 1.11, numpy 2.5. The
smoke test (`api/tests/test_smoke.py`) imports each. v1's `<3.13` pin had no recorded reason, and no
incompatibility turned up in v2's set.

**Rejected.** 3.12, the `ASSUMED:` value: nothing failed that would justify the older version.

## D-19: Wire models fail closed; block lifecycle (2026-10-05)

**Decision.**
- Every generated Pydantic model is `extra='forbid'`, `strict=True`, `allow_inf_nan=False`.
- `BlockStatus` has five values: `empty`, `loading`, `partial`, `ready`, `error`. The execution doc
  named four (the render states); a finished block needs a status too.
- `BlockMeta.error` carries an `ErrorEnvelope` and is non-null if and only if status is `error`.
- A block event whose `id` was already seen replaces that block (upsert by id). There is no patch type.
- `CitedSummaryData` has no `summary` string: the answer is its ordered `segments`.
- Rules the schema cannot express are the server validator's job (task 8): every `citationIds`
  entry exists in `citations`; every `chunkId` and `docId` resolves in the DocStore; a `ready` block
  has at least one citation and every segment cites at least one.

**Why.** The first review by `schema-guardian` found, and a test reproduced, that `extra='forbid'`
alone still coerced `"1"`, `True` and `1.0` into an `int` field, so a model-produced block could
reach the client with a different type than declared. Strict mode closes that. Two sources of the
answer text (`summary` and segments) could drift, so one was dropped.

**Rejected.** A codegen `@minItems` tag for non-empty arrays: `empty`, `loading` and `error` blocks
legitimately carry empty arrays, so the rule is status-dependent and belongs in the validator.

## D-20: Graph-retrieval scoring is frozen before gold annotation (2026-10-05)

**Decision.** The graph signal's scoring rules are fixed now and stamped into every results file
(`api/retrieval/protocol.py`, `GRAPH_SCORING_VERSION = "p0-2"`):
- Entity resolution is deterministic and uses no LLM at query time: exact longest-n-gram slug match
  (also matching with separators removed, so "graphrag" finds `graph_rag`), then approximate
  token-containment matching on the words left over: at least half of a node's tokens, at most three
  nodes, each query word claimed by at most one. Exact weighs 1.0, approximate 0.6.
- A chunk scores the entity weight if it mentions the entity or a relation touching it was extracted
  from it, and half that if it only mentions a 1-hop neighbour. Scores add across entities.
- Ties break by edge support (relations touching the query entities extracted from the chunk), then
  by document order. Never by chunk id (a hash: pseudo-random) and never by the dense or sparse scores
  (that would couple the signals).
- Changing any weight, constant, stopword or tie-break needs a declared amendment and a version bump;
  results from different stamps are never pooled. Tuning, if any, uses a separate dev set, never the
  pre-registered questions.

**Why.** The first `retrieval-auditor` review found the graph arm would return an arbitrary ten of
many tied chunks and feed those ranks into RRF as if they meant something, which would make
hybrid-minus-flat partly noise and the likeliest source of a null result. It also found that the
scoring constants were free parameters that could be tuned on the test questions.

**Trade-off.** Document order favours early chunks (abstracts, introductions). That bias is explicit,
deterministic and interpretable, which an arbitrary hash order is not. Entity specificity weighting
(down-weighting entities that appear everywhere) was considered and left out: it adds a parameter, and
the freeze is cheaper to defend with fewer of them.

**Open for the harness (task 11).** A failed signal must invalidate a question run, never score as
zero recall; the query embedding is cached per question so every arm sees identical vectors; resolution
rate (overall and exact-only), per-arm ranking length and the empty-graph fraction are recorded; the
benchmark is gated on the empty-graph fraction (above about 30 percent means a resolution defect, not a
finding about graphs); `check_corpus_parity` must return no problems before a run. Extraction is not
reproducible (no seed), so the ingested graph is treated as a fixed artefact: hashed, never re-ingested
between arms.

## D-21: v1's question set and corpus reused unchanged; monthly cap $5 (2026-10-06, resolves Q-05 and Q-01)

**Decision.** The eval harness uses v1's 20 pre-registered questions (12 cross-document, 4
single-document, 4 contradiction; pre-registered 9 Jun 2026) and its 16-paper manifest, copied
byte-identical with provenance (`eval/questions.yaml`, `eval/corpus/MANIFEST.json`). A test pins their
SHA-256; changing either is a declared amendment with its own ADR (constraint 9). The monthly LLM cap
starts at `LLM_MONTHLY_CAP_USD=5`; raising it is a settings change recorded in the changelog.

**Why.** Azim's choices on 2026-10-06. Reuse keeps v2's numbers comparable with the published pilot and
keeps the pre-registration intact. $5 covers one-document smoke runs and the P0 live check; a full
16-paper ingestion with per-chunk extraction will need it raised first, and the ledger refuses a call
that would exceed it before sending.

**Finding: q-single-01 cannot be answered from the corpus.** It asks "What is Reciprocal Rank Fusion
(RRF)...", registered as a self-contained single-document control. Searching all 16 PDFs (text with
hyphenation joined): "RRF" 0 occurrences, "rank fusion" 0, "reciprocal" 2, both defining the Mean
Reciprocal Rank metric in 2401.15391 p3. No gold passage can exist. It was NOT edited. Its gold file is
`status: unanswerable`; its retrieval metrics are `None` (never 0) and it is excluded from every
aggregate. **Open for Azim before the P1 benchmark:** amend it (replace the question, or add a paper that
defines RRF) or keep it deliberately as a "should find nothing" grounding test. Either is an amendment.

**Smoke gold.** The gold for q-cross-01 and q-single-02 was written by the assistant to demonstrate the
format and exercise the runner, from passages read in the papers, and is labelled "NOT the benchmark
gold". The benchmark gold is annotated by hand in P1 before any benchmark arm is run.

## D-22: P1 agent roster and where routing lives (2026-10-06, resolves Q-04)

**Decision.**
- **Built in P1:** Orchestrator, Research, Graph and Fact Checker, plus the Composer stub from P0.
  **Deferred, still in the roster:** Lab Builder (P4), Tutor and Writer (P5). Seven agents plus the Composer
  at the end of the build, per D-05 (fewer, deeper), each earning its place with tools that do real work.
- **Routing lives in `route_to_agent`, not in graph topology.** The turn graph stays linear
  (orchestrate, then compose). `route_to_agent` charges a hop, enforces the hop and token budgets,
  refuses an unknown agent and a hop back to an agent already on the call stack, and records a trace step.
  LangGraph's `Command` and `Send` are not used in P1; revisit `Send` if parallel fan-out is needed.
- **The roster is an explicit object** carried in the turn context. v1's process-wide global registry
  is not ported: it is hidden state, and it let any code register or reach any agent.
- **Agents return payloads and verdicts; only the Composer builds blocks** (constraint 4). The Fact
  Checker does not edit the answer; it returns a verdict per segment and the Composer applies it.
- **The Fact Checker fails closed.** v1's checker failed open (on a provider outage it treated every
  citation as supported). v2 must not: if the model judge is unavailable a deterministic lexical check
  runs, and if no check can run the answer is not shipped.

**Why.** Hop budgets, loop guards and traces are the safety properties of the agent layer, so they belong
in code that is plain Python and unit-testable, not in graph wiring. A global registry contradicts the rule
that agents compose only through `route_to_agent`. Failing open contradicts "ground before generating".

**Rejected.** Dynamic routing through `Command` per agent: spreads budget and trace logic across graph
nodes. Building Tutor and Writer now: nothing in P1's definition of done needs them, and a roster of
prompt variants is what D-05 rejected. Porting v1's registry and fail-open checker: see above.

**Amendment (2026-10-06, found while building A7 and A9; the decision above is otherwise unchanged).**
- *The Fact Checker returns the checked answer, not a verdict the Composer applies.* It still builds no
  block (it returns data: the answer with failing citations and unsupported segments removed, plus a
  report). The Composer's rule is the fail-closed part: with `fact_checker` on the roster, only the
  checker's answer can be shown, and a checker that was never run, failed or was refused gives an error
  block. Why: "the Composer applies a verdict" needs the Composer to understand segments and citations;
  gating on the checker's output keeps that logic in one place and is simpler to prove (tests cover a
  raising, a refused and a never-run checker).
- *The comparison plan runs Graph too* (`graph, research, fact_checker`), and `compare_documents` pools
  the graph's evidence chunks with retrieval. Why: the P1 definition of done names a cross-document
  comparison running all four agents, and entities shared between papers are the cheapest evidence that
  two papers are about the same thing. Trade-off: one more hop (no model call) per comparison.
- *Support is judged by a light-tier model with a lexical fallback, and the fallback has a measured blind
  spot* (a negated claim passes it, 0 of 50 caught; `eval/results/mutation-factcheck.json`). The lexical
  rule is a safety net, not evidence of faithfulness. The model judge's own detection rate is unmeasured.

## D-23: Spend ledger is one file in a live mode; the cap guards everything paid (2026-10-06)

**Decision.** (1) In a live mode (LLM or embeddings) the spend ledger lives at `./data/ledger.db`, one file
whatever `--data-dir` or `ARCANA_DATA_DIR` is, unless `ARCANA_LEDGER_PATH` says otherwise; in fake mode it stays
in the data directory so tests are isolated. (2) `LLM_MONTHLY_CAP_USD` is required (positive) when EITHER mode
is live. (3) A call is priced by the model id this code requested, normalised (no provider prefix, no dated
suffix); a provider-reported cost is a lower bound (the ledger books the larger of reported and estimated).
(4) Anthropic SDK retries are off (`max_retries=0`): the fallback provider is the recovery. (5) Ingestion refuses
a document over 600 passages, and one whose worst-case extraction plus embedding cost exceeds the cap that
remains, before any paid call.

**Why.** The pre-live `cost-auditor` found each of these could let spend escape or be mis-booked: the eval run
and the API had separate ledgers (so two caps, and deleting a data directory erased the history); a dated model id
echoed by the API would have been priced as Opus and tripped the cap at about 64 percent of the real spend;
live embeddings with a fake LLM ran uncapped; an SDK retry is a second billed request under one ledger row; and
one upload could issue thousands of extraction calls and then be rolled back.

**Trade-offs / rejected.** One shared ledger means a smoke chat session spends from the same cap as the corpus
ingestion (intended; do not chat during the one-shot ingestion). No SDK retries means a transient 5xx goes to
OpenRouter at once, whose model ids are still ASSUMED. Booking the larger of reported and estimated cost can
over-count an OpenRouter call slightly. Rejected: a ledger table inside each data directory with a "global
total" query (two files to keep in step), and leaving unknown models priced as the dearest (a dated id is not
unknown).

## D-24: Benchmark protocol amendments and enforcement, before the first live run (2026-10-06)

**Decision.** (1) The first benchmark runs the 19 approved questions; `q-single-01` stays an unapproved,
unanswerable control and is excluded and reported as such (the run records `questions_selected` and
`questions_excluded`). (2) Primary metrics are Recall@10 and nDCG@10 only, Holm-corrected against each other for
the pre-registered hybrid-versus-flat test; RAGAS stays `null` until the end of the project. (3) The paid runner,
not only pytest, enforces the freeze: question set, manifest, approved gold hashes and the whole protocol stamp
hash live in `eval/frozen.py`; a live run on a changed asset or an uncommitted tree is refused, and every result
records its commit. (4) Wilcoxon differences are rounded to 12 decimals before ranking, so mathematically tied
recall differences tie. (5) Ingestion facts persist beside the stores, the stored documents must equal the
manifest's, and `--expect-*-sha256` ties a benchmark run to the stores the one-shot ingestion made.

**Why.** The pre-benchmark `retrieval-auditor` found that a result could not name its code, the freeze was only
machine-checked by pytest, ingestion facts were lost when ingestion and benchmark were separate invocations, the
19-question run was undeclared, and the p-value was wrong in about 40 percent of simulated question sets because
float noise broke ties in Recall@10 differences (fractions such as 4/7 and 6/7).

**Trade-offs / rejected.** Refusing a dirty tree means committing before every live run. Pinning the whole stamp
makes any retrieval constant change a deliberate act (version bump plus ADR), as D-20 intended. Rejected: an
ingest-only mode (ingestion plus benchmark in one invocation, or separate runs tied by hashes, both work now);
replacing `q-single-01` unilaterally (Azim's call).

**Open, not decided here.** The graph arm's tie-break across documents is a hash order (D-20 says "document
order"); it adds question-independent noise to hybrid. Changing it needs a version bump to `p0-3` and an
amendment, and is cheapest now, before any arm has run. Recorded in the README as a limitation; Azim decides.

## D-25: Extraction output limit 2,048 tokens, measured on a live paper (2026-10-06)

**Decision.** `EXTRACTION_MAX_TOKENS` is 2,048 (was 1,024). The extraction prompt, schema caps and model are
unchanged, so the protocol stamp (and its pinned hash) is unchanged.

**Why.** The first live run (one paper, Ragas, 35 chunks, Claude Haiku 4.5): 3 of 35 replies (8.6 percent) hit
the 1,024-token limit and were cut off mid-JSON, so all 3 failed extraction; at 2,048 only 1 of 35 (2.9 percent)
failed and 1 reply still reached the limit. 8.6 percent would have tripped the 5 percent extraction-quality gate
and refused the benchmark. Measured cost rose from $0.00311 to $0.00356 per chunk, which projects to about
$5.6 for the 1,570-chunk corpus (plus about $0.07 of embeddings), inside the $10 cap.

**Trade-offs / rejected.** A larger limit raises the per-call worst-case reservation (about $0.011) and the
theoretical ceiling if every reply ran to the limit (about $17); the cap and the per-document budget check
still bound real spend, and real replies average about 620 tokens. Rejected: re-asking a truncated chunk (a
second billed call per failure, and nondeterministic); leaving 1,024 and accepting a failed gate; lowering the
schema caps (changes what is extracted, and the protocol).

**Limits of the evidence.** One paper, one run. The 5 percent gate still applies to the whole corpus ingestion.

## D-26: q-single-01 is kept as a "should find nothing" control (2026-10-06, amends D-21)

**Decision.** The unanswerable question `q-single-01` stays in the pre-registered set as a negative control. Its
gold stays `unanswerable`, its retrieval metrics stay undefined (null) and out of every aggregate, and it is now
approved and hash-pinned like the other 19 files. Azim delegated the choice to the assistant on 2026-10-06
("you decided for me using best judgment").

**Why.** The corpus never defines Reciprocal Rank Fusion (D-21). The three options were to replace the question,
add a paper that defines RRF, or keep it as a control. Replacing it changes the pre-registered question set;
adding a paper changes the frozen manifest and forces a second paid ingestion that produces a different graph,
so results before and after could not be compared. Keeping it changes nothing frozen, leaves the ingested stores
and the first benchmark valid (the question already contributed null metrics, so the 19-question numbers are
what a 20-question run would give), and turns the defect into a free test of "ground before generating".

**What the control showed.** Asked of the live system on the ingested corpus (one turn, $0.0074): retrieval
returned tangential chunks (a mention of RAG-Fusion, a conformal-calibration passage), the Research agent
answered that the passages do not contain the answer, and the Composer rendered an `empty` block with no
segments and no citations. Nothing was invented. One question, one run: it shows the behaviour is possible, not
that it is reliable.

**Trade-offs / rejected.** The question set keeps one question that can never score; accepted, it is
pre-registered. Rejected: replacing the question; adding a paper.

## D-27: LayoutSpec is the single source of placement, and it is built to grow (2026-10-06)

**Decision.** Placement is level 2 data. `LayoutSpec.placements` (a list of `{blockId, panel, order}`) is the
only place that says where a block goes; `BlockMeta.panel` and `BlockMeta.order` are removed. The spec is
designed so that **a new component, panel or mode never needs a change to the layout types or the shell**:
panels are a list of `{id, width}` (not fixed keys), the spec carries a `version`, an `origin`
(`prebuilt` or `adaptive`) and a `mode`, placements name block ids and never block types, and each catalog
component declares its own placement hint (preferred panel and priority) so the layout rules are data, not a
list of component names. A client treats anything it does not recognise as "fall back to the prebuilt layout",
never as a crash. A test registers a toy component and shows it is laid out with no change to the layout module.

**Why.** Azim 2026-10-06: the layout should follow the recommendation, "also be aware that it need to be
flexible for all the new genui features". Two copies of placement would drift (the redundant `summary` string in
D-19 is the precedent), and every later phase (P3 router, P4 `VerifiedLab`, P5 study and writing components)
adds components.

**Trade-offs / rejected.** A breaking wire change now (about five sites, cheap with one block type, dearer
later). Rejected: keeping both placements and validating they agree; fixed `sources/chat/studio` width keys (a
fourth panel would change the schema).

**Amended 2026-10-07 (P2 D3 review, what the build forced).** The claim above is true of *components* only. A new
component is laid out with no edit to the layout types, the layout module or the shell (a source-scan test and a toy
component enforce it). `PanelId`, `LayoutMode` and `LayoutOrigin` are closed unions in `packages/schema/src/layout.ts`,
so a new panel or mode is a schema change plus `layout.py` (WIDTHS), `layout.ts` and the shell's `Record<PanelId, ...>`
sites. That is deliberate: an open string would let a client accept a panel it cannot draw. "Fall back to the prebuilt
layout" is built as "ignore an unreadable layout and keep the one in force" (a new turn starts from the prebuilt layout, so
the effect is the same). Azim's 2026-10-07 UI comments (a Studio output area under the graph; vertical or horizontal
splits inside the middle section) need exactly this growth: see Working assumptions 4 and 5.

## D-28: The Composer is deterministic and admits components by evidence; a prebuilt layout comes first (2026-10-06)

**Decision.** (1) In P2 no model chooses components or layout: the Composer runs each catalog component's
structural precondition over the turn's evidence, builds the ones that pass, validates each, drops (never
repairs) any that fail, and lays them out by rules that read the catalog's placement hints. It makes no model
call. (2) **The user is shown a prebuilt, basic version first**, and the adaptive version is layered on top: the
workspace opens in a fixed `prebuilt` layout (sources, chat, and a studio panel kept empty) with a source list
available before any question is asked (served by a new `GET /workspace`, validated like any block); every turn
the Composer also produces an `adaptive` layout; a header control switches between **Basic** and **Adaptive**;
the first answer applies Adaptive automatically unless the user has pinned Basic. The prebuilt layout is also the
safe fallback whenever an adaptive layout is missing or invalid. (Amended 2026-10-07: the layout mode is chosen by a deterministic rule over the turn's intent, and the Orchestrator's light-model fallback can set that intent; no model chooses components or layout directly.)

**Why.** Azim 2026-10-06: agrees a deterministic rule should decide, "but also user is presented initially with
basic version and prebuild version they can use before having the custom adaptive version". A deterministic
Composer is free, testable and is the bound (retrieval structure limits the interface). A prebuilt layout gives
a working workspace with no model and no question, and a known-good fallback.

**Trade-offs / rejected.** The adaptivity in P2 is rule-based, so it is less flexible than a model-chosen
layout; a learned chooser belongs to the P3 router and can be added behind the same `LayoutSpec` without
changing it. Rejected: an LLM layout chooser now (a paid call per turn and an unmeasured chooser). ASSUMED:
"first answer applies Adaptive automatically unless Basic is pinned" is the assistant's reading of the request;
it is one client setting and is cheap to change.

## D-29: P2 catalog scope; capability grows by tools and recipes, not by components or agents; the graph must really work (2026-10-06)

**Decision.** P2 builds five level 1 components (`CitedSummary`, `SourceList`, `GraphView`, `ConceptMap`,
`ComparisonGrid`; `InsightCard` is a stretch) and the machinery that makes adding a sixth a bounded recipe:
a catalog entry (precondition, supplier, caps, placement hint), a schema type, a validator rule set, a builder,
a web component with four states, and the tamper and admission tests; the recipe is written in
`refdocs/guides/catalog.md` and exercised by a toy component in a test. Components whose preconditions the
current evidence cannot honestly satisfy are not built now, with reasons: `ContradictionAlert` (needs an unmeasured
judge), `Timeline` (no extracted dates; a re-extraction), `GapAnalysis` (asserts absence), `ComparisonChart` and
`DataTable` (no structured extraction), the learning and writing components (their agent work is P5).
**`GraphView` must be a working graph output, which v1 never had** (v1's `KnowledgeGraphView` was a static node
list): a drawn node-link diagram from the real extracted graph, selectable nodes and edges that show their
grounded quote and source, keyboard operable, with a text list of the same relations; it must be shown working
on the real ingested corpus, not only on fakes.

**Why.** Azim 2026-10-06: not all v1 components are wanted; wants "functionality and possibility scaling as
high"; and "i do want the graph output to work in v2 which was not there in v1". Extensibility is a property of
the recipe and the contracts, not of the number of components built now.

**Amendment (later 2026-10-06, D-31).** The catalog components are the *basic accommodating components* and
stay the foundation; they are also the first templates of the UI generation pipeline (template, fences, checking,
save, reuse), whose spine P2 builds for typed UI and whose generated-code stage is P4.

**Trade-offs / rejected.** A smaller catalog than v1's 24, which the MCAIT paper already names as a ceiling.
Rejected: building all 24 (components with no agent or evidence behind them would be filled by the model, the
failure the bound exists to prevent).

## D-30: A small roster of core agents; capability grows as tools (2026-10-06, amends D-05 and D-22)

**Decision.** Boil the agents down to a few core agents that own many typed tools each. The rule for whether
something is an agent: **it is an agent only if it owns a distinct trust boundary, a distinct state or budget, or
a terminal responsibility; otherwise it is a tool group of an existing agent.** The roster is **Orchestrator,
Research, Graph, Fact Checker, Composer, and (P5) Studio**, plus **Lab Builder at P4** because generated code is
a separate trust boundary. v1's 25 agents are absorbed as follows (full table in `refdocs/guides/agents.md`):
the comparator, cross-document, literature, contradiction, discovery, methodology, debate, annotation and
document agents become **Research** tools; the visual agent's data side and the graph and timeline analyses become
**Graph** tools; the citation agent's accuracy checks and the plagiarism check join the **Fact Checker**; the UI
agent and the visual agent's layout side are the **Composer**; the memory agent becomes the Orchestrator's
context tools; the learning agent, Socratic tutor, study planner, writing agent and citation formatting become
tool groups of one **Studio** agent (P5, replacing the separate Tutor and Writer of D-22); web search and audio are
dropped (PRD non-goals). P2 adds no agent, only the Graph tool `align_documents`.

**Why.** Azim 2026-10-06: some agents can be merged, some upgraded so others are not needed, "boiling down the
AI agents the core super AI agents with all the tools needed only instead of having 24", with possibility scaling
as high as possible. Fewer agents means fewer hops, smaller prompts, simpler budgets and a clearer trace, and a
new capability costs a tool and a catalog entry, not a new agent.

**Trade-offs / rejected.** A larger tool surface per agent (mitigated by the typed tool schemas and intent-scoped
tool selection already in the framework). The Fact Checker stays separate on purpose: a checker merged into a
generator would grade its own work. ASSUMED: merging Tutor and Writer into one Studio agent is settled
properly in the P5 plan; D-22's separate Tutor and Writer are superseded as a plan, not yet built.

## D-31: GenUI has its own generation pipeline: template, fences, checking, save, reuse (2026-10-06, amends D-29)

**Decision.** Generative UI gets one pipeline with five stages, used by every UI the system produces:

1. **Template.** A reviewed, versioned recipe for a UI (the component or composition, its typed slots, the
   evidence it needs, its placement hint). Generation starts from a template, never from a blank page. The
   catalog entry is the template.
2. **Fences.** The declared limits a template, and later a generated artifact, must stay inside: size caps,
   the grounding rule (every assertion cites a stored quote), accessibility requirements, and for code (P4) the
   allowed libraries, no network, no same-origin, resource budgets. ASSUMED reading of the word "frenses" in the
   request; if something else was meant this stage is renamed, not removed.
3. **Checking.** Staged and fail closed: precondition (admission), build, schema, content validation, a
   **registration-time mutation suite** (a template cannot register unless every planted defect is rejected),
   accessibility structure; and in P4 for generated code: static analysis, contract property tests, fuzzing, a
   sandbox run and the verifier.
4. **Save.** A saved *pattern*: the template id and version, its parameters and its layout, content-addressed, with
   a lifecycle state (`generated`, `verified`, `saved` in P2; `cached`, `audited`, `promoted` and crystallisation
   in P4, per D-11), use counts and provenance. **Evidence is not saved**; it is re-bound when the pattern is used.
5. **Reuse.** Saved patterns appear beside the prebuilt layouts (D-28). Applying one re-runs its preconditions on
   the current evidence and fails closed with a reason if they no longer hold or the template version changed
   (stale until re-verified). No model call is needed to apply a pattern.

**Built in P2 versus deferred (2026-10-07 review).** Not built, and deferred to P4: provenance on a saved pattern, the
`generated` state being produced (the state exists on the wire), the accessibility fence checked at registration (a test
checks it today), and reuse selected by evidence shape (reuse is chosen by the user today).

**Staging.** P2 builds the whole pipeline for **typed (data) UI**: the five catalog components as templates, the
fences, the checks, the saved-pattern store and the reuse flow. P4 adds the **generated-code** stage (the Lab
Builder, the verifier, the delivery gate and the sandbox) to the same pipeline. Hard constraint 3 is unchanged: no
generated code reaches the client except as a verifier-minted type, and P2 contains no code generation. The basic
accommodating components of D-29 remain the foundation: the pipeline makes them templates, it does not replace them.

**Why.** Azim 2026-10-06: GenUI needs "its own ui generation pipeline which goes through templates, [fences],
checking, just like synapse but more advanced, then the ui component will be saved and can be used in future, but
also it needs to have all the basic accommodating ui components like before". Building the spine now means P4's
generated code plugs into a pipeline that already has saving, reuse, staleness and tests, and the saved patterns
immediately serve as the "prebuilt versions" of D-28.

**Intended advances over Synapse** (from `refdocs/arcana-v2-sources.md`'s description of its contract,
mutation tests, fuzz checks and promotion ladder; I have not read Synapse's code, which is not on this machine, so
these are design intentions, not measured claims): templates as the starting point; a contract bound to retrieved
evidence; mutation testing applied at template registration, not only to artifacts; versioned staleness; reuse
selected by evidence shape; crystallisation into typed components (P4).

**Expected to change.** Azim (2026-10-06): the pipeline as planned is fine for now, and he may change it or
experiment with it after testing. So the stage interfaces are kept small and replaceable (a template record, a fence
set, an ordered list of checks, a pattern store with a state field), and no later phase may assume the stages are
fixed. "Generative UI" in this project is the MCAIT paper's full idea: typed composition now (P2), verified
generated interfaces later (P4), with Synapse as the reference for the second.

**Trade-offs / rejected.** P2 grows (four more tasks); the cut line is that the reuse and re-verification tasks may
slip to the start of P4 if P2 runs long, with the template, fence and store tasks kept. Rejected: pulling generated
code into P2 (it is the safety-critical path and needs the verifier, so it stays P4); saving evidence with a pattern
(it goes stale and could outlive the documents it came from); a free-form saved-JSON pattern (parameters are typed
strings validated against the template's slots).

---

## D-32: Layout v2 adds regions inside panels, and the Studio is a shell before it has generators (2026-10-07)

**Status.** Accepted 2026-10-07 (Azim approved the P2b plan). Built 2026-10-07 (P2b F1 to F5).

**Built, with what the build changed.** The Composer gives the studio panel a graph area above its shelf (60 and 40 in Adaptive; the fixed Basic layout is 25 and 75 because Basic shows graphs in chat and its graph area only says so, seen in the browser), keeps the studio at a 20 percent column in Adaptive even with no graph so the shelf and the saved views stay reachable (answer-only layouts are 0, 80, 20), and decides a split's direction by the highest-priority hint that names one. A region size may be 0 (the plan said 1) so an unused region can exist without space. The chat panel must have a `main` region (both validators). A version 1 layout is read as one `main` region per panel. The Studio generators are inert list items.

**Decision.** (1) `LayoutSpec` version 2 lets a panel be divided into regions (`main`, `secondary`, `shelf`) with a direction (`rows` or `columns`) and sizes in percent; a placement names a panel and a region; a v1 spec is read as one `main` region per panel. The region ids are a closed union and the split is one level deep. (2) The studio panel's basic layout is the graph area above a Studio area, which holds inert generator tiles and an Outputs shelf; the shelf's first items are the saved views. (3) The generators and the Studio agent stay in P5 (D-30).

**Why.** Azim 2026-10-07: v1's Studio sits under the graph on the right with its outputs below it (NotebookLM was the inspiration), and the middle section should split vertically or horizontally by the kind of component generated (a quiz, a study session). D-27 made panels closed, so this is a deliberate, breaking wire change; doing it while five components and one layout exist is cheaper than after P5.

**Trade-offs / rejected.** A second breaking change to `LayoutSpec`. Rejected: an open tree of nested splits (the server could describe a layout the client cannot draw, and the validator would be recursive); building the generators now (they are P5 and need the Studio agent); hiding the generator tiles until they work (the screen should say what is not built).

## D-33: A TraversalView shows what the search followed, as its own component (2026-10-07)

**Decision.** A new catalog component, `TraversalView`, shows for a prompt which concepts the question resolved to (the seeds), the one-hop edges the graph signal followed, and the passages reached, in rank order, with how each was reached. Its precondition: the graph signal resolved at least one query entity and followed at least one edge to a stored chunk. It is grounded by **provenance**: every seed, edge and passage is checked against the stores (not "the text states the relation"), and the view says it shows what the search followed. It is computed by a read-only function (`trace_graph_signal`) that shares the retriever's helpers and constants; **the retriever is not edited**, and a parity test over the frozen question set keeps the two in step. Placed in the studio's graph area under `GraphView`.

**Why.** Azim 2026-10-07: show "the node traversal based on each prompts" in the top-right graph. `GraphView` guarantees every edge's quote names both concepts, which hides the edges the search actually followed; mixing the two would weaken that guarantee. A separate component keeps each claim honest and makes the graph's real behaviour inspectable, which is also the evidence for D-34.

**Trade-offs / rejected.** A second walk over the graph can drift from the retriever (mitigated by the parity test, not by editing frozen code). One hop only: that is what the retriever does. Rejected: extra fields on `GraphView` (weakens its guarantee); recording the path inside the retriever (touches frozen D-20 code and changes `RetrieverResult`); an LLM-written explanation (no model call, and it would be unverifiable).

**Amended 2026-10-07 (the build, P2c T2 to T5).** (1) **Grounding is re-derivation:** the validator re-runs the traversal from the block's own seeds over the stores and requires exactly the block's passages, steps and left-out count (it takes the graph store as a new argument and refuses a TraversalView without one). What it cannot check, because the question is not in the block, is which concepts are the seeds and each seed's match kind: those are taken as given from the Composer. (2) At most 10 seeds, 40 nodes, 60 steps, 10 passages; a question resolving to more than 10 concepts is refused with the closed reason `too_many_seeds` (with `nothing_resolved` and `no_edge_followed`). (3) The template is reusable: a saved view stores the seed labels and re-runs the traversal. (4) "Reached" is the graph signal's own top ten, not the fused top ten the answer is built from.

## D-34: The atomic-note graph is v2's graph direction, built beside the frozen baseline and measured with the protocol fixed first (2026-10-07)

**Decision.** (1) The Obsidian-style ingestion idea (small concept notes with typed, evidenced relations, merged across documents) is built as a **variant behind the same interface** that writes to its own store directory. (2) It is evaluated as the additional arms `graph_atomic` and `hybrid_atomic` against `graph` and `hybrid` on the frozen question set; no existing store, question, gold annotation, scoring constant or result is changed. (3) A free structural baseline of the current graph is measured first. (4) The protocol (the comparison, Recall@10 and nDCG@10 as primary, structural metrics as secondary, what counts as improved, descriptive-only reporting where the number of answerable questions is small) is written into this ADR and committed **before any live run**. (5) Paid steps run in two stages: a 4-paper subset (about $1.5, within the cap), then the full 16 papers (about $5.8) only after Azim raises the monthly cap; each paid step needs Azim's confirmation of the amount. (6) `Node` and `Edge` gain optional fields with defaults; old stores still load.

**Why.** Azim 2026-10-07: break documents into small nodes with relations at ingestion; "I think this can improve the graph RAG output"; and "part 2 will actually have experimentation or actual test results". The current graph is measurably weak in structure (44 percent of edges drawable, a path map admitted on 3 of 20 questions), so the hypothesis is plausible; whether it helps retrieval is unknown, and constraint 9 requires the protocol to be fixed before the arms run.

**Trade-offs / rejected.** Evidence filtering costs edges (many are dropped); the experiment measures whether the survivors are worth more. A subset run can only describe retrieval on the few questions whose gold sits in its papers. Rejected: replacing the builder (cannot be compared, rewrites history); an LLM-judged merge (paid, unrepeatable); tuning the prompt on the evaluation questions (constraint 9).

**Amended 2026-10-07 (Azim).** "The Obsidian style is not actually an experiment, this is the current direction I want to go." The decision stands as written for how it is built and measured, with this change of status: the atomic-note graph is the **intended direction**, not a hypothesis to accept or reject. (a) It is still compared with the frozen baseline as additive arms and the protocol is still fixed before any live run (constraint 9; the report needs the evidence); (b) an unfavourable result is reported and is a reason to improve the design and measure again, not to abandon the direction; (c) the builder becomes the **default for new ingestion** once the subset run shows no structural regression against the same slice of the pinned graph and Azim confirms, with the pinned stores left untouched and readable; (d) the user-facing notes view (an Obsidian-style whole-corpus graph and a page per concept note, with backlinks) is planned **next after G1** and is not conditional on the results. Azim, later the same day: make the atomic notes "a test to validate first but commit fully to this": the subset run (G1.5) is the validation step that comes first, and the commitment to the direction does not depend on it. The wording "experiment" in the plan's file name is kept so links do not break.

**Protocol registered 2026-10-07 (G1.3) and amended the same day after the retrieval audit, still before any live run (builder prompt g1-2).** The full text is the module text of `eval/graph_variant.py`, copied into every result; the points that changed or were added:

- *Merging.* Abbreviations are **not merged by judgement**. The first design folded a defined abbreviation into its long form and joined an abbreviation to a known concept by initials; the audit showed the frozen resolver reads node ids only (so "RAG" would no longer resolve), that the initials rule raised the shared-node count without textual support, and that the result depended on the order of the papers. Now an abbreviation the text defines stays its own node and is linked to the long form by an `alias_of` relation whose evidence is the defining sentence, built per chunk. Notes and evidence are cut to **one sentence** by the server, and a label shorter than two characters is dropped.
- *Slice rule* (stated before any choice): greedy by newly answerable frozen questions per chunk, ties to the lower arxiv id, 450-chunk budget; build order arxiv id ascending. The `choose` command applies it.
- *Pilot rule:* one paper, the shortest in the manifest (Ragas, 2309.15217v2); its outputs may be examined only to find a defect, any resulting change is a declared amendment with a new prompt version, and the whole measured slice is then rebuilt with that version.
- *Gate.* Replaced, because a builder that checks sentences passes "edges stated in one sentence" by construction, a closed vocabulary passes "distinct relations", and merging inflates "nodes in several documents". *No structural regression* is now: concept coverage of the slice's chunks at least 0.8 times the baseline's, and the share of edge ends owned by the ten largest nodes and the share of node-to-chunk links owned by the largest one percent of nodes both not above the baseline's, each by the same code on both graphs. The old measures, edges per node, nodes with no edge and the label check are reported, not gating. *No large retrieval drop* applies to both the `hybrid` and the `graph` arm, reads `not_evaluable` when fewer than ten questions are answerable, and never passes on nothing.
- *Amended after the pilot (still before any measured run; builder g1-3).* The copy check is blind to PDF line-break hyphenation and stores the chunk's own words; the share of edge ends owned by the ten largest nodes leaves the gate (it rises in any graph with fewer edges) and is reported.
- *Validity and control.* The graph arm is flagged INVALID if it returns nothing for more than half of the answerable questions; resolution hit rates and empty-ranking counts are reported for both graphs. A `flat` control that differs between the directories refuses the run.
- *Audit.* 50 edges per graph, fixed seed, mixed and blind (`audit` command), read by a person; reported beside the gate, never folded into it.
- *Declared differences:* the atomic extractor allows 25 concepts and 40 relations per chunk and 3,072 output tokens; the baseline 30 entities, 40 relations and 2,048. One build is one sample (no temperature is set).

**Subset run, 2026-10-07 (builder g1-3).** Reported in `refdocs/evidence/20261007T051315Z-g1-subset.md`. The registered gate did **not** pass: concept coverage held (98.3 against 99.0 percent) but the share of node-to-chunk links owned by the largest one percent of nodes was 14.75 percent against 14.19 (a margin of 0.0056); retrieval held (hybrid +0.0096 and graph +0.0048 mean paired nDCG@10 over 19 questions, 6 better and 7 worse for hybrid; the flat control identical; descriptive only). By the amended D-34 a failed gate is a reason to improve the design and measure again, not to drop the direction, and the gate is not reinterpreted. What the run shows is a graph one third the size with a tenth of the edges that retrieves about as well, whose edges are mostly sensible where the baseline's are often noise, but that is thin: 73 percent of its nodes have no edge and only 39 percent of passages carry a relation, because about three quarters of the proposed relations are lost (221 of about 916 survive).

## D-35: Mark 2 is a compiled vault over the graph: links, concept pages, claims, a notes view, a learner layer and lint; retrieval over it is a new arm with its protocol fixed first (2026-10-07)

**Decision.** (1) The graph direction continues as a **vault** of four layers: passages; mentions and links (asserted by a model and checked, or **co-mentioned** in one sentence and found by the server); **concept pages** that sit above nodes as lists of node ids (nodes are never merged by judgement, so the frozen resolver still reads node ids); and **claim notes** (sentences that state a finding, linked to the concepts they name, kept in the vault and not in the graph). (2) Retrieval over the vault is a **new additive arm** (`vault`, `hybrid_vault`, and a semantic-resolution variant) with its own version stamp (`VAULT_SCORING_VERSION = "vault-1"`); the frozen graph retriever, `GRAPH_SCORING_VERSION`, the question set, the gold and every pinned store are untouched (D-20, D-34). (3) A second builder `atomic2` (prompt `g2-1`): the prompt numbers the sentences and the model names concepts, typed relations and claim sentence numbers; **the server chooses and checks the sentence** (a relation may use a window of two adjacent sentences). (4) The vault sits behind a `VaultStore` abstraction (constraint 6). (5) The user-facing notes view, a learner layer and a lint pass are built on the vault, each with schema first and server-side validation that re-derives the block from the vault. (6) The protocol below is fixed and committed **before any vault run**. (7) Paid steps need Azim's confirmation of the amount first; the monthly cap is his to raise.

**Why.** Azim 2026-10-07: "im okay with doing a to g ... if u think a to g is the best way to make the best v2, pls proceed". Mark 1 measured about equal retrieval from a graph a third the size with cleaner edges, but 73 percent of its nodes had no edge and about three quarters of proposed relations were lost. Three free probes (`refdocs/evidence/20261007-m2-brainstorm-probes.md`) show the loss is mostly the one-sentence evidence rule, not bad concepts, and that a deterministic co-mention layer removes about a third of the isolation for free.

**Trade-offs / rejected.** Co-mention links are weaker evidence than asserted ones (they carry a quarter of the weight and are counted separately). Rejected: merging nodes by judgement (kept as a layer); editing the frozen retriever to read pages (not comparable, rewrites history); tuning weights on the 19 questions; a model judge of contradictions in P1 of Mark 2 (needs a model, deferred and flagged).

### Protocol registered 2026-10-07, before any vault run (`vault-1`, builder `g2-1`)

**Corpus and questions.** The Mark 1 slice (3 papers, 285 passages) and the frozen 20 questions, 19 answerable; gold unchanged. Baseline directory = the pinned graph restricted to the slice (`data/g1/slice-base`); reference directory = the same documents with the g1-3 graph (`data/g1/slice-atomic`); a third directory is the same documents with an `atomic2` graph (built by the paid rebuild). The three share byte-identical chunks and vectors (checked by hash); `flat` must be identical across them or the run is refused.

**Vault construction (deterministic, no model).**
- *Pages:* nodes are grouped by union-find over `alias_of` edges and over equal compact ids (`graph_rag` and `graphrag`). A page keeps the list of node ids, a display label (the longest member label that is not an all-capitals abbreviation, else the most mentioned; ties to the smaller id), the other labels as aliases, and the members' notes as defining sentences.
- *Mentions:* a passage mentions a page if any member's chunk list holds it, or if any member's label (at least 3 characters) occurs in it as a whole word, blind to hyphenation (the Obsidian "unlinked mentions", found corpus-wide by the server).
- *Asserted links:* node edges lifted to pages (self-loops dropped), each with its relation, evidence sentence and chunk.
- *Co-mention links:* two pages whose labels occur in the same sentence of a passage, counted as the number of distinct passages. Sentences naming more than **6** distinct pages make no links (lists, author lines); pages whose members are of kind `person` or `organisation` make none.
- *Spread:* `idf(p) = ln(1 + N / df(p)) / ln(1 + N)`, N = passages in the corpus, df = passages that mention the page.
- *Claims (only from `atomic2`):* a sentence the model marked claim-worthy and that holds the label of at least one kept concept; at most 6 per passage.

**Retrieval, `vault-1`.** Query to pages as the frozen resolver does (longest exact n-gram up to 4 over every member label and alias, then approximate by half-token containment, at most 3), weights 1.0 exact and 0.6 approximate. For each resolved page with weight `w`: passages that mention the page, or hold an asserted-link evidence sentence touching it, score `w * idf(page)`; passages that mention an **asserted** neighbour page (and are not already scored for this page) score `0.5 * w * idf(neighbour)`; passages that mention a **co-mention** neighbour (and are in neither set) score `0.25 * w * idf(neighbour)`. Scores add across pages. Ties are broken by asserted-link support, then document id, then position (as in the frozen retriever); scores are rounded to 12 places before comparing. Top 10 per signal; `hybrid_vault` swaps the graph signal in RRF (k = 60) and changes nothing else.
- *Semantic resolution (`vault_sem`, `hybrid_vault_sem`):* when lexical resolution recognised fewer than half of the question's content words, add the **2** pages whose label embedding is nearest (cosine) to the question embedding, weight 0.5, **no similarity threshold** (rank-based, so there is no number to tune on the questions). Page labels are embedded once with the same model as the chunks.
- *Ablations on one build (free):* co-mentions off; spread discount off (idf = 1); claims off.

**Arms** over each directory: frozen `graph`, `hybrid`, control `flat`; and over the two atomic directories `vault`, `hybrid_vault`, `vault_sem`, `hybrid_vault_sem`. The frozen arms are run by the existing code with the existing constants.

**Primary metrics.** Recall@10 and nDCG@10 per question and arm, paired differences, mean, and counts improved, tied and worsened. With 19 answerable questions retrieval is **descriptive**: no significance test is run or claimed. Model-judged scores are never primary.

**Mark 2 gate (replaces, for the vault, Mark 1's top-1% clause; the Mark 1 gate's text and result are history and are not reinterpreted).** A vault passes `no structural regression` if ALL hold: (1) the share of the slice's passages that at least one page mentions is at least 0.8 times the baseline graph's; (2) the share of pages with at least one link of either kind is at least **0.5** (a declared target set after the free probe, which showed 59 percent of g1-3 nodes linked: disclosed, not blind); (3) the mean fraction of the questions' content words that the vault's resolver recognised is at least the frozen baseline resolver's on the same questions; (4) no large retrieval drop: mean paired nDCG@10 of `hybrid_vault` against the baseline directory's frozen `hybrid` is at least -0.05, and of `vault` against the baseline directory's frozen `graph` is at least -0.05. **Reported, not gating:** the Mark 1 top-1% share of node-to-passage links (merging aliases into pages concentrates mentions by design; the spread discount is the mechanism and clause 4 measures its effect), edges and links per page, pages with no link, co-mention versus asserted shares, drops by reason (builder). Also reported: paired differences of each vault arm against the same directory's frozen arm (the improvement question) and against the baseline directory's.

**Validity.** A vault arm is INVALID if it returns no passage for more than half of the answerable questions. The `flat` control must be identical across directories.

**Audit.** A blind sample of 50 asserted and 50 co-mention links per vault (fixed seed), read by a person, reported beside the gate and never folded into it.

**Looks ledger (forking-paths control).** Look 1: the g1-3 graph on the slice (Mark 1, reported). Look 2: `vault-1` over the same g1-3 graph (free, planned first). Look 3: `vault-1` over an `atomic2` graph of the same slice. Any change to a `vault-1` constant after seeing a result is a new version (`vault-2`), is declared here before the next run, and is counted as the next look. The report states how many looks the same 19 questions have had.

**Declared differences.** `atomic2` allows 25 concepts, 40 relations and 6 claims per passage, 3,072 output tokens (as g1-3); relation evidence may span two adjacent sentences; concept notes are the first sentence holding the label (preferring one with a definitional cue: " is ", " are ", "refers to", "denotes", "called", "known as", "we propose", "we introduce"). Both builders use the light tier. One build is one sample (no temperature).

**Amendment A1, 2026-10-07, after compiling the vault over the Mark 1 slice and reading 28 sampled co-mention links, still before any vault retrieval run.** 262 of the first build's 1,633 co-mention links (16 percent) had, as their stored example, a sentence that read like a reference-list entry (with the rule 211 links, 12.9 percent, disappear; the other 51 also co-occur in a non-reference sentence of another passage and stay, with that sentence as their example) ("Yu, ... arXiv preprint arXiv:2305.19912, 2023."), which name the concepts of a cited title and state no relation. Rule added to the construction: a sentence holding a strong bibliography marker (arXiv, preprint, proceedings, doi, pp., journal of, conference on, association for computational; case-insensitive; "et al" is not a marker because prose cites "Lewis et al." too) makes no co-mention links. The structure of the build (pages, mentions, asserted links) and every retrieval constant are unchanged; only that one rule moved, and it is part of `vault-1` because no retrieval run has used the earlier text. The first build's counts were seen before this amendment; they are disclosed here, not hidden.

**Amendment A2, 2026-10-07, while building the retriever, before any retrieval run (clarifications, plus one constant that D-35 had not stated).** (a) The D-35 text left open how a passage that mentions several neighbour pages is scored: it takes the **best** neighbour's value once (the largest `spread(neighbour)` among those that mention it), and asserted neighbours are applied before co-mention neighbours, so a co-mention never lowers or adds to a passage an asserted neighbour already reached. (b) The D-35 text named "claims" only as an ablation without saying how a claim is used: a passage that holds a claim naming a resolved page adds `0.25 * w * spread(page)` once per such page, only when the vault has claims and the claims toggle is on. (b) introduces `CLAIM_WEIGHT = 0.25`, a constant D-35 did not state; it is chosen to match the co-mention weight, a priori, and the Look-2 vault has no claims, so it cannot affect that look. The arithmetic is pinned by hand in `api/retrieval/test_vault.py` and the protocol text in `eval/vault_compare.py`.

**Amendment A3, 2026-10-07, after the `retrieval-auditor` review of the built tool and still before any retrieval run.** One rule is made to follow the D-35 text and the rest is disclosure.
- *The 6-page cap counts every page a sentence names, people and organisations included* (D-35 said "more than 6 distinct pages"; the first build counted only the eligible ones, so an author line naming five concepts and four people kept its links). The links themselves are still made only among pages that are not of kind person or organisation. The vault was rebuilt before any retrieval run: 1,406 co-mention links (from 1,422) and 65.5 percent of pages linked (from 65.7).
- *The mention scan covers labels with no ASCII letter or digit* ("αβγ" was pruned out by the token index although the matcher accepts it); none of the 725 labels in the Look-2 build is affected.
- *Claims are sorted before they are numbered*, so the vault hash does not depend on the order a builder returned them.
- *Disclosure, not a protocol change: what is known about the gate before Look 2.* Clause 1 and clause 2 are expected passes and were seen before registration (100 percent of passages mentioned and 65.5 to 65.7 percent of pages linked in the build; g1-3 itself covers 98.3 percent against the baseline's 99.0), and clause 1 is not like for like with Mark 1's (the vault counts passages a page's label is found in anywhere in the corpus; the baseline counts only passages in a node's own chunk list). **Clause 3 reads the same node ids the g1-3 resolver reads, so it cannot recognise more of a question's words than g1-3 does (0.389 against the baseline's 0.546 in Mark 1) and is expected to fail at Look 2 by construction.** Only clause 4 and the paired differences carry information at Look 2; a "gate failed" line at Look 2 must not be read as evidence about the vault.
- *Headline comparisons, named before the run:* `hybrid_vault` against the same directory's `hybrid`, and `vault` against the same directory's `graph`. The semantic arms and the three ablations are exploratory. The P1 full-corpus benchmark read the same 19 questions over the pinned graph, so the looks ledger begins before Mark 1.
- *Tool hardening (no constant changed):* a vault arm whose retriever raised is counted as a failed cell and invalidates the arm instead of being dropped; a missing measure never passes a clause; the semantic arms are registered, so a run without them is refused unless `--without-semantic` is given and then says so at the top; label vectors carry their mode, model, dimension and a hash of the labels and are refused if any differs; the vault file must belong to its directory (passage count, node ids, build record); a live run checks the frozen assets and approved gold as the runner does and a result must use the frozen question and gold paths; the audit leaves out links without a sentence (which would reveal the kind) and writes its key to a separate folder.

**Amendment A4, 2026-10-07 (M2.6, after the `schema-guardian` review; a recorded deviation, not a change of protocol).** The notes view adds two blocks, `ConceptPage` and `NotesGraph`, with **their own registry** (`api/genui/notes_catalog.py`, `NOTES_CATALOG`) and not entries in `CATALOG`: `CATALOG` drives per-turn admission and the trace through `check(ComposerEvidence)`, and these components are not offered to a question. They are built by the Composer (`compose_notes`), placed by the layout (`compose_notes_layout`, which keeps only the regions something is placed in), served by `GET /vault/notes` in the `/workspace` response shape and validated by **re-deriving** them from the vault. **Constraint 7 is met in a changed form:** the written structural precondition is satisfied by the vault, not by retrieval (a page exists and a passage mentions it; a graph has a page to show), and the guide says so. Everything else of the pattern holds: schema first, strict models, fail closed (a block with no vault to check against is refused), all five states, caps in one place and parsed against the guide, accessibility labels checked statically against the component source.

**Amendment A5, 2026-10-07, before the run: Look 3 is a scale check (Azim: "maybe graphrag is better generally when the knowledge base or inputted document is a huge quantity").** The Mark 1 slice has 285 passages; the pinned free-form graph covers all 16 papers (1,570 passages, 11,173 nodes). **Look 3** compiles the vault with the **same `vault-1` rules and constants** over that pinned graph (a copy; the pinned directory is only read) and runs the same arms on the same 19 answerable questions, with the pinned directory as the baseline and the copy (same graph, same vectors, plus its vault) as the variant. Declared before the run: (1) nothing changes in `vault-1`; (2) the free-form graph has no kinds and the builder's free relation strings, so people and organisations are **not** excluded from co-mentions (the 6-page sentence cap still applies) and the asserted links carry no evidence sentences, so the page shows no stated links and the asserted-link evidence path is inert: this look measures mentions, co-mentions and the spread discount, not stated relations; (3) the Mark 2 gate's clause 3 compares the vault's resolver with the same graph's own resolver and so is equal by construction (it passes trivially: reported, carrying no information); clauses 1, 2 and 4 are read as before; (4) the headline pairs are the same (`hybrid_vault` against `hybrid` and `vault` against `graph`, over the same directory), and the question asked is whether the gain of the vault arm over the frozen graph arm, and the gap between the hybrid and the `flat` control, change with the size of the corpus from 285 to 1,570 passages; (5) the two looks are on different corpora, so their numbers are compared descriptively and not paired; (6) the page labels are embedded for the semantic arms (about 11,000 labels, under a cent) and the sem arms stay exploratory. Looks ledger: Look 3 = this; the `atomic2` graph over the slice is Look 4.

**Amendment A6, 2026-10-07 (M2.7, before the code): the learner layer.** Per-concept mastery from the learner's own events, shown on a page and as the colour of the graph's pages. **Events** (stored locally in `learner.db` beside the other stores, behind a `LearnerStore` abstraction; events only, no document text, no identity; deletable by `DELETE /learner`): a page id, a `signal` and a time. Signals now: `know`, `unsure`, `dont_know` (self-ratings from the page's buttons). Quiz results are the same events with `quiz_correct` and `quiz_wrong` once the Studio generators exist (P5); the store accepts any of the five, the route accepts the first three until then. **The update rule (deterministic, no model):** an event adds to a pair (`a`, `b`): `know` (1, 0), `unsure` (0.5, 0.5), `dont_know` (0, 1), `quiz_correct` (1, 0), `quiz_wrong` (0, 1), each multiplied by a decay of `0.5 ^ (whole days since the event / 14)`; with `A` and `B` the sums, **score = (A + 1) / (A + B + 2)**, rounded to 4 places, in [0, 1], and a page with no events has no mastery (null, not 0.5). `events` is the count of the page's events kept (the latest 200). The score is a belief that decays towards ignorance, not a grade; the screen words it as "comfortable" from 0.67, "getting there" from 0.4 and "needs work" below, and never as a mark. **The Composer takes one snapshot of mastery per request** and builds and validates the blocks from it (a score depends on the clock, so a block is checked against the snapshot it was built from, not against a later reading); a block that claims a mastery the snapshot does not hold, or a mastery when no snapshot is given, is refused. Rejected: a model-judged mastery (paid, unrepeatable), a per-document score, and storing the learner's data in the vault (the vault is derived and rebuilt). **Limitations, stated (`schema-guardian`, M2.7 and M2.8):** `DELETE /learner` and the rating route are unauthenticated, which is right for a single-user local app and needs authentication and a confirmation step before any deployment; events for a page that later disappears from the vault stay in `learner.db` until the learner deletes them (harmless, invisible); the display thresholds 0.67 and 0.4 are written twice (`api/learner/mastery.py` and `web/components/genui/mastery.ts`, a test pins the web ones) because the wire carries the score and not the words; the corpus fingerprint is computed on every notes, lint and rating request (a few hundred milliseconds at 1,570 passages and 11,000 nodes, not cached).

**Amendment A7, 2026-10-07, before the paid run (after the `retrieval-auditor` and `cost-auditor` reviews of `atomic2`; neither found a blocking defect).** No change to the prompt (its SHA-256 stays pinned) or to a rule that decides what is stored; three tolerances and disclosures. (1) A field the model writes as `null` is read as an empty list (it previously discarded the whole passage's extraction). (2) What the caps cut and a repeated relation are now counted (`concept_over_cap`, `relation_over_cap`, `relation_duplicate`). (3) **Disclosed, not changed:** a relation's evidence is chosen by the server when the model's number does not hold, so it can be a sentence that merely holds both names rather than one that states the relation (and when one name contains the other, any sentence with the longer name satisfies both): edge precision may therefore fall against g1-3, and `relation_sentence_corrected` and `relation_window_of_two` measure how often; the Look 4 write-up reports both and the audit sample is read against them. A pair of adjacent sentences needs both parts to be at least 20 characters, and the splitter cuts after "et al." and "Fig.", so a few concepts (about 3 percent in an oracle replay of Mark 1's labels) and some two-sentence windows are lost; a sentence longer than 240 characters is cut and a label past the cut is dropped (the same as g1-3). The counters named `relation_window_of_two`, `relation_sentence_corrected`, `relation_without_a_usable_number`, `claims_kept`, `kind_other` and `alias_links_added` are information, not losses. **Tool changes:** `compare` refuses a variant whose rebuild record says it is incomplete and records each variant's builder, prompt version and claim count; a provider failure during `rebuild` is recorded as `not_built_error` with what it cost; the start-of-document projection is per builder (0.0030 per passage for `atomic2`, from the cost audit's expected $0.0022). **Preconditions of the paid run (cost audit):** commit first (the tool refuses a dirty tree), run from the repository root (the live ledger path is relative to the working directory, so another directory would see an empty ledger and a cap that does not know the spend; the existing cost tests encode this on purpose), and set `--max-usd 1.30` (at that ceiling all three papers build for any output up to about 735 tokens per call; the expected total is about $0.65, plausible $0.55 to $1.20, the worst case the ledger reserves per call is never expected).

**Amendment A9, 2026-10-14, before the full-corpus run (Look 5: the `atomic2` graph and the vault over all 16 papers; after the `cost-auditor` review, which found no blocking defect and two free fixes, both made).** No change to the prompt `g2-1`, the vault rules, `vault-1` or the gate. **What is measured:** the same 19 answerable questions, the same frozen arms (`graph`, `hybrid`, `flat`) and the four vault arms, over (a) the free-form graph of the full corpus with its vault (`data/m2/full-freeform-vault1`, Look 3's directory) and (b) the new full-corpus `atomic2` graph with its vault, against the baseline `data/eval-live-live`. **Headline pairs, named now:** `vault` against the same directory's frozen `graph`, and `hybrid_vault` against the same directory's frozen `hybrid`, both on nDCG@10, for (b); and `hybrid_vault` of (b) against the baseline's frozen `hybrid` and against the baseline's `flat` control. Everything else is exploratory. Descriptive only (19 questions, one build per graph), as at every earlier look; the gate's clause 3 stays uninformative by construction and is read as before. **The hypothesis it tests** (Azim, 2026-10-07: graph retrieval gains with corpus size): over the free-form graph the hybrid-minus-flat gap went from -0.022 at 285 passages to +0.039 at 1,570 (Look 3); this look asks whether the better graph and the vault add to that at 1,570, and whether `hybrid_vault` finally exceeds the no-graph `flat` control (it did not on the slice). A result of no gain is reported as such. **Tool changes (free):** the per-passage start-of-document projection for `atomic2` is 0.0033 (the measured $0.003134 rounded up; 0.0030 was 4 percent under); a rebuild writes its `variant.json` with `complete: false` at the start so an interrupted build cannot look like a finished one or like a copy of the pinned stores (the audit found that a hard stop left no record and the partial graph could reach a compare); a build in which more than 5 percent of passages returned an unusable extraction is not complete. **Cost (audit, measured per-call tokens of the slice, 1,570 passages, claude-haiku-4-5 at $1 and $5 per million tokens in and out):** expected **$4.92**, plausible $4.58 to $6.92 (every call at the slice's 90th-percentile tokens), embeddings under $0.01; the theoretical worst case (every call filling its 3,072-token cap) is $25 and unreachable. **Preconditions:** a **cap that fits**: the month's spend is $8.46, so the cap must be at least about $15.60 before the 2026-11-01 reset, or at least $7.10 after it (Azim edits `LLM_MONTHLY_CAP_USD` in `.env`); **`--max-usd 7.00`** (the build is not resumable: a ceiling trip discards the half-built paper and the whole run is repaid, so the ceiling is set at the high case, not the expected one); a clean committed tree (the tool refuses a dirty one); run from the repository root (the ledger path is relative to it; another directory would see an empty ledger); one uninterrupted foreground run; compare only after `vault_tool.py build` and `embed-labels`. **Commands:** `uv run python eval/graph_variant.py rebuild --slice data/eval-live-live --to data/m2/atomic2-full --builder atomic2 --max-usd 7.00 --allow-paid`, then `uv run python eval/vault_tool.py build --from data/m2/atomic2-full --to data/m2/atomic2-full-vault1`, `uv run python eval/vault_compare.py embed-labels --data data/m2/atomic2-full-vault1 --allow-paid`, `uv run python eval/vault_compare.py compare --baseline data/eval-live-live --variants data/m2/full-freeform-vault1,data/m2/atomic2-full-vault1 --allow-paid`, then `audit` for the link sample. **Not done, stated:** per-paper persistence so that a stop at paper 15 does not repay 14 (the audit's optional item d); the price table is not independently verified against the provider's console (the embeddings price is still marked `ASSUMED` in `api/llm/pricing.py`, the ledger prices with the same table), so the figure should be reconciled with the console after the run.

**A9 addendum, 2026-10-14 (after the run; the protocol above was not changed).** The ceiling used was `--max-usd 6.50` (the top of the range Azim agreed to; the monthly cap he set was $15 with $6.54 left, so $7.00 would not have fit), and a second invocation used `--resume --max-usd 1.00`. The run exposed two things the audit had flagged as risks: the provider's own credit balance is separate from the monthly cap (the failure is a 400 and looks like a bad request; it is now classified in the log as `status_400_credit_balance_low`), and a build that dies on one chunk failing on both routes cannot continue without a resume, which was added (a rebuild of the same builder, the finished papers kept, the spend summed, the earlier record required to be incomplete and to state its spend). Results: Look 5 in D-35 and `refdocs/evidence/20261014-m2-look5-full-corpus.md`.

**Amendment A8, 2026-10-07 (Q1, before the code; amends D-29): `QuizCard`, a quiz from the vault's claims, with no model.** D-29 and the catalog guide left `QuizCard` to the Studio agent (P5) because "no agent produces their evidence yet". The vault's claims are that evidence and a deterministic tool can supply it (D-30: capability grows by tools), so `QuizCard` moves from "not admitted" to **built, with the vault as its supplier**; the Studio agent will route to this tool later and may add a model-written supplier of the same block behind the same validator. It is a notes component (its own registry, as A4), placed in the chat panel's main area. **The rules (all fixed here):** (1) *Eligible claim and target:* a claim names pages; a page can be blanked if its label or an alias occurs in the claim's sentence as a whole word (case-insensitive, the longest such name first, literal text, so a name broken by PDF hyphenation makes no item); a claim's **target** is the eligible page with the lowest mastery (a page not rated counts 0.5), ties to the higher spread, then the page id. (2) *Choosing items:* up to **5**; claims are taken in order of the target's mastery ascending, then the claim id; **one item per target page**, except when the quiz is about one page (`focusId`), when its claims (those that name it) give up to 5 items in claim-id order, each with that page as target. (3) *The blank:* **every** whole-word, case-insensitive, literal occurrence of **every** name of the target (its label and its aliases, each of at least 2 characters, the longest first) is replaced by `_____` (five underscores); the item is not made when a name still occurs in the blanked text (hyphen-blind, so a name a PDF broke across a line cannot stay), when the sentence already holds a `_____`, or when fewer than 4 words are left (the blank counts as one). *Revised the same day after the `schema-guardian` review found that the first form (the first occurrence of one name) left a name of the answer in the sentence in 122 of 1,569 real items; with the revision 0 of 1,577 do.* (4) *Options:* the target and **3 distractors**: pages mentioned in **at least two passages**, with a name of 3 or more characters, of **at most six words and without a `:` or `?`** (a longer name is a paper's title, a reference-list entry that became a page), **not** the target, **not** a page whose name occurs in the sentence, **not** a page whose word set contains or is contained by the target's (so "language models" is never a distractor for "large language models"), and, when the target has a kind, of the same kind; ordered by `sha256(item_id + "|" + page_id)` ascending, first three; the four options are then ordered by `sha256(item_id + "|order|" + page_id)`. An item with fewer than 3 distractors is not made. (5) *Item id:* `claim_id + "~" + target_page_id`. (6) ***The block never carries the answer or the source quote** (the quote contains the answer): an item has its id, the blanked text, the four options (id and label) and the source's document title (left out, as an empty string, when it holds a name of the answer: a title that is a file name such as `2312.10997_Retrieval_Augmented_Generation_...` would give it away; 290 of 1,577 real items) and page; the `POST /quiz/answer` response carries the right page, whether the choice was right, the source as a validated `Citation` and the page's mastery after the event. (7) *Answering:* the server derives the item again from its id (the claim and the target page must still exist and the name must still occur in the sentence), compares the chosen page id with the target, records `quiz_correct` or `quiz_wrong` for the **target** page (never the page that was chosen) and answers (the reply is built first and the event recorded last, so a failure never leaves an event behind for a retry to record again); a forged id, an unknown page and a quiz signal sent to the rating route are refused (the rating route stays at three self-ratings). (8) *Validation:* the validator derives the block again from the vault, the passages and the mastery snapshot of the request and requires equality, so a moved blank, a changed option or an added answer field is refused. (9) With no claims, or none that can be blanked, the block is `empty` and the screen says why in words. **Revised the same day, before anything used it:** the two extra conditions of rule 4 (two passages, not title-like) were added after a read-only look at the 819 real claims of the `atomic2` slice vault (`data/m2/atomic2-vault1`, 777 claims make an item). With the first form of the rule, 119 of 3,108 options (3.8 percent) were more than six words (paper titles) and 56 held `:` or `?`, and several wrong answers were one-off mentions ("Tokyo Skytree", "Meiji Shrine") that made an item trivial; with the two conditions 4 and 1 remain (answers, which a claim names, are not filtered) and the same 777 claims still make an item. The remaining weakness is a wrong answer that is a real but unrelated concept of the same kind. **Limits, stated:** there is no per-question guard: a client can answer the same question again and each answer is an event in the learner's own data (their mastery, nothing shared); if the documents change between the quiz and an answer, the question can no longer be derived and the answer is refused (404 or 422, nothing recorded), so the screen offers more questions; a failure while the server re-derives a quiz is a generic error envelope, nothing unvalidated is shown; a plural or other form of a name that is not an alias of the page ("the LLM" for "large language models") can stay in the sentence; a cloze tests recognising a name in a sentence, not understanding; distractors chosen without a model can be too easy; a quiz changes as mastery moves, so a repeated request gives different items.

**Spend.** Only the `atomic2` rebuild (extraction, under the cap and a `--max-usd` ceiling enforced per call, confirmed by Azim beforehand) and embeddings (the questions' query embeddings and the page labels, under $0.001 together) are paid.

**Look 2 result, 2026-10-07 (`vault-1` over the g1-3 graph).** Reported in `refdocs/evidence/20261007T060911Z-m2-look2.md`; no amendment was made after seeing it. The gate did not pass because clause 3 (question words recognised) failed by construction, as A3 said it would (0.3886 against 0.5463; the vault reads the same node ids as the g1-3 resolver); clauses 1, 2 and 4 passed. The headline pairs (19 questions, descriptive): **`vault` against the frozen `graph` over the same nodes: nDCG@10 0.1408 to 0.2268, 8 better, 10 tied, 1 worse; `hybrid_vault` against the frozen `hybrid`: 0.3706 to 0.3454, 5 better, 7 tied, 7 worse.** The vault is a much stronger graph signal on its own and does not improve the fused arm; the `flat` control (0.3826) is still the best arm. Ablations: the spread discount carries the gain (without it the gain nearly vanishes); co-mentions add a little; the semantic step as registered did not help. Cost $0.000445. Candidates for a `vault-2` are recorded in the evidence and not applied.

**Look 3 result, 2026-10-07 (`vault-1` over the pinned 16-paper free-form graph, A5).** Reported in `refdocs/evidence/20261007T131202Z-m2-look3-scale.md`; no amendment after seeing it. All four gate clauses pass (clauses 2 and 3 carry no information here, as A5 said). **On scale (Azim's question):** the frozen graph signal helps the hybrid more as the corpus grows: nDCG@10 hybrid minus `flat` is -0.0215 on the 285-passage slice (5 better, 8 worse) and **+0.0394 on all 1,570 passages (7 better, 4 worse)**; descriptive, same 19 questions, one ingestion, different passage mix. **On the vault:** over the free-form graph it is level with the frozen graph arm (+0.0111, 8 better, 6 worse) and the hybrid with it is slightly below the frozen hybrid (-0.0331); its large gain at Look 2 was over the evidence-checked atomic graph. Cost about $0.0065. The measurement that now matters is the `atomic2` graph at full scale (about $4 to $6, needs the cap raised or the 2026-11-01 reset).

**Look 4 result, 2026-10-07 (`vault-1` over the `atomic2` graph of the slice).** Reported in `refdocs/evidence/20261007T140853Z-m2-look4.md`; no amendment after seeing it. The `atomic2` rebuild cost $0.8928 (Azim confirmed a $1.30 ceiling; 285 passages, no failures) and the graph is larger and better connected than g1-3's (1,295 nodes and 947 edges against 744 and 221; about 55 percent of proposed relations survive against about 24 percent; the frozen resolver recognises 0.475 of a question's words against 0.389). **Headline pairs:** `vault` against the frozen `graph` over the same nodes nDCG@10 0.2107 to **0.2871** (6 better, 11 tied, 2 worse); `hybrid_vault` against the frozen `hybrid` 0.3247 to **0.3496** (+0.0249, positive where it was negative over g1-3). The graph arm over `atomic2` alone (frozen retriever) scores 0.2107 against 0.1408 over g1-3 and 0.1360 over the free-form graph. The semantic fused arm (exploratory) reaches 0.3624, level with the free-form hybrid (0.3611); claims add about +0.007. **Still not above the no-graph control** (`flat` 0.3826) on this 285-passage slice; Look 3 showed that comparison reversing at 1,570 passages with the older graph, so the full-corpus `atomic2` build is the measurement that can answer it. Gate clause 3 fails by construction again (0.4747 against 0.5463). Cost for the look about $0.8935; month total $8.4561.

**Look 5 result, 2026-10-14 (`vault-1` over the full-corpus `atomic2` graph and over the free-form graph, 16 papers, 1,570 passages).** Reported in `refdocs/evidence/20261014-m2-look5-full-corpus.md`; no amendment after seeing it. The build cost **$5.117** (two invocations: Anthropic's own credit balance ran out mid-run and the seam's fallback served 942 calls through OpenRouter at the same model; a `--resume` kept the 14 finished papers and built the last two for $0.40); the confirmed range was $3 to $6.50. Headline pairs on nDCG@10 (19 questions, exact Wilcoxon): `vault` against its own frozen `graph` **0.1028 to 0.1371 (+0.034; 8 better, 4 worse; p = 0.52)**; `hybrid_vault` against its own frozen `hybrid` **0.1823 to 0.1822 (no change; p = 0.57)**; `hybrid_vault` against the baseline's free-form frozen `hybrid` **0.2080 to 0.1822 (-0.026; 3 better, 9 worse; p = 0.11)**; `hybrid_vault` against the baseline's `flat` control +0.014 (p = 0.41), a smaller margin than the free-form frozen hybrid's +0.039 over `flat` (p = 0.15, reproduced). The `atomic2` graph is smaller than the free-form one (6,833 nodes and 5,646 edges against 11,173 and 13,972) and the frozen resolver recognises fewer question words (0.632 against 0.657), so the gate's clause 3 fails, not by construction this time. **Reading:** the vault strengthens the graph signal itself (as on the slice) but that does not carry into the fused result; Azim's hypothesis (graph gains with corpus size) is supported only for the free-form graph and only descriptively; at this size the new builder and the vault do not beat the frozen free-form hybrid, and every difference is within noise. The vault's case in this project is the notes, links, claims, quiz and mastery it supports, not a retrieval gain.

## D-36: VerifiedLab starts as one generated pure function inside a fixed template, behind a verifier that alone mints the deliverable type (2026-10-08, extends D-10 and D-31)

**Decision.** The first level 3 slice (P4) generates **one pure numeric function** `lab(params)` in a restricted JavaScript subset. The interactive chrome (sliders, plot, readout) is a **fixed template we wrote** (pinned by a version number and a fingerprint test that fails when the template text changes without a version bump), held by the web host; it is never generated. A lab is declared by a **contract** (parameters with ranges, outputs, a cited source passage, reference cases, properties). The function passes four gates in order: (1) the contract's evidence precondition (the formula is in a stored passage, cited); (2) the **checker**, an AST allowlist (acorn) that accepts only listed constructs and identifiers; (3) the **verifier**, which runs the function in a locked-down `node:vm` child process (no `require`, null-prototype context, frozen intrinsics, a time, memory and output limit) on the reference cases, the properties and a seeded fuzz, and compares with a Python reference; (4) the **mint**: only the verifier module can construct `VerifiedArtifact` (a private token), and only that type can build a `VerifiedLab` block. The block carries the verified source as inert data with its SHA-256 and the template version; the validator re-derives the block from the stored verified record by `labId` and requires equality (the `ConceptPage` pattern), and the web host checks the hash before it renders. It renders in `<iframe sandbox="allow-scripts">` (no other token) with a `<meta>` CSP of `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'`; libraries come from a local vendor directory that starts empty, and a URL or an unlisted library is rejected. A mutation suite of at least 25 planted defects, each with the stage that must reject it, is run and its **detection rate and limits are recorded**. This slice has the lifecycle states `generated` and `verified` only; `cached`, `audited`, `promoted`, eviction, staleness and crystallisation are P4b.

**Why.** The safety argument of the project is that generated code reaches the client only through a gate that is itself checked. A general generated app cannot be verified with bounded effort; a generated function with no names for the DOM, the network, storage, time or randomness can be bounded and tested, and the template is where the user-facing behaviour (and its accessibility) is written once by us. The gate is made of two independent lines on the server (allowlist, then an isolated execution) and a third in the browser (the sandbox and the CSP), so one hole in one line is not the whole claim. `node:vm` is **not** presented as isolation (the Node documentation says it is not a security mechanism): it is a correctness and resource harness in a child process, and the isolation claim rests on the process boundary and the browser sandbox. The claim is worded as "rejected every planted defect in this set", never "proven safe".

**Rejected / trade-offs.**
- *Arbitrary generated UI (React, DOM, canvas code) in the iframe:* cannot be verified with a bounded effort; the fixed template removes DOM access from the generated part altogether. Cost: a lab can only be a numeric function of declared parameters.
- *A tiny expression language instead of JavaScript:* sound and simple to check, but it weakens the claim that this is generated *code*. Kept as the **fallback** if the AST allowlist proves unsound under the mutation suite.
- *`allow-same-origin`, a runtime CDN, or evaluating generated code in the host page:* forbidden by hard constraint 3.
- *Pyodide or WebAssembly:* a large attack and size surface for a first slice.
- *A blocklist checker:* open-ended by construction; the allowlist fails closed.
- *The Lab Builder as an agent now:* D-30, growth is by tools; this slice is a tool behind a route.

**Amendment 2026-10-08 (after two independent reviews of the built slice).** (1) *"The wire carries data only" is amended for one field:* `VerifiedLab.source` is the text of a function that only the verifier can mint; the web host treats it as inert text until it places it, with its own template, in the sandboxed iframe (the schema header says so). (2) *The verifier runs every value the interface can ask for.* A red-team review found a source that matched the reference on the whole sampled battery (603 vectors) and froze the iframe at one slider position, and a sibling that returned a wrong number there; both were VERIFIED. A sample is never complete, so the contract now fixes a **grid** (each parameter takes `gridSteps + 1` evenly spaced values, the sliders are grid indexes, the swept axis uses the grid) and the verifier runs **all combinations** (at most 10,000) plus a seeded fuzz as extra evidence; what the user can reach is exactly what was verified. A branch off the grid is not seen and is unreachable. (3) *Loop bounds are exact:* the same review found a loop the checker counted as 10 iterations that never ends in floating point; loop literals are now integers of bounded size, with a cap on the total iterations over all loops (20,000) and on call time (a mean of 5 ms and at most 250 ms for any call; a first 50 ms maximum refused a good lab under machine load and was replaced), and loop counters obey the name rules (a counter could shadow `Math` or `p`). (4) *The gate does not trust the store:* the delivery gate re-hashes and re-checks the stored source and compares a fingerprint of the contract, the store ties the id to the hash and never replaces a lab, and the mint is a closure-held token on a class that cannot be subclassed. (5) *The template is "fixed and versioned", not hash-pinned:* a fingerprint test fails when its text changes without a version bump (the CSP also forbids `base-uri` and `form-action`). The slice now has a mutation suite of 120 planted defects in four families, all refused by the stage named for each; that is regression coverage of a set the project wrote, and the independent reviews (a `schema-guardian` pass and an adversarial pass that ran 60,000 mutation-fuzz and 400,000 markup-breakout cases with no checker bypass) are the stronger evidence. **Honest limits stay:** `node:vm` is not isolation; the claim is "refused every planted defect and survived these reviews", never "proven safe".

**Amendment 2026-10-14 (the domain, and more labs).** Azim asked whether scoring and loss formulas are the right domain or "a legacy thing". The reasoning: the *generation* tier is domain-free by construction (constraint 7): a lab exists only where a stored passage states the formula, and where none does the server says so (`empty`, and `GET /labs` lists the lab as unsupported with the reason). So the right unit is "formulas the user's own documents state", not "loss formulas". For this corpus (retrieval and ranking papers) those are exactly the metrics and losses a reader of the papers has to understand, and they are the same quantities this project's own benchmark reports (recall@k, F1@k, nDCG). For a corpus with no stated formulas the tier correctly produces nothing; it is **not** a general interactive-app generator and does not claim to be. The probe that chose the labs (2026-10-14, free): the passages state F1@k as "the harmonic mean of precision and recall" (and recall@k and precision@k as fractions), the InfoNCE loss, the RankNet loss and a cosine chunking distance `1 - max(cos, 0)`; they do **not** state reciprocal rank fusion, BM25 or nDCG as formulas (those are named only), and the pointwise BCE is printed as `log sigma(1 - s)`, which differs from the standard `log(1 - sigma(s))`, so it was **not** made a lab (teaching a probable typo as the formula would be worse than no lab). Four labs now exist (RankNet loss, F1@k from hits, k and relevant documents, InfoNCE, the chunker's cosine distance), each with a hand-written reference, a phrase that must occur verbatim in a stored passage, and the same all-grid verification. A live generator is still not built (V9, paid). Azim also confirmed the restricted-JavaScript subset and `acorn` (2026-10-14).

**Open / assumed (see Working assumptions):** the domain (retrieval-scoring formulas from the corpus, replacing Q-06's physics example), the restricted-JavaScript choice, the new dependency `acorn`, and a live generation run (paid, Azim confirms the amount first).

## D-37: P3 (trained tools) is reduced to one measured engine; built and measured, not shown to help (2026-10-14)

**Decision (proposed).** Do **not** build the distilled router or a trained Mastery engine. Build **one** engine behind the `Engine` interface, a **Re-Rank engine using a pretrained cross-encoder** (not trained by us), evaluated as a new arm on the same 19 questions at candidate depths 10, 30 and 50 against the RRF order and the vault arm, with the paired test already in `eval/stats.py`, the protocol written before the run, and the result reported whichever way it falls. If review scheduling is wanted later, adopt FSRS with its default parameters as a deterministic engine.

**Why.** (1) v1 never built an engine (its repository has no `engines` package, only a specification), so there is no measured benefit to inherit. (2) The stored P1 benchmark bounds a re-ranker over the top ten: a perfect oracle re-ordering of the same ten passages lifts the hybrid arm from 0.208 to 0.290 nDCG@10, six of 19 questions have no relevant passage in the top ten at all, and the binding weakness is recall (about 0.21 at ten); the graph and vault work moved a larger lever. (3) A router saves a fraction of a cent per turn on a single-user workspace and has no training data; a learned mastery model has no review history. (4) The original proposal has a graded Objective 03 ("Trained ML Models"); the v2 direction records an advisor-approved scope change but not that the objective was removed, so one honestly evaluated engine is the smallest way to keep it satisfied. The full deliberation is `refdocs/plans/2026-10-14-p3-trained-tools-deliberation.md`.

**Rejected / trade-offs.** Dropping P3 entirely: cheapest, but an assessment risk if Objective 03 stands. Training our own models: no data worth the name; a model trained on LLM-judged labels measures the judge (v1's R-11). A heavy dependency (torch) for a small expected gain: ONNX first, and stop if the footprint is large.

**Result (2026-10-14, Azim: "implement").** Built: `api/engines` (the `Engine` interface, the fallback rule, a cross-encoder re-rank engine on `fastembed`/ONNX as the optional `engines` extra). Measured with a protocol committed before the run (`eval/rerank_compare.py`, `refdocs/evidence/20261014-p3-rerank.md`): on the 19 questions, `rerank_n50` against its depth control `hybrid_n50` gives -0.007 nDCG@10 (7 better, 7 worse, 5 tied, p = 0.90), so by the rule fixed in advance the engine is **not shown to help**; at 30 candidates +0.021 (p = 0.60). It costs about 5 s per query on CPU. The engine stays built, additive and **off by default**. **A finding that matters more:** the candidate depth alone (30 per signal instead of 10) raises the hybrid arm's Recall@10 from 0.212 to 0.305 with no model (exploratory, p = 0.21); that is a candidate protocol amendment for the final benchmark, declared before it, not applied (adopted in the product path by D-38). Spend $0.000062. **Open.** Whether Objective 03 is satisfied by this negative result (Azim).

## D-38: The product retrieval path takes 30 candidates per signal before fusion; the frozen benchmark arms are unchanged (2026-10-14, follows D-37)

**Decision.** `Container.retrieve` (the product path, which every agent and route uses) asks each retriever for `CANDIDATE_DEPTH = 30` passages before RRF fusion; the fused cut stays at 10 (`TOP_K`). `hybrid_retrieve(..., depth=None)` keeps the frozen protocol by default (depth equals `top_k`, D-20), refuses a depth below `top_k`, and the frozen benchmark arms are not touched. It is a code constant, not an environment variable. For a final benchmark the amendment is to **report `hybrid_d30` (from `eval/rerank_compare.py`) beside the frozen `hybrid`**, never in place of it.

**Why.** Azim: "if it improves the system then go for it." The only lever the P3 work found that moved the binding weakness (recall at ten) without a model, a dependency or a cent: on the same 19 questions, the hybrid arm at 30 per signal gives Recall@10 0.2123 to 0.3054 (+0.093; 6 better, 12 tied, 1 worse; exact Wilcoxon p = 0.094) and nDCG@10 0.208 to 0.238 (+0.030; 8 / 4 / 7, p = 0.80, mixed). Leave-one-question-out the recall gain stays between +0.057 and +0.109, and it is in the same direction in every question category. It costs nothing at query time that matters (three retrievers return 30 rather than 10 rows; the cross-encoder, which was the slow part, is not in this path).

**Stated limits.** (1) The depth was chosen after seeing the results, among depths declared in advance ({10, 30, 50}); 50 gave +0.080 (p = 0.21). (2) 19 questions: the recall p-value is 0.094, not below 0.05; nDCG is flat. (3) Exploratory by the protocol's own label. (4) The adoption is a product decision on the strength of a measured, consistent, free gain with one worse question in nineteen; it is **not** a claim that deeper candidates beat the frozen protocol significantly.

**Rejected / trade-offs.** Waiting for a larger question set before adopting: the cost of being wrong is nearly nil (the fused cut is still 10, and one question is worse), and the gain is the largest measured in this project. Depth 50: smaller measured gain and more noise per signal. An environment variable for the depth: another knob that has no tested meaning at other values.

## Working assumptions (`ASSUMED:`)

Not decisions; guesses made to keep moving. Each one must be confirmed or killed before anything
load-bearing is built on it. When one is resolved, delete it here and write a real ADR above.

1. **ASSUMED (D-36; narrowed 2026-10-14, still to be confirmed by Azim):** a lab is made only from **a formula that a stored passage states**, and is offered only where one does (`GET /labs` says which; the rest are listed as unsupported, with the reason). This replaces the PRD's physics example (Q-06). Azim (2026-10-14) was unsure that scoring and loss formulas are the right domain; the deliberation is in the D-36 amendment below, and the labs added since are teaching formulas for the metrics and losses retrieval papers use.
2. **ASSUMED:** OpenRouter model ids follow its dotted naming (`anthropic/claude-sonnet-5.5`, `-opus-5.5`, `-haiku-4.5`). Its public model list did not show the sonnet and haiku entries on 2026-10-05. Confirm in P0 task 10.
3. **ASSUMED:** `text-embedding-3-large` costs $0.13 per million tokens (`api/llm/pricing.py`). The OpenAI reference page does not state a price. Confirm against the pricing page before the first live embedding run (P0 task 10); the cap check depends on it. **Confirmed 2026-10-07 by `cost-auditor`'s fetch of the OpenAI pricing page ($0.13 per million tokens) and the Anthropic pricing page (Haiku 4.5 $1 and $5, Sonnet 5.5 $2 and $10, Opus 5.5 $4 and $20 per million), matching `api/llm/pricing.py`; delete this item when Azim agrees.**

4. **ASSUMED:** D-28's default "the first answer applies Adaptive unless Basic is pinned" is built (`web/lib/store.ts`). It is sticky: once Basic is pinned, Adaptive does not auto-apply until the user chooses it. Confirm or change at the next checkpoint.

Resolved and removed from this list: Q-02 (D-17), Q-03 (D-18), Q-04 (D-22), Q-05 and Q-01 (D-21), Q-08 (Tailwind v4 and LangGraph 1.x read from current docs at install: `@tailwindcss/postcss` with `@import "tailwindcss"` and no config file; `StateGraph(State, context_schema=...)`, `runtime: Runtime[Context]` in nodes, `graph.ainvoke(..., context=...)`).
