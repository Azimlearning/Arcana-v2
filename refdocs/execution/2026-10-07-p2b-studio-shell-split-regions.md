# Execution: P2b Studio shell and split regions (layout v2)

> Plan: `refdocs/plans/2026-10-07-p2b-studio-shell-split-regions.md`. Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Done 2026-10-07** (F1 to F5). Approved by Azim 2026-10-07; ADR D-32 accepted.

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

**Reality (F1 done 2026-10-07):** Schema first: `RegionId` (`main`, `secondary`, `shelf`), `SplitDirection` (`rows`, `columns`), `RegionSpec {id, size}`, `PanelSpec.direction` and `.regions`, `Placement.region`, all required on the wire; `pnpm codegen` and `codegen:check` OK; layout version is 2. The spike was skipped: codegen already handled nested arrays of records and closed string unions (`PanelSpec`, `PatternParam`), so nothing new was needed. `validate_layout` now takes `known_block_ids` as a required argument (it was optional: closes a P2 review note) and enforces the region rules; a version 1 mapping goes through `upgrade_layout` first (one `main` region per panel, direction `rows`; a boolean is not version 1). A region size is 0 to 100 (not 1 to 100 as the plan sketched) so that an unused region keeps no space but still exists, which F2 needs when a panel's graph area is empty and the shelf fills it; a region of size 0 holds no placements, as a panel of width 0 does. The client mirrors every rule (`isLayoutSpec`, plus `readLayout` which upgrades version 1; `stream.ts` and `api.ts` read layouts through it). Two shared fixtures: `prebuilt-layout.json` (now version 2) and `layout-v1.json`, each read by one server and one web test. `layout.py` emits a single `main` region per panel until F2. Review (`schema-guardian`, run read-only): no blocking finding; fixed the boolean-version difference, the `MAIN` typing and the stale `catalog.md` paragraph; one known difference left: the client ignores unknown extra keys where the server refuses them (it only reads server output; it existed before F1). Verified: `uv run pytest` 788 passed, web 205 passed, ruff, pyright, typecheck, lint, codegen check clean.

### Task F2: Composer rules and the catalog hint

**Files:** `api/genui/catalog.py` (`PlacementHint` gains an optional region), `api/genui/layout.py`, `refdocs/guides/catalog.md`.

1. The hint says panel, optional region and priority. The five built components keep their current panels and use `main`, except none asks for `shelf` or `secondary`.
2. `prebuilt_layout` returns the studio panel as two rows (graph `main`, Studio `shelf`) with sizes from a documented table; the chat panel is one region.
3. `compose_layout` splits a panel only when two regions are occupied, in the direction the table gives for that panel, and hides nothing it did not before. A toy component in a test asks for `chat.secondary`.
4. Document the rule in `catalog.md` ("Layout defaults and placement hints") including the new sizes.

**Verify:** layout tests: sizes sum to 100 for every mode; an unoccupied region is dropped and its size goes to the panel's `main`; the toy component is split with no edit to `layout.py` (a source-scan test as in P2); the Composer still makes no provider call.

**Reality (F2 done 2026-10-07):** `PlacementHint` gained `region` (default `main`) and `direction` (default none). `layout.py` now builds each panel from the regions that hold a placement plus the ones the panel always keeps (`ALWAYS`: the studio keeps `shelf`), with fixed weights (main 3, secondary 2, shelf 2, largest-remainder rounding so sizes are whole numbers summing to 100) and a direction from the highest-priority hint that names one, else a per-panel default (chat `columns`, others `rows`). **Decisions the build made:** (1) the studio panel is never hidden in Adaptive: with no graph it keeps a 20 percent column holding only the shelf (`KEPT_WIDTH`), because saved views move to the shelf in F4 and hiding it would make them unreachable; so "answer only" is now 0, 80, 20 instead of 0, 100, 0, and an unused region is not emitted (the wire still allows size 0). (2) The prebuilt layout's studio started as main 60 and shelf 40 with no placement in main; the browser showed that as a large empty block, so it is main 25 and shelf 75 (corrected in F5). (3) The plan said the hint asks for the direction; a conflict rule was needed, so the highest-priority hint that names one decides, and the table default applies when none does. A toy component asking for `chat.secondary` is split with no edit to `layout.py`; `layout.py` still names no component (source-scan test). The shared fixture `prebuilt-layout.json` was regenerated and the web fallback layout matches it; the version 1 reading is unchanged (one `main` region per panel). Verified: `uv run pytest` 792 passed; web 205 passed; ruff, pyright, typecheck, lint, codegen check clean.

### Task F3: The shell draws regions

**Files:** `web/components/shell/Panel.tsx`, `Shell.tsx`, `web/lib/layout.ts` (`placeBlocks` returns blocks by panel and region), tests.

1. `Panel` renders its regions in the panel's direction using flex-grow from the sizes, each region a labelled landmark where it holds content; a region of one block needs no wrapper.
2. `placeBlocks` groups by panel and region; a placement whose region is missing falls back to the panel's first region.
3. Keep the fallback layout in step with the fixture.
4. The change of widths and sizes is animated with a CSS transition on flex-grow (as Synapse does on its grid columns), and the transition is switched off under `prefers-reduced-motion`. Read the current Tailwind v4 docs for the transition utilities first.

**Verify:** component tests for rows and columns, for a region that is empty, and for a v1 layout; keyboard order follows reading order; the long-title and hidden-text containment tests from D1 still pass.

