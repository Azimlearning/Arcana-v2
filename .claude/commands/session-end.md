---
description: Close out the session: changelog entry, STATUS update, ADRs, doc reconciliation
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

Close out this session per CLAUDE.md's mandatory rules. Do not skip a step because the session felt small.

1. `git status` and `git diff`: establish what actually changed. Don't rely on memory of the conversation.
2. Add an entry to `refdocs/changelog/CHANGELOG.md` in that file's documented format (newest first). The **Verified** line names a command that was actually run and its actual result; if nothing was run this session, write "nothing verified this session".
3. Update `refdocs/STATUS.md`: the phase table, and the verification ledger if anything was genuinely verified. Status never rounds up: code that compiles but was never executed is 🔶, not ✅.
4. Any architectural decision made this session → an ADR in `refdocs/changelog/DECISIONS.md`, with an id matching `refdocs/arcana-v2-PRD.md` §7. Any `ASSUMED:` that got resolved gets promoted or deleted, here and in the PRD's open questions.
5. If the work diverged from its execution doc, edit that doc to match reality and note it in the changelog's Deviations line.
6. Update the index tables in `refdocs/plans/README.md` and `refdocs/execution/README.md` if a doc was added or changed status. If a new environment variable appeared, add it to `refdocs/guides/env_setup.md` and `.env.example` now.
7. Any file ported from v1 or Synapse this session must start with a provenance header; add any that are missing.

Write without em dashes. Then show me the changelog entry you wrote, and list anything you couldn't resolve.
