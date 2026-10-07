# Plan: P2b Studio shell and split regions (layout v2)

> A follow-on to P2 (`2026-10-06-p2-genui-catalog-dashboard.md`), from Azim's comments on the D1 screenshots on 2026-10-07. Execution doc: `refdocs/execution/2026-10-07-p2b-studio-shell-split-regions.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.
> Status: **Done 2026-10-07** (built and checked; see the check under Definition of done). **Approved by Azim 2026-10-07** ("the layout change is correct for now", the Studio understood, "I approve this plan so far and you can proceed"). ADR D-32 accepted with it. 

## Why this exists

Azim, 2026-10-07, after seeing the P2 screenshots:

> "Based on v1, on the right side bottom under the knowledge graph will have the studio section for the slide generation, quiz generation, etc, and the outputs / gems of each of those studio functions will be available down below (my inspiration in v1 was NotebookLM). Also part of the adaptive UI, the middle section can develop split panes, vertically or horizontally, depending on the generation of the GenUI components, whether it is a quiz, a study session or anything."

Two things follow. First, the layout needs **regions inside a panel**, with a direction, so the right column can hold the graph above a Studio area and the middle column can split. That is a change to `LayoutSpec`, which D-27 made closed on panels and modes. It is cheaper to make now, while five components and one layout exist, than after P5 adds quiz and study components that need it. Second, v1's Studio is a **shell** (generators and an output shelf) whose generators are P5 work (the Studio agent, D-30). This phase builds the shell and the layout, not the generators.

## What's already covered (no work needed)

- `LayoutSpec` v1, the Composer's width rules, `validate_layout` on both sides, the layout event, the shell (`Shell`, `Panel`), `placeBlocks`, the saved-view flow (patterns), the fixture shared by both sides. All exist and are tested.
- Saved views are the first kind of "output": a saved pattern is a name, a template and parameters, with no evidence. They already have a store, a list endpoint, apply and re-verify.
- v1's Studio (`../Arcana/`) is reference only. Read its layout before building the shell here (CLAUDE.md rule 5 applies if anything is ported).

## What Synapse shows (read 2026-10-07, `Synapse-V3`, read only; nothing is ported)

Azim asked for a look at how Synapse handles adaptive UI and the choice between prebuilt and generated components. What is there, and what it means here:

- **Adaptive layout is a column template switched by state** (`frontend/app/page.tsx`: three grid templates for "no lab yet", "lab focused" and "both", with a CSS transition on `grid-template-columns`), and on narrow screens the lab pane becomes an open or closed overlay instead of a column. Arcana's `LayoutSpec` already makes the widths data; P2b adds regions. Two things to take: the **width change is animated**, and **narrow screens swap a column for an overlay**. The animation goes into task F3; the phone overlay stays out of scope (recorded as a gap).
- **Prebuilt first, generated only if nothing prebuilt fits.** `resolve_builtin_lab_for_query` picks a stored, content-hashed lab deterministically; only when none matches does the Planner, Generator and Verifier pipeline run. A prebuilt lab still passes a cheap `verify_trusted_builtin` hash check. This is the same order as D-28 and D-31 here (prebuilt Basic, admitted components, saved patterns, and generation only in P4), so no change to the design.
- **One delivery gate.** Only `delivery.py` may emit the artifact-done event, a source-scan test forbids constructing it elsewhere, a verified artifact needs a type only the verifier can mint, and an artifact that failed only on science grounds is delivered with `verified=False` and an honest note instead of a reward. This is the model for P4's gate and is already in constraint 3.
- **A saved library with a verified flag** (`labLibrary.ts`): saved labs carry `verified`, are capped in count and size and evicted from the tail. Arcana's saved patterns already have a state and a cap. **The shelf in this phase shows each item's state in words**, which makes the lifecycle visible instead of only stored (task F4).
- **A promotion ladder** (`generated, verified, cached, audited, canonical`) is Synapse's plan, which became D-11 and D-31 here. Nothing to add in P2b.

