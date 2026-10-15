# Studio breadth (D-43) and the pane system (D-44): what was built and what was measured (2026-10-15)

Plan: `refdocs/plans/2026-10-15-studio-vera-parity.md`. Execution: `refdocs/execution/2026-10-15-studio-vera-parity.md`. Screenshots `v-*.png` and `v-browser-check.json` are in this folder.

## What exists now

Thirteen Studio tools on the shelf, all tools of the one Studio agent (D-05 stands): quiz, flashcards, blurting, Cornell notes, Socratic questions, learning insights, review schedule, document brief, cheat sheet, outline, literature review, abstract and audio overview. VERA AI's six functions map as: Quiz (quiz in the turn), Content (writing kinds), Podcast (a cited script, read aloud by the browser), Meetings (document brief), Visual (cheat sheet), Analytics (learning insights).

| Tool | Block | Model call | Checked by |
|---|---|---|---|
| Quiz me | `QuizCard` | none | re-derived by the validator; the answer is checked by the server |
| Document brief | `DocBrief` | none | re-derived: document, vault, mastery |
| Cheat sheet | `CheatSheet` | none | re-derived: focus page, vault |
| Learning insights | `LearningInsights` | none | re-derived: vault, mastery, rating dates, activity |
| Literature review, abstract, audio overview | `WritingDraft` (kind) | one, as the outline | server quote check, Fact Checker, validator |

Panes (D-44): any output opens beside the conversation (at most three), with a Table view (sort, filter, CSV with formula-safe cells), a keyboard-operable divider, an Expand mode, and stacking under the conversation at phone width.

## Tests (the full suites on the committed code)

| Suite | Result |
|---|---|
| Backend `uv run pytest -q` | 1627 passed, 1 skipped (was 1492; the new tests are the registration suites of planted defects for `DocBrief` (18), `CheatSheet` (15) and `LearningInsights` (16), the derivations, the kinds, the turns through the last gate) |
| Web `pnpm exec vitest run` | 459 passed (was 393) |
| `pnpm codegen:check`, typecheck, lint, `ruff check api`, `pyright api` | clean |

## Real browser (headless Chromium, fake LLM, a copy of the full-corpus vault; 19 of 19 checks pass)

The shelf offers thirteen tools; Quiz me shows a quiz in the chat and a choice is checked by the server; a brief shows key points, terms and next steps; a cheat sheet draws a diagram and lists the concepts; insights show mastery, activity and the review workload; an output opens in a pane, its Table view lists rows and sorts, the divider resizes by keyboard, the pane stays across a new question and closing all restores the layout; an abstract is labelled; an audio overview is a script with labelled speakers and offers Listen; no uncaught page errors; at 390 px a pane causes no horizontal overflow.

**What the browser found that the tests did not:** with a pane open the first version took width from the Studio and its buttons broke mid-word ("Flashcard s"). Fixed: the centre panel takes 35 percent of the Sources panel's share and the Studio keeps its own; a workspace test pins the numbers.

## Live check of the model-written kinds (`eval/studio_kinds_live.py`, protocol in its docstring; $0.353)

Four kinds on two topics, one attempt each, no retry. `eval/results/20261015T150410Z-studio-kinds-live.json`.

| Result | Value |
|---|---|
| Drafts shown (`ready`) | 8 of 8 |
| Quotes that are verbatim spans of a stored chunk | 33 of 33 |
| Passages kept by the Fact Checker | 46 of 50 (the judge removed 4, 8 percent) |
| Scripts with a speaker on every line | 2 of 2 (voices alternate in 1 of 2: the checker removed a line from the other, leaving two guest turns together) |
| Passages reported as close to their source | 0 |
| References built from the stored record | 1 to 3 per draft, none rebuilt (the model never writes them) |

## Limits, stated

- A literature review of a topic whose retrieved passages come from one paper is a review of one source; the tool does not widen retrieval (the dense retrieval topic cited one document).
- The fake LLM's text is a stand-in; the browser run shows structure and interaction, not writing quality. The live check measures grounding, not quality (constraint 9).
- Insights show a trend only with 7 of 14 days active; the weekly seasonal fit VERA used is not built (two weeks cannot separate it from noise). The workload applies the schedule's rule forward and does not model further forgetting.
- A brief is the vault's own sentences, not a summary, so it is only as complete as the vault.
- Read-aloud is a deferred enhancement (Azim, 2026-10-15): the Listen button is drawn and does nothing (`AUDIO_ENABLED = false`); the speech code is kept and tested with the flag passed on, and was never listened to.
- Not built from v1: Timeline (no extracted dates), a shown plagiarism report (the checker counts close passages and does not put them on the wire), a Studio block for gaps and contradictions (the Notes screen's lint reports them).
