# Arcana v2: Product Requirements Document (PRD)

> Arcana v2 is a learning workspace over a student's own documents. Documents are extracted into a
> knowledge graph alongside a vector index; retrieval fuses graph traversal with dense and sparse
> signals by rank. **GraphRAG is the core.** On it stand two pillars: a small set of advanced agents
> with powerful typed tools, and a generative interface that composes typed components, lays out an
> adaptive dashboard, and, only when no component can express an answer, delivers a verified,
> sandboxed interactive artifact. Trained models are tools that serve the pillars. v2 is a ground-up
> rebuild; Arcana v1 is the reference.

- **Owner:** Fakhrul Azim Bin Ahmed Mardzukie (sole author). FYP supervisor: Dr Mazeyanti Bt M Ariffin.
- **Users:** a single user (the author), local-first, no authentication.
- **Status:** Scaffolded 2026-10-05, pre-implementation
- **Last updated:** 2026-10-05
- **Source of record:** [arcana-v2-sources.md](arcana-v2-sources.md)
- **Founding context:** [context/2026-10-05-v2-direction.md](context/2026-10-05-v2-direction.md) (decisions and their sources); Arcana v1 PRD (`../Arcana/docs/arcana_prd.md`); the MCAIT 2026 paper (`../Technical-Paper/Paper/latex/main.tex`); the Synapse v4 plan (`GenUI-Education/Synapse-V3/docs/ENHANCED_VERSION_PLAN.md`)

FYP title: *Arcana: A GraphRAG-Powered Multi-Agent Research and Learning Intelligence Platform.*

---

## 1. Context & Hard Constraints

Confirmed from the founding context document and the 2026-10-05 interview. They drive every
downstream decision.

| Constraint | Value | Consequence |
|---|---|---|
| Users | Single user, no auth (D-04) | No accounts, sessions, tenancy or per-user isolation work. Data lives on the local machine. |
| Build approach | Ground-up rebuild; v1 is reference (D-01) | Nothing is inherited by default. A v1 or Synapse file copied in carries a provenance header. |
| Evaluation | Automated only; no user study, no public testing (D-06) | The results chapter rests on the retrieval benchmark, the extraction audit and verifier mutation tests. No SUS score, no participants. |
| Cost | Pay-per-use LLM APIs with a monthly cap (D-08) | Per-turn token budget, model tiers per task, caching. The cap starts at $5 (D-21). |
| Hardware | Windows 10 laptop; no Docker, no Postgres | Local-first storage that needs no server (D-09). |
| Deploy | Decided later; local first (D-13) | Nothing assumes a host. Config is environment-driven so a host can be added. |
| Paper continuity | The MCAIT paper's claims and protocol are the baseline | Benchmark settings stay comparable with v1 (chunking, embeddings, k = 60, the 20 pre-registered questions) unless an ADR says otherwise. |

---

## 2. Product Principles

1. **Ground before generating.** No user-facing claim exists without retrieved evidence and a
   traceable citation.
