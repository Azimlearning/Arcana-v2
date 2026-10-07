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

## Working assumptions (`ASSUMED:`)

Not decisions; guesses made to keep moving. Each one must be confirmed or killed before anything
load-bearing is built on it. When one is resolved, delete it here and write a real ADR above.

1. **ASSUMED:** the VerifiedLab tier targets STEM content in the user's corpus; the physics contract covers its checkable subset (Q-06). Resolve in the P4 plan.
2. **ASSUMED:** OpenRouter model ids follow its dotted naming (`anthropic/claude-sonnet-5.5`, `-opus-5.5`, `-haiku-4.5`). Its public model list did not show the sonnet and haiku entries on 2026-10-05. Confirm in P0 task 10.
3. **ASSUMED:** `text-embedding-3-large` costs $0.13 per million tokens (`api/llm/pricing.py`). The OpenAI reference page does not state a price. Confirm against the pricing page before the first live embedding run (P0 task 10); the cap check depends on it.

4. **ASSUMED:** D-28's default "the first answer applies Adaptive unless Basic is pinned" is built (`web/lib/store.ts`). It is sticky: once Basic is pinned, Adaptive does not auto-apply until the user chooses it. Confirm or change at the next checkpoint.

Resolved and removed from this list: Q-02 (D-17), Q-03 (D-18), Q-04 (D-22), Q-05 and Q-01 (D-21), Q-08 (Tailwind v4 and LangGraph 1.x read from current docs at install: `@tailwindcss/postcss` with `@import "tailwindcss"` and no config file; `StateGraph(State, context_schema=...)`, `runtime: Runtime[Context]` in nodes, `graph.ainvoke(..., context=...)`).
