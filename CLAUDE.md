# Arcana v2: Claude Context

> Read this file at the start of every session, then run through `.claude/memory/preflight.md`; it's the six-question gate that turns these rules into something you actually did. Arcana v2 is a graph-grounded learning workspace: GraphRAG is the core, agentic AI and generative UI are the pillars, trained models are tools.
> The PRD is the source of truth; this file is the short operating brief; preflight is the gate. Keep all three short.

---

## Order of authority (when docs conflict, surface it; don't resolve silently)

0. `refdocs/STATUS.md`: **where we are right now.** Phase checklist + the current phase's progress. Check this first, every session.
1. `refdocs/arcana-v2-PRD.md`: **what & why.** Owns scope, architecture, roadmap, Decision Log.
2. `refdocs/changelog/DECISIONS.md`: **settled calls.** Read before re-debating an architectural choice.
3. `refdocs/plans/*.md`: **what to build & why.**
4. `refdocs/execution/*.md`: **how & in what order.**
5. `refdocs/guides/`: **operational reference.** `env_setup.md` (every variable, where to get it), `checklist.md` (pre-ship).
6. `refdocs/arcana-v2-sources.md` and `refdocs/context/`: **raw research and the founding direction.**

If two docs disagree, stop and ask. Don't pick one and move on.

**Arcana v1** (`../Arcana/`, repo `Azimlearning/Arcana`, tag `v1.0`) is reference only: read it, never edit it, never treat its docs as authority for v2.

---

## Mandatory rules

### 1. Update the changelog after every session
After any session that changed code, made a decision, or modified a plan, add an entry to **`refdocs/changelog/CHANGELOG.md`** (format is in that file). Do not skip. Even a one-line fix gets a one-line entry.

### 2. Plan before you build
Before implementing any non-trivial feature, a **plan doc** (`refdocs/plans/`) and an **execution doc** (`refdocs/execution/`) must exist. If they don't, create them before writing code.

### 3. Log decisions as ADRs
New architectural/design decision → add an ADR to `refdocs/changelog/DECISIONS.md` (Decision → Why → Rejected/Trade-off). Mark unresolved assumptions `ASSUMED:` and surface them at the next checkpoint.

### 4. Keep docs current
If you deviate from a plan during execution, update the execution doc to match reality. Stale docs are worse than no docs.

### 5. Port with provenance
A file copied or adapted from v1 or Synapse starts with a comment naming the source repo, path and commit. Read it fully and adapt it to v2's interfaces; never paste and patch until it compiles (D-01, D-16).

### 6. Read current docs before using a library
Next.js, React, Tailwind, LangGraph, RAGAS, and the provider SDKs have all changed since v1. Read their current docs (context7 or official) before writing against them. Do not encode an API recalled from memory or copied from v1.

### 7. Writing style
No em dashes in docs or user-facing text: use commas, colons, or new sentences.

---

## The hard constraints (these are mechanism, not preference)

1. **Ground before generating.** No synthesis without hybrid retrieval evidence first; every user-facing claim carries a traceable citation.
2. **The wire carries data only.** Every type that crosses the wire is defined once in `packages/schema` and generated into Python. Every block is validated server-side before streaming and fails closed. The client renders only through the registry.
3. **Generated code only through the gate (P4).** A level 3 artifact reaches the client only as a type the verifier alone can mint; it renders in an iframe with `sandbox="allow-scripts"` only, never `allow-same-origin`; its libraries come from the local vendor directory, never a runtime CDN.
4. **Only the Composer chooses components and layout.** Every turn terminates at the Composer, even on failure or budget exhaustion.
5. **Agents compose only through `route_to_agent`,** within hop and token budgets. An agent never imports another agent.
6. **Storage and trained tools sit behind abstractions.** Code calls `GraphStore` / `VectorStore` / `DocStore` / `Engine`, never a concrete backend. Every engine is additive: absent or failing, the heuristic runs.
7. **Components join on evidence.** A new catalog component needs a written structural precondition that retrieval can satisfy; generated patterns enter the vocabulary only through the governed lifecycle.
8. **Spend is capped.** Every paid call goes through the LLM seam or the embeddings client, is written to the spend ledger, and is refused before sending if it would exceed `LLM_MONTHLY_CAP_USD`. No secret literals anywhere; this repo is public.
9. **Evaluation protocol is fixed before runs.** The question set and corpus manifest change only by declared amendment; gold annotations are written before arms are run; model-judged scores are never the primary metric.