2. **Retrieval structure bounds the interface.** A component asserts a shape of answer; it may only
   be offered when retrieval can supply that shape from evidence (the MCAIT paper's bound).
3. **The wire carries data only.** Typed blocks, validated server-side, failing closed. Generated
   code exists only as a verifier-minted, hash-addressed artifact in a sandbox (D-10).
4. **The vocabulary grows on evidence.** New components arrive through the governed lifecycle,
   never by hand-waving (D-11).
5. **Fewer, deeper agents.** An agent earns its place with tools that do real work, not with a role
   name (D-05).
6. **Models add, heuristics remain.** Every trained tool sits behind a heuristic it falls back to
   (D-12).
7. **Measured, not asserted.** Evidence comes from runs with fixed protocols; changes to a protocol
   are declared as amendments (D-06, D-15).

---

## 3. Architecture

```
                         ┌──────────────────────────────────────────┐
  browser  ◀── SSE ───── │  web/  Next.js: adaptive shell, registry, │
  (single user)          │  catalog components, sandbox host         │
                         └───────────────────▲──────────────────────┘
                                             │ typed UIBlocks / LayoutSpec (packages/schema)
                         ┌───────────────────┴──────────────────────┐
                         │  api/  FastAPI                            │
                         │  ┌─────────────── PILLAR: AGENTS ───────┐ │
                         │  │ Orchestrator (+ distilled router)    │ │
                         │  │ Research · Graph · Fact Checker      │ │
                         │  │ Studio (learn · write) · Lab Builder │ │
                         │  │ Composer (only one picking UI)       │ │
                         │  └──────────────────────────────────────┘ │
                         │  ┌─────────────── PILLAR: GENUI ────────┐ │
                         │  │ L1 typed blocks · L2 LayoutSpec      │ │
                         │  │ L3 VerifiedLab (contract + verifier) │ │
                         │  │ validator (fail closed) · lifecycle  │ │
                         │  └──────────────────────────────────────┘ │
                         │  TOOLS: router · re-rank · mastery (Engine ABC, additive)
                         │  ┌─────────────── CORE: GRAPHRAG ───────┐ │
                         │  │ ingest → chunk → embed → extract      │ │
                         │  │ dense + BM25 + graph  ──RRF──▶ top-k │ │
                         │  │ GraphStore · VectorStore · DocStore  │ │
                         │  └──────────────────────────────────────┘ │
                         └───────────────────────────────────────────┘
                                eval/  benchmark · audit · mutation suite
```

### 3.1 Components

**Core: GraphRAG.** Ingestion parses, chunks, embeds and extracts entities and relations
(schema-free) in one pass, writing vector index and graph together. Retrieval computes dense, sparse
(BM25) and graph signals concurrently and fuses them with reciprocal rank fusion. Query entity
resolution is approximate and measured, since it was the pilot's bottleneck. Every signal can be
switched off independently for ablation. Graph edges carry the passage they were extracted from.

**Pillar 1: agents.** A small roster (D-05, D-22, D-30): Orchestrator, Research, Graph, Fact Checker and
Composer are built; the learning and writing tools will live in one Studio agent (P5, ASSUMED merge) and Lab Builder
arrives with P4. An agent exists only for a distinct trust boundary, state or terminal duty; everything else is a
tool group. Agents share one state object,
call each other only through `route_to_agent` within hop and token budgets, and always terminate at
the Composer. "Super tools" means each agent's typed tools do substantial work (cross-document
comparison, path finding, verbatim quote checking, contract checking) rather than wrapping a prompt.

**Pillar 2: generative UI.**
- **Level 1:** typed component blocks (`{type, data, meta}`) from a catalog; payloads filled from
  retrieved evidence; four render states each (empty, loading, partial, error).
- **Level 2:** a typed `LayoutSpec` produced by the Composer from mode, intent and learner signals:
  which components, which panels, what order. Layout is data.
- **Level 3:** `VerifiedLab`: an interactive artifact generated from a declared contract,
  deterministically checked, then verified; the delivery path accepts only a type the verifier can
  mint. Rendered in an iframe with `sandbox="allow-scripts"` only, libraries served from a local
  vendor directory. Streams in after the rest of the answer as a `partial` block.
- **Governed lifecycle:** every generated artifact moves generated → verified → cached → audited →
  promoted. A pattern promoted repeatedly can be crystallised into a level 1 component, admitted only
  if retrieval can satisfy its precondition. Flags evict; a model or prompt version change marks
  artifacts stale.

**Tools: trained models.** Behind one `Engine` interface with `predict()` and `is_available()`.
Candidates: a distilled mode/intent router (Synapse method, confidence-gated fallback to an LLM
call), a Re-Rank engine after RRF, a Mastery engine for review scheduling (optional). Each falls back
to its heuristic when absent.

**Evaluation harness (`eval/`).** Fixed question set and corpus manifest, gold passage annotation,
an ablation runner over the five arms, RAGAS metrics, an extraction audit, and a verifier mutation
suite.

### 3.2 Data & state

ASSUMED where marked; settled in the P0 plan.

