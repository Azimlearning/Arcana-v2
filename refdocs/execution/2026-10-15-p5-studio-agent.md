# Execution: P5 Studio, the learning and writing agent (D-42)

> Plan: `refdocs/plans/2026-10-15-p5-studio-agent.md`. Status: **In progress (2026-10-15).** S1 (writing), S2 (learning) and S3 (review schedule) built and tested; S5 and S6 next (S4's context is built: the vault and learner store are on the turn). Each slice is green end to end before the next starts.

## S1: Writing

| Task | What | Verify |
|---|---|---|
| W1 | Schema first: `"studio"` in `AgentName`; `WritingDraftData` (title, sections of cited segments, citations, bibliography entries with `apa`, `ieee`, `bibtex`) and the `WritingDraft` block in the `UIBlock` union; `pnpm codegen` | `pnpm codegen:check` clean; the Python types exist |
| W2 | `api/agents/studio.py`: tools `draft_section` (retrieve, one model call, server-verified quotes) and `format_bibliography` (pure); `ToolSpec`s; the agent on the roster | Unit tests with the fake LLM: grounded draft, an uncited segment dropped, a fabricated quote replaced by the server's sentence, nothing retrieved gives no draft |
| W3 | Fact Checker tools: `check_draft` (the same quote screen and judge over the draft's flattened segments, survivors regrouped, empty sections removed), `check_citation_accuracy` (each bibliography entry matches its stored document record), `originality_check` (a segment that is mostly a verbatim run of its source is flagged) | Unit tests plus a mutation suite with planted defects and a reported detection rate |
| W4 | Orchestrator: the `write` intent (rules and the model's allowed answers), its plan (research, studio, fact_checker) | Classification tests; an intent that names an agent not on the roster is skipped, as today |
| W5 | Composer: `ComposerEvidence.studio`, the `WritingDraft` Spec (precondition, fences, grounding rule, a11y, placement), `_raw_writing_draft`, the layout mode, the trace record | The catalog completeness test (catalog, builders, raw recipes) stays green; a turn through the real graph ends at the Composer with the block validated |
| W6 | Validator: re-derive every citation from the store, every bibliography entry from the document record, caps; fail closed | Registration suite of planted defects, every one rejected |
| W7 | Web: `WritingDraft.tsx` (outline, sections with citation markers, bibliography with copy and download as BibTeX or Markdown, empty and error states), registry, fixtures, tests | Vitest; the component in a real browser |
| W8 | Docs: `refdocs/guides/catalog.md` (the new component's section and caps table, parsed by a test), `refdocs/guides/agents.md`, D-42 | The caps-parity test passes |

## S2: Learning (built 2026-10-15)

`StudySet` (kinds `flashcard`, `blurt`, `cornell`, `socratic`), derived from the vault's definitions, claims and asserted links with no model call (`api/vault/study.py`); a leak test for every kind; the `study` intent; the Composer derives and validates the block against the vault and the learner's mastery; the web component with reveal and the three self-ratings. It is in the notes family (`NOTES_CATALOG`), not the turn catalog (see D-42). Tests: `api/vault/test_study.py`, `api/genui/test_study_block.py`, `api/agents/test_study_turn.py`, `web/components/genui/StudySet.test.tsx`.

## S3: Review (built 2026-10-15)

`StudyPlan` (notes family) from the learner's mastery and the dates of their ratings (`api/vault/review.py`, `LearnerStore.last_rated`): a fixed rule, soonest first, capped at 10, re-derived by the validator; the web component states the rule on screen. Tests: `api/vault/test_review.py`, `api/genui/test_study_plan_block.py`, `web/components/genui/StudyPlan.test.tsx`.

## S4: Context and the study intent

`TurnContext` gains the vault and the learner store; the Orchestrator's `study` intent and a learner-profile tool.

## S5: The adaptive dashboard

Re-verify end to end in a real browser (Basic and Adaptive, saved views, fallback, trace); take only what the catalog's rules allow from the interactive-UI direction; record screenshots.

## S6: The live grounding run

`cost-auditor` projection first; then the agent on the 38 questions with a real model; the quote check without a model; the Fact Checker's judge live; results and limits recorded.