---

## Stack

- **Backend (`api/`):** Python (3.12 or 3.13, settled in P0, Q-03), FastAPI, LangGraph, Pydantic, SQLAlchemy over SQLite, NetworkX, BM25, a local vector store (Q-02), managed with **uv**.
- **Frontend (`web/`):** Next.js, React, Tailwind, Zustand, Vitest, managed with **pnpm** (9.12). Current versions, set in P0.
- **Schema (`packages/schema`):** TypeScript source of truth; codegen to Pydantic.
- **LLM:** Anthropic API primary, OpenRouter fallback, model tiers per task. **Embeddings:** OpenAI `text-embedding-3-large` (3,072-dim).
- **Eval (`eval/`):** Python, RAGAS as a library.

## Surfaces

One product, two deployables that share source **only** through `packages/schema`:

| Surface | Root | Run | Can | Cannot |
|---|---|---|---|---|
| API | `api/` | `uv run uvicorn api.main:app --reload` | Retrieval, agents, validation, streaming, storage, spend | Render UI |
| Web | `web/` | `pnpm --filter web dev` | Render blocks via the registry, host the sandbox | Hold secrets, reason, or call an LLM |
| Schema | `packages/schema` | `pnpm codegen` | Define wire types | Contain logic |

`api/` and `web/` never import each other. A change to a wire type starts in `packages/schema`, then flows to both sides by codegen and type import.

## Running it

| What | Command | Notes |
|---|---|---|
| Install | `uv sync` and `pnpm install` | Created in P0 task 1 |
| API | `uv run uvicorn api.main:app --reload` | Fakes by default (`ARCANA_LLM_MODE=fake`) |
| Web | `pnpm --filter web dev` | Reads `NEXT_PUBLIC_API_BASE_URL` |
| Codegen | `pnpm codegen` / `pnpm codegen:check` | Run after any schema change |
| Tests | `uv run pytest` and `pnpm -r test` | |
| Lint/types | `uv run ruff check api`, `uv run pyright api`, `pnpm -r lint`, `pnpm -r typecheck` | |
| Eval | `uv run python eval/run_ablation.py` | Costs money in live mode |

None of these exist until P0 task 1 creates them.

---

## Build sequence

- **P0** walking skeleton + eval harness → **P1** agent core with super tools (+ first full graph-vs-flat benchmark) → **P2** GenUI catalog + adaptive dashboard (LayoutSpec) → **P3** trained tools → **P4** VerifiedLab + governed lifecycle → **P5** learning/writing depth + final evidence. Details: PRD §6.

**Never build the second of anything until the first is green end-to-end.**

---

## Subagents

- `doc-keeper`: end of every session; changelog, STATUS, ADRs, index tables.
- `test-runner`: before claiming anything works; reports failures verbatim.
- `schema-guardian`: before shipping any wire change; schema-first, codegen fresh, registry complete, fail-closed validation, the bound documented.
- `retrieval-auditor`: before relying on a retrieval change or running the benchmark; fusion correctness, signal toggles, protocol fairness.
- `cost-auditor`: when adding or changing a paid call, or before an eval run.

---

## When blocked

- **Open question:** check the PRD's Open Questions section. If unresolved, write your assumption to `DECISIONS.md` as `ASSUMED:`, proceed, surface at the next checkpoint.
- **Doc conflict:** stop. Quote both passages and ask. Don't pick silently.
- **Ambiguous spec:** prefer the safer, less-coupled option. Log the choice.

---

*Companion brief to `refdocs/arcana-v2-PRD.md`. Last updated: 2026-10-05.*