## Scope

**In:**

1. **Layout v2: regions.** A panel may be divided into regions with a direction (`rows` or `columns`) and sizes. Each region has a role id from a closed union (`main`, `secondary`, `shelf`). A placement names a panel and optionally a region (default: the panel's first region). `version` becomes 2; a v1 spec is still readable. The whole wire change follows preflight question 5, and `schema-guardian` reviews it.
2. **Composer rules for regions.** The catalog's placement hint gains an optional region. Generic rules, still with no component names: a panel with one occupied region is not split; a panel with two occupied regions splits in the direction the hint asks for; sizes come from a small table. No model call.
3. **The Studio shell.** The studio panel's basic layout becomes two regions in rows: the graph area (`main`) above the Studio area (`shelf`). The Studio area has two parts: a row of generator tiles (slides, quiz, and so on) that are shown **disabled with the words "Coming with the Studio agent"**, and an **Outputs shelf** that lists saved items. The first saved items are the saved views that today sit in the header; they move here.
4. **Split middle section.** The chat panel can hold `main` and `secondary` regions. No built component asks for `secondary` yet, so a toy component in tests proves the path, and the layout rules are documented for the P5 quiz and study components.
5. A real-browser run with screenshots, an independent review, and the usual docs.

**Out (by decision, stated so they are not built by accident):**

- The generators themselves (slides, quiz, flashcards, study sessions) and the Studio agent: P5 (D-30).
- Drag to resize panes, drag to rearrange, collapsing by the user, and remembering a layout between sessions.
- Any model-chosen layout (D-28 stands: deterministic).
- Phone and tablet layout. It is recorded as a gap in STATUS and is not solved here; the region direction is the thing that would let a later phase stack columns.
- `InsightCard` (B5).

## Approach

**Wire shape (proposal, to be confirmed in task F1 by a spike, not by memory):**

```ts
export type RegionId = "main" | "secondary" | "shelf";
export type SplitDirection = "rows" | "columns";
export interface RegionSpec { id: RegionId; /** @int */ size: number }   // percent of the panel, summing to 100
export interface PanelSpec { id: PanelId; /** @int */ width: number; direction: SplitDirection; regions: RegionSpec[] }
export interface Placement { blockId: string; panel: PanelId; region: RegionId; /** @int */ order: number }
```

Invariants added to `validate_layout`: every panel has at least one region; region ids unique within a panel; sizes whole numbers from 1 to 100 summing to 100; a placement's region exists in its panel; a hidden panel (width 0) has no placements; orders unique within a region. A v1 spec (no regions) is read as one `main` region per panel.

**Why regions with a closed id and not nested free-form splits.** An open tree of splits would let the server describe a layout the client cannot draw and would need a recursive validator. Three role ids and one level of split cover every layout Azim described and keep the validator flat, in line with the "closed unions on purpose" amendment to D-27. A new region role is a schema change, the same cost model as a new panel.

**Why saved views move to the shelf.** They are the only outputs that exist, so the shelf is real on day one and the move tests the shelf with real items. The generators are shown as unavailable instead of hidden, so the screen says honestly what is not built.

## Cost estimate

No paid call is added. The browser run reuses the real stores and the existing chat path: about 3 live turns at roughly $0.015 each, under $0.05 in total. Ledger remains at about $6.2 of the $10 cap.

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| A second breaking wire change to `LayoutSpec` | Medium: validator, builders, fixture, client check and tests all change | One schema-first task (F1); a v1 spec stays readable so a saved or cached layout never breaks; `schema-guardian` reviews |
| The right column becomes crowded (graph, generators, shelf) at 1440 px | Medium: P2 already found the dashboard cramped | Sizes are data and tuned in the browser run; the generators are one compact row; stated as a limit if not solved |
| Disabled generator tiles read as a broken feature | Low | The tiles carry the words "Coming with the Studio agent" and are not focusable as buttons |
| The shelf invites generators before the Studio agent exists | Low | Out of scope is written above; no tile has behaviour |
| Azim's intent differs (for example the Studio as a tab, not an area) | Medium | This plan is a proposal; nothing is built before approval |

## Definition of done

- [x] `packages/schema` defines `RegionId`, `SplitDirection`, `RegionSpec` and the extended `PanelSpec` and `Placement`; `pnpm codegen:check` exits 0; a v1 layout still validates on both sides.
- [x] `validate_layout` and `web/lib/layout.ts` enforce the same region rules, with tests for each invariant and a shared fixture.
- [x] A toy component that asks for `chat.secondary` is split, validated and rendered with no change to the layout module (a test), and the layout guide describes the rule.
- [x] The prebuilt Basic layout has the graph area above a Studio area with disabled generator tiles and an Outputs shelf; saved views appear on the shelf and no longer in the header (component tests and a browser capture).
- [x] No generator has behaviour, and no paid call or model call was added (a test and the ledger).
- [x] In a real browser on the real stores: the Basic and Adaptive layouts, a saved view applied from the shelf, and the studio column with a real graph above the Studio area; screenshots committed, with the 1440 px crowding stated as measured.
- [x] `schema-guardian` has reviewed the wire change, `test-runner` is green on the full suite, and STATUS, CHANGELOG, ADR D-32, the file structure guide and the indexes are current.

### Check against the build (2026-10-07, P2b F5)

1. Schema types and codegen, v1 still valid on both sides: **met** (`pnpm codegen:check` OK; `layout-v1.json` is read by one server and one web test).
2. Server and client enforce the same region rules, with a shared fixture: **met**. One stated difference: the client ignores unknown extra keys and accepts `20.0` as a whole number where the server's strict models refuse them (server output never has either).
3. A toy component asking for `chat.secondary` is split with no change to the layout module: **met** (tests; an exhaustive test over every panel, region and direction a hint can name gives a layout the validator accepts).
4. The prebuilt Basic layout has the graph area above the Studio area (inert generator tiles and an Outputs shelf), with saved views on the shelf and not in the header: **met** (component tests; browser captures 01, 03, 05). The graph area in Basic is a sentence, so the fixed layout is 25 and 75 rather than the 60 and 40 of Adaptive.
5. No generator has behaviour; no model or paid call was added: **met** (a test that the Studio renders nothing focusable and calls nothing; the cost audit found no change under `api/llm`, `api/retrieval`, `api/ingestion` and the ledger unchanged at 1759 rows, $6.172354).
6. A real browser at 1440 by 900: **met for Basic, Adaptive, a saved view applied from the shelf after a reload, and the graph above the Studio area** (captures 01 to 05; fake model on two real papers, so no paid call). **Not shown:** the real model and the 16-paper store (not needed for a layout change), and any use of `secondary` in a real turn (no built component asks for it). **The 1440 px crowding, measured:** the Adaptive graph area at 60 percent of the column height cuts off the graph's details box (it scrolls within its region) and the shelf at 40 percent just fits one saved view, then scrolls. **Phone width (400 px) is unusable** (capture 06: panels squeezed to a few characters). The `flex-grow` transition was measured: a panel went 482, 480, 424, 311, 275 px at 0, 0, 60, 150 and 400 ms, so the browser interpolates it.
7. Reviews: **met.** `schema-guardian` found no blocking item in F1 or in the whole; its non-blocking items were fixed with tests (a block in a region the screen gives no content is still drawn; the region lists are exhaustive; the chat panel must have a `main` region) or recorded. `cost-auditor`: no paid call, ledger unchanged. Full suite: `uv run pytest` 793 passed twice (then 795 after the last fixes, run once), web 223 passed, ruff, pyright, typecheck, lint, codegen check, and `pnpm --filter web build` clean.

**Not done in P2b, by decision:** the generators and the Studio agent (P5); resizing and rearranging by the user; remembering a layout; phone and tablet layout.
