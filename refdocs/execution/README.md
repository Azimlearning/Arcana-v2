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
| [2026-10-05-p0-walking-skeleton.md](2026-10-05-p0-walking-skeleton.md) | [../plans/2026-10-05-p0-walking-skeleton.md](../plans/2026-10-05-p0-walking-skeleton.md) | Not started |
