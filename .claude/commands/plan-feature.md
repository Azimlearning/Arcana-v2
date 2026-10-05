---
description: Write the plan + execution doc pair required before building
argument-hint: [what you want to build]
allowed-tools: Read, Write, Glob, Grep, Bash
---

Produce the plan/execution pair CLAUDE.md requires before any non-trivial implementation, for: $ARGUMENTS

First read `refdocs/STATUS.md`, `refdocs/arcana-v2-PRD.md`, `refdocs/changelog/DECISIONS.md`, and the code this would touch. Check whether an existing plan already covers it; if so, say so instead of writing a duplicate.

Also check what already exists as reference: Arcana v1 (`../Arcana/`, read-only) and Synapse (`GenUI-Education`, see `refdocs/arcana-v2-sources.md`). Name what can be ported (with a provenance header) and what must be written fresh, and why.

Write two files, matching the structure of the existing docs in those directories:
- `refdocs/plans/YYYY-MM-DD-<slug>.md`: what and why: scope in/out with reasons, approach, a risk table with honest confidence levels, and a definition of done phrased as observable facts.
- `refdocs/execution/YYYY-MM-DD-<slug>.md`: how and in what order: numbered tasks, each naming the files it touches and carrying its own **Verify** step with a real command and expected result.

Where a task depends on an external library's behavior, its first step is "read the actual docs/types/source"; do not encode an API you're recalling from memory. If the feature touches the wire, include the schema-first sequence from `.claude/memory/preflight.md` question 5. If it adds a paid call, include a cost estimate task.

Add both files to the index tables in `refdocs/plans/README.md` and `refdocs/execution/README.md`.

Do not implement anything. Return both paths and the task order.
