# Execution Plans

> **MANDATORY:** Every plan in `refdocs/plans/` that moves to implementation must have a matching execution document here.
> An execution plan covers **how** and **in what order**: ordered tasks, file paths, commands, and a Verify step per task.
> Do not start coding a feature that has no execution doc. Write one first.

## Naming convention

`YYYY-MM-DD-<slug>.md`: **identical filename to its companion plan** in `refdocs/plans/`. Same date, same slug.

## Required sections in every execution plan

1. **Companion plan**: link to the plan doc, at the top
2. **Before starting**: preconditions, env vars, what must already be green
3. **Tasks**: ordered and self-contained, each with:
   - the files it creates or modifies
   - the exact steps or commands
   - a **Verify** step: a real command and its expected result
4. **Wrap-up**: the STATUS / changelog / ADR checklist

**A task is done when its Verify passes**, not when the code compiles. That distinction is the entire value of this folder.

## Keeping these honest

If reality diverges from the doc mid-build, **edit the doc** and note it in the changelog's Deviations line. A plan that changed silently is a plan nobody trusts next time. Stale docs are worse than no docs.

## Index

| File | Companion plan | Status |
|---|---|---|
| [2026-10-05-p0-walking-skeleton.md](2026-10-05-p0-walking-skeleton.md) | [../plans/2026-10-05-p0-walking-skeleton.md](../plans/2026-10-05-p0-walking-skeleton.md) | Closed with deferrals (tasks 1 to 9 and 11 done on fakes; task 10 and the RAGAS install deferred to P1 task B2) |
| [2026-10-06-p1-agent-core.md](2026-10-06-p1-agent-core.md) | [../plans/2026-10-06-p1-agent-core.md](../plans/2026-10-06-p1-agent-core.md) | Done 2026-10-06 (A1 to A9 and B1 to B6) |
| [2026-10-06-p2-genui-catalog-dashboard.md](2026-10-06-p2-genui-catalog-dashboard.md) | [../plans/2026-10-06-p2-genui-catalog-dashboard.md](../plans/2026-10-06-p2-genui-catalog-dashboard.md) | In progress (tracks A to E, 21 tasks; A1, A1b, A2, A3 and B1 done 2026-10-06, B2 next) |
