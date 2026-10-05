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

**Open.** The cap value (Q-01).

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

---

## Working assumptions (`ASSUMED:`)

Not decisions; guesses made to keep moving. Each one must be confirmed or killed before anything
load-bearing is built on it. When one is resolved, delete it here and write a real ADR above.

1. **ASSUMED:** a local vector store exists that handles 3,072-dim vectors on Windows without a server (Q-02). Resolve in the P0 spike.
2. **ASSUMED:** Python 3.12, not 3.13, because v1 pinned `<3.13` for a reason it did not record (Q-03). Resolve in P0 task 1.
3. **ASSUMED:** the agent roster in PRD §3.1 (Q-04). Resolve in the P1 plan.
4. **ASSUMED:** v2 reuses v1's 20 pre-registered questions and 16-paper corpus manifest (Q-05). Confirm with Azim before gold annotation.
5. **ASSUMED:** the VerifiedLab tier targets STEM content in the user's corpus; the physics contract covers its checkable subset (Q-06). Resolve in the P4 plan.
6. **ASSUMED:** current Tailwind and LangGraph APIs differ from v1's; read their docs at install rather than copying v1 usage (Q-08).