**Reality (F3 done 2026-10-07):** Tailwind v4 docs read first (`transition-[flex-grow]`, `motion-reduce:transition-none`; the old note in `Shell.tsx` saying `flex-grow` cannot be animated was wrong in principle and is replaced by a check in the real browser in F5). `Panel` now takes the panel's spec and a map of region content: it is a flex container (`flex-col` for rows, `flex-row` for columns) whose regions each take their size as a flex-grow value, are `relative` and scroll on their own, and carry the D1 containment classes; a region is a labelled landmark ("Main area", "Side area", "Outputs") only when its panel has more than one; a region of size 0 is `aria-hidden` and `inert`; a listed region with no content is drawn empty and one the layout leaves out is not drawn. `placeBlocksByRegion` groups blocks by panel and region (a placement into a region the panel lacks goes to the panel's first region; unplaced blocks go to chat's main); `placeBlocks` is kept as the by-panel view for the code that does not care (`flattenPlaced`). `Workspace` gives chat a `main` and a `secondary` and the studio a `main` (the graph or, empty, a sentence about where graphs show) and a `shelf` (blocks placed there; the saved views arrive in F4). Verified: web 214 passed, typecheck and lint clean.

### Task F4: The Studio area and the shelf

**Files:** `web/components/shell/Studio.tsx` (new), `SavedViews.tsx` (moves into the shelf), `Workspace.tsx`, tests.

1. A row of generator tiles (slides, quiz, flashcards, study session) shown disabled, each with the words "Coming with the Studio agent". They are not buttons and have no handler.
2. The Outputs shelf lists the saved views with the same actions as today (show, check again, delete) and the same refusal words. Remove the control from the header.
3. An empty shelf says what will appear there.
4. Each shelf item states its lifecycle state in words (saved, verified, or stale with its reason), so the state the store already keeps is visible. Nothing else about the state machine changes (P4).

**Verify:** tests that the tiles are inert and labelled, that the shelf shows saved views and applies one, that the header no longer carries the control, and that a refusal is still said in words.

**Reality (F4 done 2026-10-07):** New `Studio.tsx`: a labelled list of four generators (Slides, Quiz, Flashcards, Study session), each a plain list item that says "Coming with the Studio agent", with no button, link, handler or request (a test asserts it renders nothing focusable and calls nothing; `aria-disabled` is not valid on a list item, so the words carry the meaning). `SavedViews` is no longer a header dropdown: it is an always-visible section of the shelf (the `<details>` is gone, so nothing needs opening), and each item states its kind, its state in words (typed `Record<PatternState, string>`: Saved, Checked again, Made not yet checked; "Needs checking" for the view whose layout moved on) and how often it was shown. `Workspace` puts `Studio`, `SavedViews` and any block the layout places in `shelf` into the studio's shelf region and keeps only the layout switch in the header. **Decision the build made:** if a layout has no shelf region (a version 1 layout, or an older server), the shelf content is shown after the graph area instead of vanishing, so saved views stay reachable (a test). A layout that hides the whole studio panel (width 0) still hides it; the Composer never does that. Wording change: SaveView now says "You will find it on the Studio shelf, under Saved views." Verified: web 222 passed, typecheck and lint clean, `pnpm --filter web build` exit 0.

### Task F5: A real browser, review and wrap-up

1. Playwright at 1440 by 900 on the real stores: Basic, Adaptive, a saved view applied from the shelf, the right column with a real graph above the Studio area. Save screenshots to `refdocs/evidence/p2b-*.png`. State what the crowding looks like at this width as measured.
2. Run `schema-guardian` on the wire change, `test-runner` on the full suite twice (`uv run pytest`, ruff, pyright, `pnpm codegen:check`, `pnpm -r typecheck`, `pnpm -r lint`, `pnpm -r test`, `pnpm --filter web build`), and `cost-auditor` read-only to confirm no paid call was added. Fix any blocking finding with a test.
3. Update STATUS, CHANGELOG, DECISIONS (D-32 accepted, with amendments), the PRD §7 row, `file_structure.md`, `catalog.md`, both indexes, the plan's definition of done item by item. Run `/session-end`.

**Verify:** every box in the plan's definition of done is ticked with a note or marked partly met or unmet; `git status` clean after the commit; nothing pushed.

**Reality (F5 done 2026-10-07):** Browser run at 1440 by 900 with the API in fake mode on a scratch data directory outside the repo (two real papers uploaded through the page; no paid call) and the web dev server; six captures in `refdocs/evidence/p2b-*.png` (01 Basic before any question, 02 Adaptive on a comparison question, 03 Basic with the answer stacked, 04 a saved view applied from the shelf after a reload, 05 Basic with a saved view on the shelf, 06 the same at 400 px). The browser tool started without trouble. **What it showed:** the shape Azim described works (graph above, Studio below it in the right column); the `flex-grow` transition is interpolated (measured, see the plan); the Basic graph area was a large empty block at 60 percent, so the fixed layout's studio is now 25 and 75; a view saved from the graph appeared on the shelf as "Connection graph, Saved, shown once" and applied from there after a reload with no model call; no console errors; at 400 px the layout is unusable (a known gap, not in this phase). **Reviews:** `schema-guardian` and `cost-auditor` ran as their named agent types this time. Fixes with tests from the review: a validated placement into a region the screen gives no content is still drawn (`Workspace` fills it generically); `REGION_ORDER` (web) and the weights table (server) are checked against the schema's list; the chat panel must have a `main` region on both sides. **Verified:** `uv run pytest` 793 passed twice before the last review fixes; after them `uv run pytest` 795 passed (one run), web 223 passed, `pnpm --filter web build` exit 0, frozen assets 7 passed; ruff, pyright, typecheck, lint, codegen check clean.

---

## Task order at a glance

`F1` layout v2 on the wire → `F2` Composer rules and the catalog hint → `F3` the shell draws regions → `F4` the Studio area and the shelf → `F5` browser, reviews, wrap-up.
