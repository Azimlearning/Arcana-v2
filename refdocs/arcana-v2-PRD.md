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
| Cost | Pay-per-use LLM APIs with a monthly cap (D-08) | Per-turn token budget, model tiers per task, caching. The cap value is open (Q-01). |
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
                         │  │ Tutor · Writer · Lab Builder         │ │
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

**Pillar 1: agents.** A small roster (D-05). ASSUMED (to be settled in the P1 plan): Orchestrator,
Research, Graph, Fact Checker, Composer, Tutor, Writer, Lab Builder. Agents share one state object,
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
| **P2** GenUI catalog + adaptive dashboard | Level 1 catalog (ported from v1 where suitable) with the bound applied per component; Composer; level 2 `LayoutSpec` | Every catalog component has its precondition documented and enforced; dashboard composes from LayoutSpec |
| **P3** Trained tools | `Engine` interface; distilled mode/intent router; Re-Rank; Mastery optional | Each engine evaluated against its heuristic; fallback verified |
| **P4** VerifiedLab + governed lifecycle | Contract, checker, generator, verifier, delivery gate, sandbox host; lifecycle states, eviction, staleness, crystallisation | No path to the client bypasses the verifier (test); mutation-suite detection rate recorded |
| **P5** Learning/writing depth + polish | Tutor and Writer depth, final eval runs, evidence for the report | Final benchmark, audit and mutation results committed |

---

## 7. Decision Log

Canonical one-line list. Load-bearing entries are expanded as ADRs in `changelog/DECISIONS.md`
under the same id.

| # | Decision | Why |
|---|---|---|
| D-01 | Ground-up rebuild; v1 is reference only; copied files carry provenance | Azim wants a fresh perspective; v1's shape was built for a different emphasis |
| D-02 | GraphRAG core; agentic AI and GenUI as the two pillars; trained models as tools | Azim's framing; matches the MCAIT paper's argument |
| D-03 | Stack: FastAPI + LangGraph (Python 3.12, uv), Next.js + React + Tailwind (pnpm), schema-first codegen, current versions | Same proven shape as v1 and Synapse, without starting dated |
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

---

## 8. Open Questions

Anything marked `ASSUMED:` is a working assumption, not a confirmed fact. It must be confirmed before
anything load-bearing is built on it.

| ID | Question | Owner / when |
|---|---|---|
| Q-01 | The monthly LLM spend cap, in USD | Azim, before the first paid run in P0 |
| Q-02 | ASSUMED: a local vector store exists that suits 3,072-dim vectors on Windows without a server. Which one? | P0 spike task |
| Q-03 | ASSUMED: Python 3.12 rather than 3.13 (v1 pinned `<3.13`; the reason was not recorded) | P0 task 1: check the dependency set on 3.13 |
| Q-04 | ASSUMED: the agent roster in §3.1 | P1 plan |
| Q-05 | ASSUMED: v2 reuses v1's 20 pre-registered questions and 16-paper corpus manifest for continuity | P0 eval task; confirm with Azim before gold annotation |
| Q-06 | ASSUMED: the VerifiedLab tier targets STEM content in the user's corpus, with the physics contract covering the checkable subset | P4 plan |
| Q-07 | Where to deploy, if anywhere | Later (D-13) |
| Q-08 | ASSUMED: Tailwind's current major version and the current LangGraph API are read from their docs at install, not recalled | P0 task 1 |

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
