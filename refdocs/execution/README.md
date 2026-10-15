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
| [2026-10-07-g1-atomic-graph-experiment.md](2026-10-07-g1-atomic-graph-experiment.md) | [../plans/2026-10-07-g1-atomic-graph-experiment.md](../plans/2026-10-07-g1-atomic-graph-experiment.md) | Done (tasks G1.1 to G1.7, 2026-10-07; measured in Looks 2 to 5) |
| [2026-10-15-p4b-lab-lifecycle.md](2026-10-15-p4b-lab-lifecycle.md) | [../plans/2026-10-15-p4b-lab-lifecycle.md](../plans/2026-10-15-p4b-lab-lifecycle.md) | Done 2026-10-15 (tasks L1 to L4) |
| [2026-10-15-question-set-extension.md](2026-10-15-question-set-extension.md) | [../plans/2026-10-15-question-set-extension.md](../plans/2026-10-15-question-set-extension.md) | Done 2026-10-15 (tasks X1 to X6) |
| [2026-10-14-p5-final-evidence.md](2026-10-14-p5-final-evidence.md) | [../plans/2026-10-14-p5-final-evidence.md](../plans/2026-10-14-p5-final-evidence.md) | In progress (F1, F4, F5, F6, F7 done 2026-10-14/15; F2 partly; F3 human link reading open, assistant-labelled estimate recorded) |
| [2026-10-14-p3-lite-rerank.md](2026-10-14-p3-lite-rerank.md) | [../plans/2026-10-14-p3-trained-tools-deliberation.md](../plans/2026-10-14-p3-trained-tools-deliberation.md) | Done (2026-10-14; spend $0.000062) |
| [2026-10-08-p4-verifiedlab.md](2026-10-08-p4-verifiedlab.md) | [../plans/2026-10-08-p4-verifiedlab.md](../plans/2026-10-08-p4-verifiedlab.md) | Done (V1 to V8 2026-10-08; V9 live generator 2026-10-15, $0.0458) |
| [2026-10-07-m2-lint-screen.md](2026-10-07-m2-lint-screen.md) | [../plans/2026-10-07-m2-lint-screen.md](../plans/2026-10-07-m2-lint-screen.md) | Done (tasks L1, L2, 2026-10-07; free) |
| [2026-10-07-q1-cloze-quiz.md](2026-10-07-q1-cloze-quiz.md) | [../plans/2026-10-07-q1-cloze-quiz.md](../plans/2026-10-07-q1-cloze-quiz.md) | Done (tasks Q1.1 to Q1.4, 2026-10-07; free, no paid step) |
| [2026-10-07-m2-obsidianmark2-vault.md](2026-10-07-m2-obsidianmark2-vault.md) | [../plans/2026-10-07-m2-obsidianmark2-vault.md](../plans/2026-10-07-m2-obsidianmark2-vault.md) | Done (tasks M2.1 to M2.10 built and measured; Look 5 full corpus 2026-10-14) |
| [2026-10-07-p2c-traversal-view.md](2026-10-07-p2c-traversal-view.md) | [../plans/2026-10-07-p2c-traversal-view.md](../plans/2026-10-07-p2c-traversal-view.md) | Done 2026-10-07 (tasks T1 to T5) |
| [2026-10-07-p2b-studio-shell-split-regions.md](2026-10-07-p2b-studio-shell-split-regions.md) | [../plans/2026-10-07-p2b-studio-shell-split-regions.md](../plans/2026-10-07-p2b-studio-shell-split-regions.md) | Done 2026-10-07 (tasks F1 to F5) |
| [2026-10-06-p2-genui-catalog-dashboard.md](2026-10-06-p2-genui-catalog-dashboard.md) | [../plans/2026-10-06-p2-genui-catalog-dashboard.md](../plans/2026-10-06-p2-genui-catalog-dashboard.md) | Done 2026-10-07 (tracks A to E; every task done except B5, a stretch deferred) |
