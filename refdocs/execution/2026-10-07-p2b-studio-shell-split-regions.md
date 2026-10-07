# Execution: P2b Studio shell and split regions (layout v2)

> Plan: `refdocs/plans/2026-10-07-p2b-studio-shell-split-regions.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07; ADR D-32 accepted.** Task F1 is next.

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, read `refdocs/STATUS.md`, and read `refdocs/guides/catalog.md` (layout section) and D-27 as amended on 2026-10-07.
- Fakes first. Tasks F1 to F4 need no keys. Task F5 uses the real stores read-only and about $0.05 of real calls.
- **The wire change follows preflight question 5, in order:** schema first, `pnpm codegen` then `pnpm codegen:check`, the server validator, the web registry and layout check, a fixture shared by both sides.
- Do not touch retrieval, the protocol stamp, the frozen assets or the ingested stores; `uv run pytest eval/tests/test_frozen_assets.py` runs in every verify.
- Read the current Tailwind v4 and React docs (context7) before writing layout CSS; do not recall them from memory (CLAUDE.md rule 6).
- No paid call and no model call is added.

---

### Task F1: Layout v2 on the wire (schema first)

**Files:** `packages/schema/src/layout.ts`, `api/genui/generated.py` (generated), `api/genui/validate.py`, `api/genui/layout.py`, `packages/schema/fixtures/` (new v2 fixture, v1 kept), `web/lib/layout.ts`, tests on both sides.

1. Read v1's `Shell.tsx` and the current `Shell.tsx`/`Panel.tsx` first. Spike the proposed shapes in the plan in a scratch copy of the schema package to confirm codegen supports them (nested arrays of records, a closed string union as a field), as was done in P2 task A1.
2. Write the types in `layout.ts`; `pnpm codegen`; `pnpm codegen:check`.
3. Extend `validate_layout` with the region rules from the plan, and read a v1 spec (no regions) as one `main` region per panel. Make `known_block_ids` required, which also closes a P2 review note.
4. Mirror the rules in `isLayoutSpec`, using `Record`s keyed by the schema unions as in P2 D3.
5. A shared fixture is read by one server test and one web test, as the prebuilt fixture is.

**Verify:** `uv run pytest api -q` and `pnpm --filter web test` pass with tests for: each new invariant refused (missing regions, duplicate region ids, sizes not summing to 100, a placement into a region the panel lacks, a hidden panel with placements, duplicate orders within a region); a v1 layout still accepted by both sides; the fixture agreeing on both sides.

### Task F2: Composer rules and the catalog hint

**Files:** `api/genui/catalog.py` (`PlacementHint` gains an optional region), `api/genui/layout.py`, `refdocs/guides/catalog.md`.

1. The hint says panel, optional region and priority. The five built components keep their current panels and use `main`, except none asks for `shelf` or `secondary`.
2. `prebuilt_layout` returns the studio panel as two rows (graph `main`, Studio `shelf`) with sizes from a documented table; the chat panel is one region.
3. `compose_layout` splits a panel only when two regions are occupied, in the direction the table gives for that panel, and hides nothing it did not before. A toy component in a test asks for `chat.secondary`.
4. Document the rule in `catalog.md` ("Layout defaults and placement hints") including the new sizes.

**Verify:** layout tests: sizes sum to 100 for every mode; an unoccupied region is dropped and its size goes to the panel's `main`; the toy component is split with no edit to `layout.py` (a source-scan test as in P2); the Composer still makes no provider call.

### Task F3: The shell draws regions

**Files:** `web/components/shell/Panel.tsx`, `Shell.tsx`, `web/lib/layout.ts` (`placeBlocks` returns blocks by panel and region), tests.

1. `Panel` renders its regions in the panel's direction using flex-grow from the sizes, each region a labelled landmark where it holds content; a region of one block needs no wrapper.
2. `placeBlocks` groups by panel and region; a placement whose region is missing falls back to the panel's first region.
3. Keep the fallback layout in step with the fixture.
4. The change of widths and sizes is animated with a CSS transition on flex-grow (as Synapse does on its grid columns), and the transition is switched off under `prefers-reduced-motion`. Read the current Tailwind v4 docs for the transition utilities first.

**Verify:** component tests for rows and columns, for a region that is empty, and for a v1 layout; keyboard order follows reading order; the long-title and hidden-text containment tests from D1 still pass.

### Task F4: The Studio area and the shelf

**Files:** `web/components/shell/Studio.tsx` (new), `SavedViews.tsx` (moves into the shelf), `Workspace.tsx`, tests.

1. A row of generator tiles (slides, quiz, flashcards, study session) shown disabled, each with the words "Coming with the Studio agent". They are not buttons and have no handler.
2. The Outputs shelf lists the saved views with the same actions as today (show, check again, delete) and the same refusal words. Remove the control from the header.
3. An empty shelf says what will appear there.
4. Each shelf item states its lifecycle state in words (saved, verified, or stale with its reason), so the state the store already keeps is visible. Nothing else about the state machine changes (P4).

**Verify:** tests that the tiles are inert and labelled, that the shelf shows saved views and applies one, that the header no longer carries the control, and that a refusal is still said in words.

### Task F5: A real browser, review and wrap-up

1. Playwright at 1440 by 900 on the real stores: Basic, Adaptive, a saved view applied from the shelf, the right column with a real graph above the Studio area. Save screenshots to `refdocs/evidence/p2b-*.png`. State what the crowding looks like at this width as measured.
2. Run `schema-guardian` on the wire change, `test-runner` on the full suite twice (`uv run pytest`, ruff, pyright, `pnpm codegen:check`, `pnpm -r typecheck`, `pnpm -r lint`, `pnpm -r test`, `pnpm --filter web build`), and `cost-auditor` read-only to confirm no paid call was added. Fix any blocking finding with a test.
3. Update STATUS, CHANGELOG, DECISIONS (D-32 accepted, with amendments), the PRD §7 row, `file_structure.md`, `catalog.md`, both indexes, the plan's definition of done item by item. Run `/session-end`.

**Verify:** every box in the plan's definition of done is ticked with a note or marked partly met or unmet; `git status` clean after the commit; nothing pushed.

---

## Task order at a glance

`F1` layout v2 on the wire → `F2` Composer rules and the catalog hint → `F3` the shell draws regions → `F4` the Studio area and the shelf → `F5` browser, reviews, wrap-up.
