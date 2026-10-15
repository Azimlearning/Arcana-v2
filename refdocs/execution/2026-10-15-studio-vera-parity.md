# Execution: Studio breadth, covering the six functions of VERA AI (D-43)

> Plan: `refdocs/plans/2026-10-15-studio-vera-parity.md`. Status: **Done (2026-10-15).** V1 to V6 built and green; the live check of the writing kinds recorded in `refdocs/evidence/20261015-studio-vera-parity.md`.

## Order

| Slice | Delivers | Schema change | Model call |
|---|---|---|---|
| **V1 Quiz in the turn** | `quiz` study kind; the Composer derives `QuizCard` and validates it with the vault and mastery; the web `QuizCard` answers through the API when no notes screen is present; shelf buttons for Quiz and Blurting | none | none |
| **V2 Writing kinds** | `WritingDraftData.kind` (`outline`, `literature_review`, `abstract`, `script`), an optional `speaker` on a segment, per-kind prompts, `write_kind`, validator rules, a "Listen" control (browser speech) on a script | `WritingDraftData`, segment | one, as before |
| **V3 Document brief** | `DocBrief` (notes family): key points, key terms, action items for one document; `brief` study kind | new payload and block | none |
| **V4 Cheat sheet** | `CheatSheet` (notes family): one page for a concept and its neighbours, a small diagram with a text list beside it, copy and print; `sheet` study kind | new payload and block | none |
| **V5 Learning insights** | `LearningInsights` (notes family): coverage, mastery spread, weakest pages, activity by day with a fitted trend and a moving average, the review workload for the next 7 days; `LearnerStore.daily_activity`; `insights` study kind | new payload and block | none |
| **V6 Panes** | The centre area's pane system (D-44): open any output beside the conversation, Table view with sort, filter and CSV, resizable, expandable; `web/lib/tables.ts`, `Panes.tsx`, `TableView.tsx`, store and workspace | none | none |
| **V7 Close** | Shelf complete; real-browser pass at desktop and phone width; one live check of the writing kinds; guides, D-43, PRD row, STATUS, README, CHANGELOG | none | the live check |

## V1: Quiz in the turn

| Task | What | Verify |
|---|---|---|
| Q1 | `api/agents/studio.py`: `quiz` in `_KIND_WORDS` (before flashcard; words: quiz, test me, practice questions, multiple choice); `api/vault/study.py` `STUDY_KINDS` stays the set of `StudySet` kinds, so `quiz` is dispatched separately | `study_kind("Quiz me on dense retrieval") == "quiz"` |
| Q2 | `api/agents/compose.py` `_quiz_block`: `derive_quiz(vault, docs, focus, mastery)`, build, `validate_block(..., vault, mastery)`; refused with `no_study_material` when there are no items | A turn test through the real graph; an empty vault is refused, not an error |
| Q3 | Web `QuizCard.tsx`: use `answerQuiz` when `useNotesNav()` has no `answer`; remove the "open the notes screen" line | Vitest: answers from the chat; the notes screen path unchanged |
| Q4 | Shelf: Quiz becomes a starter ("Quiz me on "), Blurting is added | `Studio.test.tsx` |

## V2: Writing kinds

| Task | What | Verify |
|---|---|---|
| K1 | Schema first: `WritingDraftData.kind`, `WritingSegment.speaker?: "host" \| "guest"`; `pnpm codegen` | `pnpm codegen:check` |
| K2 | `studio.py`: `write_kind(request)`; one system prompt per kind (outline and section as now; a literature review of 2 to 4 paragraphs comparing the sources; an abstract of one section; a script of 6 to 12 short turns between a host and a guest); the same `build_draft` | Unit tests per kind with the fake LLM |
| K3 | `fact_checker.check_draft` keeps `speaker` through the regroup | A script survives the checker with speakers intact |
| K4 | Validator: `kind` known; `speaker` present on every segment of a script and absent otherwise; caps | Registration suite: planted defects (missing speaker, speaker on an outline, unknown kind) |
| K5 | Orchestrator `write` patterns: "abstract", "literature review", "audio overview", "podcast", "script"; `ROUTE_SYSTEM` words | Classification tests; every frozen question still classifies as before |
| K6 | Web: kind label, dialogue layout, Listen and Stop (hidden when `speechSynthesis` is absent), the on-screen note that the voice is the browser's | Vitest with a speech stub |

## V3: Document brief

| Task | What | Verify |
|---|---|---|
| B1 | Schema: `DocBriefData` (docId, title, keyPoints with `citationId`, terms with `citationId`, actions with a `kind` and a reason, citations) and the block | codegen |
| B2 | `api/vault/brief.py` `derive_doc_brief(vault, docs, doc_id, mastery)`: key points are the document's claims ordered by how many pages each names, then claim id; terms are pages with a stored definition in that document; actions come from mastery (review what is weak, start with what is unrated), each with a stated reason | Unit tests; a leak-free and verbatim test |
| B3 | `NOTES_CATALOG` entry (precondition, caps, a11y, placement); validator re-derives and compares | Registration suite |
| B4 | Composer `brief` kind; the document is the one the request names or, failing that, the document the focus page is mostly in, else the one with most claims | Turn test |
| B5 | Web component; copy as Markdown | Vitest |

## V4: Cheat sheet

| Task | What | Verify |
|---|---|---|
| C1 | Schema: `CheatSheetData` (focus, entries with a definition citation and neighbour ids, citations) and the block | codegen |
| C2 | `api/vault/sheet.py` `derive_cheat_sheet(vault, docs, focus_id, mastery)`: the focus page and up to 7 neighbours by link strength; each entry its first stored definition or claim; neighbour ids drawn from asserted links | Unit tests |
| C3 | Catalog entry, validator re-derivation, registration suite | planted defects |
| C4 | Composer `sheet` kind | Turn test |
| C5 | Web: entries, a small SVG diagram with the same entries as a list beside it, copy as Markdown, print stylesheet | Vitest; a browser check |

## V5: Learning insights

| Task | What | Verify |
|---|---|---|
| I1 | `LearnerStore.daily_activity(days, now)` (default empty), SQLite implementation: events per local day | Store tests |
| I2 | `api/vault/insights.py` `derive_insights(vault, mastery, last_rated, activity, as_of)`: coverage, three mastery bands, five weakest, the last 14 days of activity, a least-squares trend and a 3-day moving average only when 7 or more days have activity, the review workload for each of the next 7 days from the schedule's rule applied forward | Unit tests with fixed dates |
| I3 | Schema, catalog entry, validator re-derivation (from the same inputs), registration suite | planted defects |
| I4 | Composer `insights` kind (passes the activity into the validator through the turn context) | Turn test |
| I5 | Web: counts, a bar chart as an accessible table, the workload row | Vitest |

## V6: Panes (built 2026-10-15)

`useWorkspace` holds `panes` (at most three), `paneShare` (30 to 70 percent) and `paneFocus`; `Workspace` splits the centre panel into the conversation, a keyboard-operable separator and `Panes`; `Shell` widens the centre panel while panes are open; each block in the conversation gets "Open in a pane"; a pane's Table view comes from `tablesOf` (a pure function of the block). Tests: `web/lib/tables.test.ts`, `web/components/shell/Panes.test.tsx`, store and workspace tests.

## V7: Close

Shelf with all tools; Orchestrator patterns anchored and frozen-question test green; `catalog.md` caps parity; real-browser pass; the live check; docs.
