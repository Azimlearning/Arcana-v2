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
| [2026-10-05-p0-walking-skeleton.md](2026-10-05-p0-walking-skeleton.md) | P0: walking skeleton + eval harness | Draft |
