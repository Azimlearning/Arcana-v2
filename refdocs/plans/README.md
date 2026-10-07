# Plans

> **MANDATORY:** Before implementing any non-trivial feature, a plan document must exist in this folder.
> A plan covers **what** and **why**: goal, scope, constraints, risks, definition of done.
> The **how** and **in what order** belongs in `refdocs/execution/`. When the two merge, both stop being read.

## Naming convention

`YYYY-MM-DD-<slug>.md`: the date the plan was written, then a short kebab-case slug.

**The execution doc uses the identical filename** in `refdocs/execution/`. Same date, same slug; that mirroring is how you find a plan's other half without opening anything. If a plan gets superseded, write a new one and mark the old row Superseded; don't rewrite history in place.

## Required sections in every plan

1. **Why this exists**: the problem, in the user's terms
2. **What's already covered**: what needs no work, so nobody rebuilds it (in v2 this includes what v1 or Synapse already has as reference)
3. **Scope**: what's in, and what's explicitly out *with reasons*
4. **Approach**: the shape of the solution
5. **Risks & unknowns**: with honest confidence levels. "I read this library's docs" and "I think this library does that" are different rows.
6. **Definition of done**: phrased as observable facts, not intentions

## Index

Add a row when you write a plan. Update the status when it moves; a stale index is how a project ends up with three plans for the same thing.

Status vocabulary: `Draft` · `In progress` · `Done` · `Blocked` · `Superseded` · `On hold`

| File | Description | Status |
|---|---|---|
| [2026-10-05-p0-walking-skeleton.md](2026-10-05-p0-walking-skeleton.md) | P0: walking skeleton + eval harness | In progress (closed with two deferrals, see STATUS) |
| [2026-10-06-p1-agent-core.md](2026-10-06-p1-agent-core.md) | P1: agent core with super tools + first full benchmark | Done 2026-10-06; one declared open item (RAGAS metrics deferred to the end); result inconclusive |
| [2026-10-07-g1-atomic-graph-experiment.md](2026-10-07-g1-atomic-graph-experiment.md) | G1: an atomic-note graph builder as a measured experiment (extra arms, protocol fixed first, free baseline, subset then full) | In progress (approved 2026-10-07, ADR D-34; G1.1 next) |
| [2026-10-07-p2c-traversal-view.md](2026-10-07-p2c-traversal-view.md) | P2c: `TraversalView`, what the search followed for each prompt (no ingestion or scoring change) | In progress (approved 2026-10-07, ADR D-33; T1 next) |
| [2026-10-07-p2b-studio-shell-split-regions.md](2026-10-07-p2b-studio-shell-split-regions.md) | P2b: layout v2 (regions inside panels), the Studio shell and the Outputs shelf (Azim's UI direction, 2026-10-07) | Done 2026-10-07 (ADR D-32; definition of done checked in the plan) |
| [2026-10-06-p2-genui-catalog-dashboard.md](2026-10-06-p2-genui-catalog-dashboard.md) | P2: GenUI catalog (level 1, evidence-admitted components) + adaptive dashboard (level 2 `LayoutSpec`) + first measurement of the bound | Done 2026-10-07 (ADRs D-27 to D-31; B5 stretch deferred; definition of done checked item by item in the plan) |
