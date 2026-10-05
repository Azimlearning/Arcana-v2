# Arcana v2: Build Status

> **Read this first to know where we are.** Updated at the end of every build session. Phases and scope come from `refdocs/arcana-v2-PRD.md` §6. Don't reorder phases without updating this file and saying why (CLAUDE.md "keep docs current").

**Build philosophy:** walking skeleton first. One PDF, one chunk, one embedding, one hybrid call, one `CitedSummary`, one streamed block, one rendered component, end to end, before building the second of anything. Evidence is measured, never asserted.

**Right now:** Nothing is built. This project was scaffolded on 2026-10-05: the docs, agent config, and the P0 plan exist; no code does. The next session starts at `refdocs/plans/2026-10-05-p0-walking-skeleton.md`.

---

## Phase checklist

| Phase | Scope | Status |
|---|---|---|
| P0 | Walking skeleton + eval harness | ⬜ Not started |
| P1 | Agent core with super tools; first full graph-vs-flat benchmark | ⬜ Not started |
| P2 | GenUI catalog (level 1) + adaptive dashboard (level 2 LayoutSpec) | ⬜ Not started |
| P3 | Trained tools: router distillation, Re-Rank, Mastery (optional) | ⬜ Not started |
| P4 | VerifiedLab (level 3) + governed lifecycle | ⬜ Not started |
| P5 | Learning/writing depth, final eval runs, report evidence | ⬜ Not started |

Status vocabulary: use these exactly, and never round up:
- ⬜ **Not started**
- 🔶 **In progress**: say precisely what works and what doesn't
- ✅ **Done**: built *and* verified. If it compiles but was never run, it is not done.
- ⛔ **Blocked**: name the blocker and who/what unblocks it

---

## P0: Walking skeleton + eval harness (current phase)

| Item | Approach | Status |
|---|---|---|
| Monorepo + toolchain | pnpm workspace (`web`, `packages/schema`) + uv project (`api`), Python version settled (Q-03) | ⬜ |
| Wire schema + codegen | `UIBlock` union with `CitedSummary` first; TS → Python codegen; drift check | ⬜ |
| Core + LLM seam | Settings, logging, error envelope, token budget, spend ledger; Anthropic primary, OpenRouter fallback | ⬜ |
| Stores | `GraphStore` (NetworkX on disk), `VectorStore` (local, spike Q-02), `DocStore` (SQLite) | ⬜ |
| Ingestion | PDF → chunks (1,200 / 200) → embeddings → schema-free extraction, one pass | ⬜ |
| Hybrid retrieval | Dense + BM25 + graph, RRF k = 60, per-signal toggles, approximate entity resolution | ⬜ |
| One agent → one block | Research agent → `CitedSummary` → validate (fail closed) → SSE | ⬜ |
| Web | Shell, stream consumer, registry, `CitedSummary` with four states | ⬜ |
| Eval harness | Question set + manifest (Q-05), gold-set format, five-arm runner, RAGAS smoke run | ⬜ |

---

## Verification ledger

What has actually been run, not what has been written. A row here needs a real command and a real result.

| Date | What was verified | How | Result |
|---|---|---|---|
| n/a | n/a | n/a | nothing verified yet |

---

## Known gaps

- No code, no tests, no manifests yet. Every command in `guides/checklist.md` is created in P0 task 1 and is not runnable before then.
- No file-structure doc: there is no tree to describe yet. Write one once P0 has produced the layout.
- Open questions Q-01 to Q-08 in the PRD; Q-01 (spend cap) blocks the first paid run.
- Evidence gaps inherited from v1 (founding context §5): no gold annotation, unrun extraction audit, unmeasured entity resolution, verbatim quote check missing.