| Data | Store | Notes |
|---|---|---|
| Knowledge graph (nodes, edges with source passage) | NetworkX, persisted to disk, behind `GraphStore` | Neo4j adapter possible later behind the same interface |
| Chunk embeddings (3,072-dim) | Local vector store behind `VectorStore` | ASSUMED: library chosen by a P0 spike (Q-02) |
| Documents, chunks, artifacts and lifecycle state, review state, turn log | SQLite via SQLAlchemy, behind `DocStore` | Single file, no server |
| Raw uploaded files | Local data directory | Source of truth for re-processing |
| Generated artifacts (L3) | Local data directory, addressed by content hash | Lifecycle state in SQLite |
| Eval inputs and results | `eval/` in the repo; corpus PDFs listed by identifier, not committed | Results committed as JSON |

---

## 4. Modules / Feature Areas

| Module | Owns | Built in |
|---|---|---|
| `packages/schema` | Every type that crosses the wire; codegen to Python | P0 |
| `api/core` | Settings, logging, error envelope, budgets | P0 |
| `api/llm` | One LLM seam: Anthropic primary, OpenRouter fallback, model tiers, spend ledger | P0 |
| `api/stores` | GraphStore, VectorStore, DocStore abstractions and local implementations | P0 |
| `api/ingestion` | Parse, chunk, embed, extract | P0 |
| `api/retrieval` | Dense, BM25, graph, RRF, signal toggles | P0 |
| `api/agents` | The agent roster, `route_to_agent`, shared state, LangGraph assembly | P0 (one agent), P1 |
| `api/genui` | Validator, streamer, Composer contract, lifecycle registry | P0 (validator), P2, P4 |
| `api/engines` | Trained tools behind `Engine` | P3 |
| `api/labs` | Contract, checker, generator, verifier, delivery gate | P4 |
| `web` | Shell, registry, catalog components, sandbox host, stream consumer | P0 (one component), P2, P4 |
| `eval` | Benchmark, gold set, RAGAS, audit, mutation suite | P0 (harness), then every phase |

---

## 5. Non-Goals

Explicitly out of scope. Revisit only by adding an ADR that says why.

- Accounts, authentication, multi-user notebooks, collaboration (D-04).
- A user study, participant recruitment, or public testing (D-06).
- Synapse's product scope: KSSM syllabus library, misconception tutor, phone-first, offline packs,
  Bahasa Melayu (founding context, decision 1).
- Matching v1's agent count; agent count is not a target (D-05).
- A native mobile app, audio or video generation, general web search (carried from v1).
- Local or offline LLM inference (carried from v1).

---

## 6. Build Roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| **P0** Walking skeleton + eval harness | Monorepo, schema + codegen, settings, LLM seam, three stores, ingestion, hybrid retrieval with toggles, one agent, one `CitedSummary` block validated and streamed, rendered in the browser; eval harness with gold-set format and RAGAS smoke run | One PDF → a cited answer rendered in the browser; codegen check, backend and frontend tests green; an eval smoke run writes metrics for all five arms |
| **P1** Agent core with super tools | The agent roster, `route_to_agent`, budgets, Fact Checker with verbatim quote check (fail closed), graph edge provenance; gold annotation complete; **first full graph-vs-flat benchmark run** | Multi-agent request traced end to end; benchmark results committed with the paired test |
| **P2** GenUI catalog + adaptive dashboard | Level 1 catalog (ported from v1 where suitable) with the bound applied per component; Composer; level 2 `LayoutSpec`; the typed UI pipeline spine (templates, fences, checks, saved patterns, D-31) | Every catalog component has its precondition documented and enforced; dashboard composes from LayoutSpec |
| **P3** Trained tools | `Engine` interface; distilled mode/intent router; Re-Rank; Mastery optional | Each engine evaluated against its heuristic; fallback verified |
| **P4** VerifiedLab + governed lifecycle | Extends the P2 pipeline (D-31) with generated code: contract, checker, generator, verifier, delivery gate, sandbox host; lifecycle states, eviction, staleness, crystallisation | No path to the client bypasses the verifier (test); mutation-suite detection rate recorded |
| **P5** Learning/writing depth + polish | Studio depth (learning and writing tool groups, D-42), final eval runs, evidence for the report | Final benchmark, audit and mutation results committed |

---

## 7. Decision Log

