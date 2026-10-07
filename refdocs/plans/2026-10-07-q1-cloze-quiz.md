# Plan: Q1 a quiz from the vault's claims, feeding the learner's mastery (no model call)

> Follows M2 (`2026-10-07-m2-obsidianmark2-vault.md`). Execution doc: `refdocs/execution/2026-10-07-q1-cloze-quiz.md`. ADR: D-35 amendment A8 (the rules are fixed there before the code).
> Status: **Approved by Azim 2026-10-07** ("Quiz from claims", chosen from the options for what to do while the monthly cap stays as it is). **Free: no model call, no embedding, nothing paid.**

## Why this exists

Mark 2 left two pieces waiting for each other. The vault holds claim sentences (819 over the 3-paper slice with the `atomic2` builder); the learner layer takes ratings and has the rule for quiz results (`quiz_correct`, `quiz_wrong`, D-35 A6) but nothing yet produces a quiz. A fill-in-the-blank quiz made from a claim joins them: **notes to claims to a question to an answer to mastery to the graph's colour**, with every sentence taken from the documents and checkable against its source. It is also the first step towards the Studio's quiz generator (P5), done here in a form that needs no model.

## How it fits the plans and docs that already exist

- **The component and its name are the catalog guide's.** `QuizCard` is listed in `refdocs/guides/catalog.md` ("Not admitted, and why") and in D-29 as Studio-agent work for P5, **because no agent produced its evidence yet, so an admission check would have nothing to check**. That reason no longer holds: the vault's claims are such evidence, and a deterministic tool can supply it without a model. This plan therefore **moves `QuizCard` from "not admitted" to built, with the vault as its supplier** (D-35 amendment A8, which amends D-29); the guide's table and the component's own section are updated when it is built.
- **The tool belongs to the Studio group, as D-30 and `refdocs/guides/agents.md` say** ("learning: flashcards, quiz, blurting, Feynman explainer, Cornell notes"; capability grows by tools and recipes, not by agents). This is the quiz tool of that group, with no agent in front of it yet: the Studio agent (P5) will route to it, and may add a second supplier of the same block (model-written questions) behind the same validator.
- **Placement follows P2b (D-32).** The quiz is an interaction, so it asks for the chat panel's main area (a study component may later ask for `secondary` to split the middle section); its outputs would go to the Studio shelf. The disabled generator tiles on the chat screen are the Studio agent's to enable; this plan reaches the quiz from the notes screen instead and does not touch them.
- **The learner layer's rule for quiz events is A6's** (`quiz_correct`, `quiz_wrong` in the same decayed-belief rule); this plan only produces them.

## What it is

A `QuizCard` block: up to 5 items, each a claim sentence from the documents with the name of one concept blanked out and four concept names to choose from, one of them the blanked one. The block does **not** say which option is right. The learner picks one; the server checks it (it derives the answer from the vault again, as the validators do), records a `quiz_correct` or `quiz_wrong` event for the concept that was blanked (not for the wrong one chosen), and answers with whether it was right, the right name, the source of the sentence and the concept's new mastery. The notes screen gets a "Quiz me" button (on a page: claims that name it; otherwise across the vault) and shows the graph beside the quiz, so the colours move as the learner answers.

## What's already covered (no work needed)

The vault, its claims and pages (M2.1 to M2.4), the notes registry and the pattern for a re-derived block (`ConceptPage`, `NotesGraph`, D-35 A4), the learner store and the mastery rule with the two quiz signals (A6), the Composer's `compose_notes`, the notes screen and its context for actions (`notesNav`).

## Scope

**In:** the schema (`QuizCard`, the answer request and response); the derivation (a pure function of the vault, the stored passages and the mastery snapshot, with fixed rules for choosing items, the blank and the distractors); the validator (re-derive and require equality; the block never carries the answer); the notes catalog entry; the Composer's `compose_quiz`; `GET /vault/quiz` and `POST /quiz/answer`; the web component with all five states; the notes screen's button; tests; a real-browser run; a `schema-guardian` review.

**Out:** model-written questions or distractors (a Studio generator in P5 may add them, as another builder of the same block); free-text answers; spaced-repetition scheduling beyond "weakest first"; quiz history or scores beyond the mastery events; timed quizzes.

## Approach

- **Server-checked answers.** The block holds no answer, so a client cannot read it; the answer is derived again from the item's id. The public rating route still refuses quiz signals, so a quiz result cannot be forged from outside the quiz route.
- **Weakest first.** Items are chosen from claims whose concept the learner knows least (a concept rated "needs work", then one not yet rated, then comfortable ones), at most one item per concept, so a short quiz spreads across concepts.
- **Distractors without a model.** Other concepts of the same kind (when the kind is known), mentioned in at least two passages, whose names are not a paper's title and do not occur in the sentence or share all their words with the answer's, ordered by a hash of the item and the concept so the same quiz always looks the same and cannot be gamed by position (D-35 A8 rule 4, which was tightened the same day after a read-only look at the real claims).
- **Honest limits.** A cloze tests recognition of a name in a sentence, not understanding; distractors can be too easy (a different kind of thing) or, with the older free-form graph, noisy. The claims exist only for graphs built with `atomic2`; with none, the block says so.

## Cost estimate

None. No model call, no embedding, no network.

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| A distractor is a synonym of the answer (an alias page that was not grouped) | Medium: an unfair item | Distractors exclude names that occur in the sentence and pages whose words contain or are contained in the answer's (a hyphen counts as a space); the lint report is not used |
| The blank cannot be made (the name is hyphen-broken in the passage) | Low | Such a claim is not an item; counted |
| The same quiz every time | Low | Items depend on mastery, which moves with every answer; a "More questions" request after answering gives a different set |
| The answer leaks through the block | High | The block carries no answer; every name of the answer is blanked everywhere in the sentence and an item with a name left is not made; a title holding a name is left out; a corpus-level test and a count over the real vault (0 of 1,577) pin it; the answer route derives it again |
| Learner data | Low | Events only, as before; the quiz adds `quiz_*` events for a concept id |
