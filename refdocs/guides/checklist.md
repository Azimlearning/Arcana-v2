# Pre-Ship Checklist: Arcana v2

> Run the relevant section before pushing or calling a phase done.
> Not every item applies to every change; use judgement based on what actually changed. But read the list; that's where you notice the thing you forgot.
> **The commands below are created by P0 task 1** (`refdocs/execution/2026-10-05-p0-walking-skeleton.md`). Before that task is done they do not exist; say so rather than claiming they passed.

---

## Every change

- [ ] **It was actually run.** Not "it compiles": executed, and the result observed. If it wasn't run, say so.
- [ ] **Build passes**: `pnpm -r build`
- [ ] **Tests pass**: `uv run pytest` and `pnpm -r test`
- [ ] **Lint/type check clean**: `uv run ruff check api`, `uv run pyright api`, `pnpm -r lint`, `pnpm -r typecheck`
- [ ] **No secrets staged**: `git status` shows no `.env*` except `.env.example`; no key literal in the diff. This repo is public.
- [ ] **No stray debug output** left in the diff
- [ ] **Changelog entry added**: `refdocs/changelog/CHANGELOG.md`, with an honest **Verified** line
- [ ] **STATUS.md reflects reality**: the phase table doesn't round up; the verification ledger has a row for what you just ran
- [ ] **Docs match what you built**: if the work diverged from the execution doc, that doc is edited

---

## Wire contract changed (a UIBlock, LayoutSpec, API payload, or error envelope)

- [ ] The type was changed in `packages/schema` first
- [ ] `pnpm codegen` was run and `pnpm codegen:check` passes
- [ ] The server validator handles the new or changed variant (fail closed)
- [ ] A new block type has a registry entry and a component with all four states
- [ ] A new component's structural precondition is written down, and retrieval can satisfy it (the bound)

---

## Generated artifacts (P4 onward)

- [ ] No new path lets an artifact reach the client without the verifier-minted type (there is a test for this)
- [ ] The artifact iframe still has `sandbox="allow-scripts"` only; no `allow-same-origin`
- [ ] Libraries come from the local vendor directory; no runtime CDN fetch
- [ ] The mutation suite was re-run if the verifier, contract checker, or generator prompt changed

---

## Paid API calls

- [ ] The call goes through `api/llm` (or the embeddings client) and writes to the spend ledger
- [ ] Model tier is the cheapest that does the job; any heavy-tier use is justified in the code comment
- [ ] No retry without a cap, no loop over user-sized input without a budget

---

## Evaluation runs

- [ ] The question set and corpus manifest are unchanged, or the change is declared as an amendment in the eval README and the changelog
- [ ] Gold annotations were written before the arms were run
- [ ] Results JSON is committed with the git commit it ran against

---

## New dependency

- [ ] Recorded in `refdocs/arcana-v2-sources.md` with its license and why it was chosen
- [ ] License is compatible with a public repository
- [ ] Its actual docs/types were read; the API was not recalled from memory
- [ ] Considered-and-rejected alternatives noted

---

## New environment variable

- [ ] Added to `refdocs/guides/env_setup.md` with where to get it
- [ ] Added to `.env.example` with a blank value
- [ ] Missing-variable case fails loudly at startup, naming the variable

---

## Architectural decision

- [ ] ADR in `refdocs/changelog/DECISIONS.md`: Decision → Why → Trade-offs/rejected
- [ ] Same id added to the PRD's §7 Decision Log
- [ ] Any `ASSUMED:` it resolves is deleted from the assumptions list

---

## Ported from v1 or Synapse

- [ ] The file starts with a provenance header: source repo, path, commit
- [ ] It was read in full and adapted to v2's interfaces, not pasted and patched until it compiled