Canonical one-line list. Load-bearing entries are expanded as ADRs in `changelog/DECISIONS.md`
under the same id.

| # | Decision | Why |
|---|---|---|
| D-01 | Ground-up rebuild; v1 is reference only; copied files carry provenance | Azim wants a fresh perspective; v1's shape was built for a different emphasis |
| D-02 | GraphRAG core; agentic AI and GenUI as the two pillars; trained models as tools | Azim's framing; matches the MCAIT paper's argument |
| D-03 | Stack: FastAPI + LangGraph (Python 3.13 per D-18, uv), Next.js + React + Tailwind (pnpm), schema-first codegen, current versions | Same proven shape as v1 and Synapse, without starting dated |
| D-04 | Single user, no auth, local-first | Azim: no study or public use |
| D-05 | A small roster of advanced agents with super tools; count is not a target | Azim: fewer, deeper, more useful |
| D-06 | Evaluation is automated only: benchmark, audit, mutation suite; no user study | Azim; the reviewers' gap is empirical retrieval evidence |
| D-07 | Build order P0 to P5 as in §6 | Azim accepted; skeleton proves the wire contract first |
| D-08 | Anthropic API primary, OpenRouter fallback, model tiers, per-turn token budget, monthly cap | Azim; v1's benchmark died on an exhausted quota |
| D-09 | Local storage: NetworkX on disk, SQLite, a local vector store, each behind an abstraction | Single user; no Docker or Postgres; removes cloud quota risk |
| D-10 | Three GenUI levels; the wire carries data only; L3 code only via the verifier-minted sandboxed artifact | Agreed 2026-10-05; preserves the paper's safety argument |
| D-11 | Governed component lifecycle with admission by the retrieval bound | Azim's elevated concept, shared with Synapse v4 |
| D-12 | Trained tools behind `Engine`, additive with heuristic fallback | v1 invariant; keeps the primary ablation clean |
| D-13 | Deploy target deferred; local first | Azim |
| D-14 | Embeddings stay `text-embedding-3-large` (3,072-dim) | Continuity with v1 and the paper's protocol |
| D-15 | Eval metrics: non-LLM context recall/precision and Recall@10 / nDCG@10 primary after gold annotation; paired Wilcoxon; RAGAS faithfulness secondary; RAGAS used as a library | Avoids confounding retrieval with generation, as the paper itself argued |
| D-16 | Synapse and v1 code is ported by copying with provenance headers; no submodules, no shared package for now | Different storage stacks; solo work; submodules are costly |
| D-17 | Local vector store is exact cosine over a numpy matrix in one `.npz`; no vector-database library | P0 spike: exact and fast at this scale, no dependency, keeps index error out of the ablation (resolves Q-02) |
| D-18 | Python 3.13 | Whole dependency set installs and imports; v1's `<3.13` pin had no recorded reason (resolves Q-03) |
| D-19 | Generated wire models are strict and forbid extras; five block statuses; `BlockMeta.error`; upsert by block id | `schema-guardian` found lax coercion accepting `"1"` for an int; fail closed means no coercion |
| D-20 | Graph retrieval scoring is frozen before gold annotation: deterministic entity resolution, evidence-based tie-break, version-stamped results | `retrieval-auditor`: hash-order ties would make the graph arm noise; free constants invite test-set tuning |
| D-21 | v1's question set and manifest reused unchanged and pinned by hash; monthly cap $5; q-single-01 found unanswerable from the corpus | Azim 2026-10-06; comparability with the pilot; constraint 9 |
| D-34 | The atomic-note graph is v2's graph direction (Azim: "not an experiment"): built beside the frozen baseline, measured as extra arms with the protocol fixed before any live run, paid in two stages, default for new ingestion once the subset shows no structural regression | Azim 2026-10-07: Obsidian-style notes at ingestion; wants real test results; constraint 9 |
| D-37 | P3 is reduced to one measured engine (a pretrained cross-encoder re-ranker against RRF, protocol first); no distilled router, no trained mastery model; proposed, pending Azim's go | 2026-10-14, Azim asked for the deliberation |
| D-38 | The product retrieval path takes 30 candidates per signal before RRF (fused cut stays 10); the frozen benchmark arms are unchanged and a final benchmark reports `hybrid_d30` beside the frozen hybrid; Recall@10 +0.093 (p = 0.094, exploratory, post hoc depth) | 2026-10-14, Azim: "if it improves the system then go for it" |
| D-39 | The question set is extended by 19 declared questions (own files and pins; frozen assets untouched) and D-38's depth is tested on them before anything else is claimed; proposed, pending Azim's gold approval | 2026-10-15 |
| D-40 | D-38 reversed: on the 19 declared new questions the 30-candidate depth changed Recall@10 by -0.007, so by the rule fixed in advance the product depth is 10 again; D-39 accepted (gold approved and pinned); the graph signal's gain over flat does not replicate (pooled -0.001) | 2026-10-15 |
| D-41 | Verified labs get a governed lifecycle (verified, cached, audited, promoted; evicted, stale): a closed transition table, a cache path that verifies the stored source again, audit, staleness at start; crystallisation reported, not built | 2026-10-15 |
| D-42 | Studio is one agent with tool groups (settles D-22 and D-30); S1 builds the writing group and the `WritingDraft` component (derived references, Fact Checker draft checks, `write` intent) | 2026-10-15, Azim: "the full studio agent as planned" |
| D-44 | The centre area has panes: any output opens beside the conversation (at most three), with a Table view (sort, filter, formula-safe CSV); the viewer's arrangement of blocks the server composed, never a component choice | 2026-10-15, Azim: the centre area "should have pane system... like Claude or ChatGPT" |
| D-43 | The Studio covers the function classes of VERA AI's six agents as tools of one agent (thirteen tools): quiz in the turn, writing kinds (literature review, abstract, audio-overview script read by the browser's voice), document brief, cheat sheet, learning insights; the audio non-goal is read as "no generated audio" (`ASSUMED:`) | 2026-10-15, Azim: the Studio "is supposed to be more" than VERA's six functions |
| D-36 | VerifiedLab (P4) starts as one generated pure function in a fixed hash-pinned template; an AST-allowlist checker and an isolated verifier gate it; only the verifier can mint the deliverable type; sandboxed iframe plus CSP; a mutation suite with a recorded detection rate; lifecycle states beyond `verified` are P4b. Amends Q-06 (domain: retrieval formulas) | 2026-10-08, proposed on Azim's "proceed"; `ASSUMED:` rows await his confirmation |
| D-35 | Mark 2 compiles the graph into a vault (links, concept pages above nodes, claim notes) with a new retrieval arm (`vault-1`), a sentence-numbered builder `atomic2`, a notes view, a learner layer and lint; protocol fixed before any run, a looks ledger on the shared 19 questions | Azim 2026-10-07: do directions A to G; constraint 9 |
| D-33 | `TraversalView`: what the search followed for a prompt, as its own component grounded by provenance; the retriever is not edited | Azim 2026-10-07: show node traversal per prompt in the top-right graph |
| D-32 | Layout v2: regions (`main`, `secondary`, `shelf`) inside a panel with a direction; the Studio is a shell (inert generator tiles, an Outputs shelf holding saved views) before it has generators, which stay in P5 | Azim 2026-10-07: v1's Studio under the graph, outputs below, middle section splitting by component kind |
| D-31 | GenUI has its own pipeline: template, fences, checking, save, reuse. P2 builds it for typed UI (templates, registration-time mutation checks, saved patterns, reuse); P4 adds generated code to the same pipeline. Amends D-29 | Azim 2026-10-06: templates, checking, saved and reusable UI, "just like Synapse but more advanced", on top of the basic components |
| D-30 | A small roster of core agents that own many tools; an agent exists only for a distinct trust boundary, state or terminal duty. Roster: Orchestrator, Research, Graph, Fact Checker, Composer, Studio (P5), Lab Builder (P4). Amends D-05 and D-22 | Azim 2026-10-06: boil v1's 25 agents down; growth by tools, not agents |
| D-29 | P2 catalog scope (five components, InsightCard stretch) plus an extension recipe; GraphView must be a real working graph output | Azim 2026-10-06: not all components, high scalability, graph output must work (v1 had a static list) |
| D-28 | Deterministic evidence-admitting Composer; a prebuilt Basic layout first, Adaptive layered on top and switchable | Azim 2026-10-06; free and testable; known-good fallback |
| D-27 | `LayoutSpec` is the single source of placement; new components need no layout change, new panels or modes are a deliberate schema change (amended 2026-10-07); `BlockMeta.panel` and `order` removed | Azim 2026-10-06: flexible for all new GenUI features; two copies drift |
| D-26 | `q-single-01` kept as an approved, pinned "should find nothing" control (amends D-21); no paper added, no question replaced | The corpus never defines RRF; replacing or adding changes frozen assets and forces a second ingestion; the control showed an empty, grounded answer |
| D-25 | Extraction output limit raised from 1,024 to 2,048 tokens after a live measurement: 8.6 percent of chunks truncated at 1,024 | First live run on one paper: 3 of 35 chunks cut off mid-JSON, 1 of 35 at 2,048; cost per chunk $0.0036 |
| D-24 | Benchmark amendments and enforcement: 19 approved questions, primary metrics Recall@10 and nDCG@10 only, freeze enforced by the paid runner, commit recorded, tie-safe Wilcoxon | Pre-benchmark retrieval audit: undeclared 19-question run, freeze checked only by pytest, results not tied to code, float-noise ties in the test |
| D-23 | Spend ledger is one file in a live mode (`./data/ledger.db`); cap required when any paid mode is live; priced by requested model; no SDK retries; per-document ingestion limits | Pre-live cost audit: separate ledgers, a dated model id priced as Opus, an uncapped live-embeddings mode, unledgered retries, uncapped single uploads |
| D-22 | P1 roster: Orchestrator, Research, Graph, Fact Checker (+ Composer stub); routing in `route_to_agent`, explicit roster, fail-closed Fact Checker | Q-04 resolved; hops and budgets must be plain testable code; v1's global registry and fail-open checker not ported |

