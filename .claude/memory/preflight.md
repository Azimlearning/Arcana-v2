# Preflight: Arcana v2 Session Start

> Read this at the start of every session, before touching code.
> One page, six questions, then you can build. CLAUDE.md is the reference; this is the gate.

---

## 1. Where are we?

Open `refdocs/STATUS.md`. Find the current phase and the one next action.
If STATUS's claims and the code disagree, **that's the session's first task**, not the thing you were about to do.

---

## 2. Which surface am I touching?

| Surface | Root | Shares source with |
|---|---|---|
| API | `api/` | `packages/schema` only (generated Python) |
| Web | `web/` | `packages/schema` only (TypeScript import) |
| Schema | `packages/schema` | Both, by codegen |
| Eval | `eval/` | Imports `api/` retrieval to run arms |
| v1 reference | `../Arcana/` | Nothing. Read-only. Never edit. |

`api/` and `web/` never import each other. If you are about to edit both in one session, the change almost certainly starts in `packages/schema`.

---

## 3. Does a plan exist for what I'm about to build?

Non-trivial feature → a plan doc in `refdocs/plans/` **and** an execution doc in `refdocs/execution/`.
If neither exists, write them first (`/plan-feature`). If one exists but reality has moved, update it before building on it.

---

## 4. Has this already been decided?

Skim `refdocs/changelog/DECISIONS.md` before re-opening an architectural choice. If your plan contradicts an ADR, you need a new ADR that says why, not a silent reversal.

Check the open `ASSUMED:` list at the bottom of that file. If today's work is load-bearing on one of them, **confirm it before you build**, not after.

---

## 5. If I changed what crosses the wire, did every side move with it?

A wire type (UIBlock variant, LayoutSpec, API payload, error envelope) changes in this order, every time:
1. `packages/schema` first,
2. `pnpm codegen`, then `pnpm codegen:check` passes,
3. the server validator handles it and fails closed,
4. a new block type gets a registry entry and a component with all four states,
5. a new component gets its structural precondition written down, and retrieval can satisfy it.

The first step compiles on its own, which is why this breaks silently. `pnpm codegen:check` (run by `test-runner`) and `schema-guardian` are the backstops. From P4 on, add one more check: does any new code path let a generated artifact reach the client without the verifier-minted type? If yes, stop.

---

## 6. Will I close the session properly?

`/session-end`: changelog entry, STATUS phase table, verification ledger, any new ADR.
The changelog entry is mandatory after any session that changed code, made a decision, or modified a plan. Even a one-line fix gets a one-line entry.

---

## Quick links

| Doc | Purpose |
|---|---|
| `refdocs/STATUS.md` | Where the build actually is |
| `CLAUDE.md` | Operating brief: rules, constraints, stack |
| `refdocs/arcana-v2-PRD.md` | Scope, architecture, roadmap, decision log |
| `refdocs/changelog/DECISIONS.md` | Settled calls; read before re-debating |
| `refdocs/context/2026-10-05-v2-direction.md` | What Azim decided, and when |
| `refdocs/guides/env_setup.md` | Every env var, where to get it |
| `refdocs/guides/checklist.md` | Pre-ship checklist |
| `refdocs/plans/` · `refdocs/execution/` | What/why · how/in what order |
