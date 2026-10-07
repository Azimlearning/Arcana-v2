# Execution: M2.11 the vault review screen

> Plan: `refdocs/plans/2026-10-07-m2-lint-screen.md`. Tasks run in order. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Done (2026-10-07). Free: no paid step.**

## Before starting

- Read `CLAUDE.md`, `api/vault/lint.py`, `GET /vault/lint` in `api/routes/vault.py`, the lint types in `packages/schema/src/api.ts`, `web/app/notes/NotesWorkspace.tsx`, `web/lib/api.ts`.
- No wire change: the types already exist. Only the web changes.

### Task L1: the client and the screen

**Files:** `web/lib/api.ts` (`fetchLint`), `web/app/notes/review/{page,ReviewScreen}.tsx`, `web/app/notes/NotesWorkspace.tsx` (a "Review" link), tests.
1. `fetchLint(options)` returns `{ok:true, report}` or `{ok:false, error}`; a body that does not have the report's shape is an error.
2. `ReviewScreen`: loading, error, empty (`pages` is 0), ready; four sections with headings, exact totals, a "N more not shown" line when the total exceeds the list.
3. A "Review" link in the notes header and a "Notes" link back.

**Verify:** component tests for the four states and the four lists (reasons in words, definitions as text, totals beyond the list), a client test (URL, error, malformed body), `pnpm --filter web test`, typecheck and lint.

### Task L2: a real-browser look and close

Run the API on a copy of the `atomic2` vault and open `/notes/review`; screenshot; fix what the browser shows; docs (changelog, STATUS, file map, indexes); commit locally.

## Reality

- **L1.** `fetchLint` in `web/lib/api.ts` (a body that lacks the report's shape is an error); `/notes/review` (`ReviewScreen.tsx`): loading, error, no-pages and ready states, four sections with exact totals and "N more are not shown (the list stops at 50)"; a "Review" link in the notes header and links back. No wire change and no server change. 10 screen tests and 2 client tests; web suite 343 passed, typecheck and lint clean.
- **L2.** Seen in a real browser on a copy of the `atomic2` vault (1,245 pages): 98 near-duplicate pairs (48 not shown), 6 concepts several papers define, 301 pages no link reaches (251 not shown), 5 pages named almost everywhere. `refdocs/evidence/m2-11-review.png`.
- **Noted, not changed:** the `one_more_word` reason is noisy on real data: most of the pairs shown are specialisations ("legal large language model" next to "large language models"), not duplicates. The screen says "may" and "only a person can say"; tightening the lint rule would be a change to M2.8's reported rule and is left to Azim's reading of the list. Opening a page from the report is out of scope (the notes screen keeps its page in state, not in the address).