---

## 8. Open Questions

Anything marked `ASSUMED:` is a working assumption, not a confirmed fact. It must be confirmed before
anything load-bearing is built on it.

| ID | Question | Owner / when |
|---|---|---|
| Q-01 | RESOLVED 2026-10-06 by D-21: $5 per month to start | n/a |
| Q-02 | RESOLVED 2026-10-05 by D-17: exact numpy store in one `.npz` | n/a |
| Q-03 | RESOLVED 2026-10-05 by D-18: Python 3.13 | n/a |
| Q-04 | RESOLVED 2026-10-06 by D-22 | n/a |
| Q-05 | RESOLVED 2026-10-06 by D-21: v1's 20 questions and 16-paper manifest reused unchanged (q-single-01 is unanswerable from the corpus: open for Azim) | Azim, before the P1 benchmark |
| Q-06 | ASSUMED: the VerifiedLab tier targets STEM content in the user's corpus, with the physics contract covering the checkable subset | P4 plan |
| Q-07 | Where to deploy, if anywhere | Later (D-13) |
| Q-08 | RESOLVED 2026-10-05: Tailwind v4 and LangGraph 1.x were read from current docs (tasks 1 and 8); v1's usage differs and was not copied | n/a |

---

## 9. Glossary

| Term | Meaning |
|---|---|
| GraphRAG | Retrieval over a knowledge graph as well as flat chunks |
| RRF | Reciprocal rank fusion: combining ranked lists by rank, k = 60 |
| UIBlock | The typed unit on the wire: `{type, data, meta}` |
| LayoutSpec | Level 2 output: typed layout of components across panels |
| VerifiedLab | Level 3 output: a contract-checked, verifier-minted, sandboxed interactive artifact |
| Structural precondition | The relation a component's payload asserts among its evidence |
| Governed lifecycle | generated → verified → cached → audited → promoted, with eviction and staleness |
| Crystallisation | Turning a repeatedly promoted artifact pattern into a typed level 1 component |
| Engine | A trained, narrow model behind `predict()` / `is_available()`, additive to a heuristic |
| Super tools | Typed agent tools that do substantial work, not prompt wrappers |
| Provenance header | A comment at the top of a ported file naming its source repo, path and commit |
