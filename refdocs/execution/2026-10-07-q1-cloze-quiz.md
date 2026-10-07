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

## Reality (what was built, and where it differs from the plan above)

Status: **Q1.1 to Q1.4 built, reviewed and checked.** Free throughout: no model call, no embedding.

- **Q1.1.** Schema types as planned (`QuizItem`, `QuizCardData`, the `QuizCard` block, `QuizAnswerRequest`, `QuizAnswerResponse`); `QuizItem.page` is `@int` (without it the generated model holds a float and the validator's type-strict comparison refused every item). `api/vault/quiz.py` holds `derive_quiz`, `derive_item`, `check_answer` and `source_citation`. 23 by-hand tests in `api/vault/test_quiz.py` over a nine-page vault (the expected items and the passed-over counts are worked out in the file's header).
- **Deviation 1, the wrong-answer rule (A8 rule 4) was tightened before anything used it.** A read-only probe over the 819 real claims of `data/m2/atomic2-vault1` (777 make an item) showed 119 of 3,108 options longer than six words (paper titles) and 56 with `:` or `?`, and one-off mentions ("Tokyo Skytree", "Meiji Shrine") as wrong answers. Two conditions were added: a wrong answer is in at least two passages and its name is not title-like (at most six words, no `:` or `?`). Afterwards the same 777 claims make an item and 4 and 1 options remain (answers, which are not filtered). Names are compared as words with a hyphen counted as a space, so "Retrieval-Augmented Generation" and "retrieval augmented generation" are one name (the folding the vault uses joins a hyphenated word, which is right for finding names in PDF text and wrong for this comparison). The remaining weakness is a real but unrelated concept of the same kind, which only a model or a human could judge.
- **Deviation 2, `empty` carries `skipped`.** The plan said a placeholder carries nothing; an `empty` quiz now carries the count of claims looked at so the screen can say why in words (no claims at all, or N looked at and none made fair). `loading` and `error` still carry nothing, and the validator refuses an `empty` block when the vault can make a question.
- **Deviation 3, the graph beside the quiz follows the concept just answered.** The plan said the graph recolours after an answer; in the overview the 40 most linked pages usually do not include the concept answered, so nothing would have changed on screen. After an answer the screen now asks `/vault/notes?page=<answered concept>` and replaces only the graph block with the graph around that concept (its colour is the new mastery); the questions are not refetched, so they do not change under the learner. "More questions" fetches a new quiz (the weakest concepts first, so a missed one comes back).
- **Reading a result.** `0.6667` after one correct answer is "getting there" (comfortable starts at 0.67), as the rule says; a page's mastery line now reads "from N ratings and answers".
- **Q1.2.** Validator `_quiz_card_issues` (re-derive and require equality; the schema forbids extra fields, so a block carrying an answer is refused before content validation), `QUIZ_CARD` in the notes registry (chat main, priority 10), `compose_quiz` (the quiz and the notes graph, placed by the layout), `GET /vault/quiz`, `POST /quiz/answer` (404 for an item the vault cannot derive, 422 for a choice that is not one of the four options, neither records anything; a 4 KB body limit). 16 planted defects and 5 leaked-field defects are rejected; the route tests run on a fresh app with the same vault.
- **Q1.3.** `QuizCard.tsx` with all five states, options as buttons that keep focus, the result as a polite status that says which option was right in words, the source shown after answering, document text as text. The notes screen has "Quiz me" ("Quiz me on this page" when a page is open) and a quiz mode: answering goes through the server, "All pages" leaves it. Real browser (fake mode, the `atomic2` vault copy in `data/m2/q1-demo`, 1440 by 900): a quiz of five, a wrong and a right answer, mastery in words under each, the graph around the answered concept in amber, "More questions" asking the missed concept again, a quiz about one page (GraphRAG) with keyboard Enter and focus kept on the button, no console errors; `refdocs/evidence/q1-1-quiz.png`, `q1-2-answered.png`.
- **Q1.4 review and deviation 4 (the answer leaked).** `schema-guardian` found one blocking defect: the blank replaced only the first occurrence of one name, so a name of the answer stayed in the sentence in 122 of 1,569 real items (7.8 percent: `claim-1~rag` showed "RAG system" after the blank), and the document title, a file name here, held it in 132 (8.4 percent). The validator re-derives from the same function, so it had blessed every one, and the one test looked at a single item. Fixed: every occurrence of every name (label and aliases of 2 or more characters) is blanked, an item is not made when a name still occurs (hyphen-blind), a sentence that already holds a blank is refused, and a revealing title is left out (`docTitle` empty, "a document" on screen); the screen fills every blank. Counted over all 1,724 claim and page pairs of the real vault: 1,577 items, name still in text 0 (it was 2 after the first fix, "QA" beside "question answering", until names of 2 characters were included), 290 titles left out. A corpus-level test and by-hand tests now pin it. Should-fix items done: the answer route builds the reply first and records the event last (a failure no longer leaves an event for a retry to double); a failed answer offers "More questions" (the documents may have changed); the limits are written (no per-question guard, a rebuild between quiz and answer, a derivation failure is a generic error envelope, plural forms not in the alias list can stay). Noted, not changed: the client swaps the graph block it gets from a second `/vault/notes` reply (the server validated it; only which block shows is the screen's); the plan's mention of lint near-duplicates was wrong and is corrected; a merged page labelled with a long name and the alias "RAG" blanks "RAG" (a graph-quality limit).
- **Not built (as planned):** model-written questions or wrong answers, free-text answers, scheduling beyond "weakest first", quiz history. A cloze tests recognising a name in a sentence, not understanding it; the screen says so.
