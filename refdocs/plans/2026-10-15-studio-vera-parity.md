# Plan: Studio breadth, covering the six functions of VERA AI (D-43)

> Execution doc: `refdocs/execution/2026-10-15-studio-vera-parity.md`. ADR: D-43 (extends D-42; narrows one non-goal, flagged `ASSUMED:`). Scope source: Azim, 2026-10-15: "for the studio make sure there will be more functions and outputs cause arcana v1 is successor to the vera ai project that has 6 studio functions so its supposed to be more".
> Status: **Done (2026-10-15).** Spend: the build is nil (fakes drive every test); one small live check of the new writing kinds, under a dollar.

## Why this exists

VERA AI (the PETRONAS Upstream project, May 2026; `vera-ai/VERA_AI_Project_Summary_Document.pdf`) is a RAG chatbot with six specialised agents: Analytics, Meetings, Podcast, Content, Visual and Quiz. Arcana is its successor, so a reader of the report will set the Studio beside that list. The Studio after D-42 had five tools (flashcards, Cornell notes, Socratic questions, a review schedule, an outline), and its Quiz sat in the Notes screen where "quiz me" gave flashcards. It was narrower than its predecessor in outputs, though deeper in grounding. This plan closes the breadth gap without giving up the rule that every shown sentence is a stored quote.

## What each VERA function becomes here (a learning workspace, not an enterprise one)

| VERA agent | What it did | Arcana Studio function | Model call | New component |
|---|---|---|---|---|
| Quiz | Assessments from internal material | **Quiz me**: the cloze quiz inside a turn, answers checked by the server | none | none (`QuizCard` exists) |
| Content | Drafts stories from raw submissions | **Literature review** and **abstract** writing kinds beside the outline, same cited and checked pipeline | one (as the outline) | none (`WritingDraft` gains `kind`) |
| Podcast | Audio from a topic, with a script | **Audio overview**: a two-voice script, every line cited, read aloud by the browser's own voice | one | none (`WritingDraft` kind `script`) |
| Meetings | Notes to an executive brief and action items | **Document brief**: key points, key terms and action items for one document | none | `DocBrief` |
| Analytics | Trends and a forecast (regression, moving average, weekly seasonal) | **Learning insights**: coverage, mastery spread, weakest concepts, activity trend and the review workload ahead | none | `LearningInsights` |
| Visual | Infographics and image tagging | **Cheat sheet**: a one-page visual of a concept and its neighbours, printable | none | `CheatSheet` |

After this the Studio holds thirteen tools: flashcards, blurting, Cornell notes, Socratic questions, quiz, review schedule, learning insights, outline, literature review, abstract, audio overview, document brief and cheat sheet. Every one has a request pattern that reaches it through the Orchestrator and a button on the shelf.

## Where v1's outputs and agents went (Azim, 2026-10-15: refer to v1, but merge and upgrade, do not rebuild all of them)

v1 had 25 agents and 24 output components. D-05 stands: these became tools of one agent, and several v1 outputs were merged into one v2 block or into a view of one.

| v1 output or agent | v2 | Status |
|---|---|---|
| FlashcardDeck, BlurtingPrompt, CornellNotes, SocraticDialog, FeynmanExplainer | `StudySet` (four kinds) and the plain Research answer | built (P5 S2) |
| QuizCard | `QuizCard`, now also in the turn | built (V1) |
| StudyPlanner | `StudyPlan` | built (P5 S3) |
| ProgressDashboard, InsightCard | `LearningInsights` | built (V5) |
| DraftEditor, BibliographyExport, CitationPreview | `WritingDraft` (kinds, bibliography, citation pills) | built (P5 S1, V2) |
| AudioSummary | `WritingDraft` kind `script`, read aloud by the browser | built (V2) |
| ConceptMap, KnowledgeGraphView | `ConceptMap`, `GraphView`, `NotesGraph`, `CheatSheet` | built |
| ComparisonChart, LiteratureMatrix, DataTable | `ComparisonGrid` and the panes' Table view (sort, filter, CSV) | built (D-44) |
| SourceList | `SourceList` | built |
| PlagiarismReport | the Fact Checker counts passages close to their source (`too_close_to_source`); not a shown block | partial: counted, not shown (limit) |
| ContradictionAlert, GapAnalysis | the Notes screen's lint (orphans, duplicate names, concepts two papers define, hubs): reported there, never fixed | covered in Notes, not a Studio block (decision: it has no cited sentences to re-derive a block from) |
| Timeline | none | not built: no dates are extracted |
| Web Search | none | PRD non-goal |

## Design

1. **One dispatch for the vault-derived tools.** The deterministic tools (quiz, brief, sheet, insights, plus the existing flashcards, blurt, Cornell, Socratic, plan) are `study` kinds. The Studio returns a request (a kind and a page), the Composer derives the block from the vault and the learner's data, and the validator derives it again. Nothing the agent says is trusted.
2. **The writing tools stay one pipeline.** A kind changes the prompt and the label, not the trust path: retrieval first, server-verified quotes, derived references, the Fact Checker's judge, the validator. A script adds a speaker per segment; every line is cited like any segment.
3. **Components join on evidence (constraint 7).** Each new component has a written precondition the vault or the learner's events can satisfy, fences with caps, a grounding rule the validator re-derives, accessibility requirements, a placement hint and a registration suite of planted defects.
4. **Forecasts say what they are.** Learning insights reports the workload ahead by applying the review schedule's own fixed rule forward (no model), and a trend line only when there are enough days of activity to fit one. Below the threshold it shows the counts and says why there is no line.
5. **Audio.** The wire carries data only. The server generates no audio. The browser's Web Speech API reads the script on the learner's device, if the browser has it; nothing is sent anywhere. This reads D-43's narrowing of the PRD non-goal "audio or video generation": generation is not done, listening is a user-agent feature. `ASSUMED:` until Azim confirms.

## Not in scope, with reasons

- **Server-side speech or an audio file:** a non-goal, a paid or heavy dependency, and not needed to make the script listenable.
- **Image generation (VERA's Stable Diffusion), image tagging:** a non-goal (generation), and a local GPU service is not this project's shape.
- **Transcribing a meeting:** Arcana's inputs are the learner's documents; the brief is made from those.
- **Time-series models beyond a fit and a moving average:** the data is a few hundred ratings; anything fancier would be unmeasurable.
- **Matching VERA's agent count:** D-05 stands. These are tools of one agent, not agents.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A new kind of draft drifts from its sources | High if shown | The same server quote check, judge and validator as the outline; a mutation case per kind |
| A brief or sheet shows a sentence that is not a stored span | High if shown | Every sentence comes from the vault's claims and definitions through the existing citation path; the validator re-derives |
| Insights forecasts over too little data | Medium | A written threshold; below it, no line and a statement of why |
| The speech API is absent or speaks badly | Low | The script is readable text first; the button is hidden when the API is absent |
| Five new request patterns reroute frozen questions | Medium | Anchored patterns; the existing test runs every frozen question through `classify` |
| Scope: a function ships without its tests | Medium | One slice at a time, each green before the next |

## Definition of done

Each slice: its plan task checked, its registration suite's planted defects all rejected, a turn through the real graph with the fake LLM ends at the Composer with the block validated, the web component renders every state, the full suites, ruff and pyright clean, D-43, STATUS and CHANGELOG current. Overall: all thirteen tools reachable from the shelf and from a typed request; a real-browser pass over the new blocks at desktop and phone width; the one live check of the new writing kinds recorded.
