# Execution: Q1 a quiz from the vault's claims

> Plan: `refdocs/plans/2026-10-07-q1-cloze-quiz.md`. ADR: D-35 amendment A8. Tasks run in order. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07. Free: no paid step.**

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, D-35 A4, A6 and A8, `api/vault/view.py`, `api/genui/validate.py` (`_concept_page_issues`), `api/learner/`, `web/components/genui/ConceptPage.tsx`, `web/app/notes/NotesWorkspace.tsx`.
- A wire change starts in `packages/schema`, then `pnpm codegen` and `pnpm codegen:check`, then the validator, then the registry and the component with all five states.
- Only named files are formatted with `ruff format` (the repository is not ruff-formatted).

### Task Q1.1: Schema and the derivation

**Files:** `packages/schema/src/{payloads,blocks,api}.ts`, `api/vault/quiz.py` (new), `api/genui/builders.py`, tests.
1. Types: `QuizItem`, `QuizCardData`, the block `QuizCard`, `QuizAnswerRequest`, `QuizAnswerResponse`.
2. `derive_quiz(vault, docs, page_id, mastery)` and `derive_item(vault, docs, item_id)` as the rules of A8 say; `check_answer(vault, docs, item_id, chosen_page_id)` returns the right page and whether the choice was right.

**Verify:** tests by hand on the small vault: item choice order, one per concept, the blank, the distractors (same kind, not in the sentence, not grouped with the answer), the hash order, determinism, the block carries no answer, an item with no way to make a blank or fewer than three distractors is skipped and counted.

### Task Q1.2: Validator, catalog, Composer, routes

**Files:** `api/genui/validate.py`, `api/genui/notes_catalog.py`, `api/agents/compose.py` (`compose_quiz`), `api/routes/vault.py` (`GET /vault/quiz`), `api/routes/quiz.py` (`POST /quiz/answer`), `api/main.py`, the catalog guide.
**Verify:** the validator re-derives and rejects every planted defect (a moved answer, a changed option, a leaked answer field, a wrong sentence, a missing citation); the route records `quiz_correct` or `quiz_wrong` for the blanked concept; a forged item id, an unknown page and a quiz signal on the rating route are refused; no vault or no claims gives an `empty` block with a reason.

### Task Q1.3: The web

**Files:** `web/components/genui/QuizCard.tsx`, `registry.tsx`, `notesNav.tsx` (the answer action), `web/app/notes/NotesWorkspace.tsx` (the "Quiz me" button), `web/lib/api.ts`, tests, a real-browser run.
**Verify:** all five states; document text only as text; options as buttons that keep focus; the result announced politely; the source shown after answering; "More questions" asks again; the graph beside it recolours after an answer.

### Task Q1.4: Review and close

`schema-guardian` on the wire change; full suites; docs (changelog, STATUS, execution Reality notes, file map, catalog guide); commit locally.
