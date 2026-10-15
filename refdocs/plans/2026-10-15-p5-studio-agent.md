# Plan: P5 Studio, the learning and writing agent (D-42)

> Execution doc: `refdocs/execution/2026-10-15-p5-studio-agent.md`. ADR: D-42 (settles D-22's separate Tutor and Writer, merged by D-30 as an ASSUMED). Scope source: PRD §3 (Tools, Studio), §6 P5; `refdocs/guides/agents.md` ("Studio (P5)" and the Fact Checker's P5 tools).
> Status: **Draft (2026-10-15).** Azim, 2026-10-15: "i would like the full studio agents as planned"; "proceed the rest". Spend for the build itself is nil (the fakes drive every test); the one paid step is the live end-to-end grounding run (A2, approved, about $1).

## Why this exists

P0 to P4 built retrieval, agents, a typed catalog, an adaptive layout and verified labs, but the product's second pillar, **learning and writing**, exists only as notes, a quiz route and mastery colouring. The PRD names a Studio agent that owns learner state and draft state, with learning tools (flashcards, quiz, blurting, Feynman explainer, Cornell notes), a Socratic turn, review scheduling, and writing tools (outline, a section drafted with citations, bibliography export, citation formatting), and the Fact Checker's matching tools for Studio output. Without it the project is a retrieval system with a viewer, not a learning workspace.

## What is built, in slices (never the second of anything before the first is green end to end)

| Slice | Delivers | New component | Spend |
|---|---|---|---|
| **S1 Writing** | The Studio agent and its `write` tool group: an outline and cited sections drafted from retrieved evidence, a formatted bibliography (APA-style, IEEE, BibTeX) derived deterministically from the cited documents; the Fact Checker's `check_draft`, `check_citation_accuracy` and `originality_check`; the Orchestrator's `write` intent; the Composer, validator and layout for it; the web component | `WritingDraft` | none (fakes) |
| **S2 Learning** | Learning tools over the vault, **no model call**: flashcards, blurting, Cornell notes, a Socratic turn (asks, withholds the answer, reveals the source on request), and the existing quiz through the same turn path; the Feynman explainer is the Research answer asked for plainly (existing `CitedSummary`) | `StudySet` | none |
| **S3 Review** | A review schedule from the learner's decayed mastery (A6): what is due, when, and why; checkable | `StudyPlan` | none |
| **S4 Context** | The Orchestrator's `study` intent and a learner-profile context tool; `TurnContext` carries the vault and the learner store | none | none |
| **S5 Dashboard** | The adaptive dashboard re-verified end to end (Azim: "make sure the adaptive dashboard works"), and the interaction ideas worth taking from the "intelligent UI" direction (interactive input components chosen by evidence, follow-up actions), within the catalog's rules | none or small | none |
| **S6 Live grounding run** | The agent on the 38 questions with a real model; every claim's quote checked verbatim against its cited passage without a model; the Fact Checker's judge run live for the first time | none | about $1 |

## Design (the decisions D-42 records)

1. **Studio is one agent with tool groups**, not Tutor and Writer (D-30). It owns two things nothing else owns: the learner's state (read through the learner store) and the draft. It never imports another agent, never builds a block (it returns payloads; only the Composer builds), and is reached only through `route_to_agent`.
2. **Everything the learner is shown is a verbatim span of a stored passage.** Learning items are derived deterministically from the vault's claims (no model, no spend, no new trust boundary); writing is the only Studio tool that calls a model, and it is gated by the Fact Checker like an answer (fail closed, a removed segment is never put back).
3. **Components join on evidence (constraint 7).** Each new component has a written structural precondition retrieval or the vault can satisfy, fences with caps, a grounding rule the validator re-derives, accessibility requirements, a placement hint, and a registration suite of planted defects. A component whose precondition is not met is not shown.
4. **Citation formatting is derived, never generated.** A bibliography entry is built by code from the stored document record (title, source file, arXiv id when the file name carries one); no author or year is invented. Where the record lacks a field the entry says so by omitting it.
5. **No wire type is defined twice.** Every payload is defined once in `packages/schema` and generated into Python; each block is validated server-side before streaming.
6. **Each new checker ships with a mutation suite** (planted defects the checker must catch), with the detection rate reported, not asserted.

## Not in scope, with reasons

- **A model-judged tutor that grades free-text answers:** a grader that is the same family as the generator is not independent; blurting shows the sources for self-comparison instead.
- **FSRS or any trained scheduler:** the P3 deliberation (D-37) found no data worth a model; the schedule uses the existing mastery arithmetic.
- **Audio, web search, essay-length generation, PDF export:** PRD non-goals or beyond a draft section.
- **A second writing component** (a "paper" with multiple sections across turns): one draft per turn; revision is a new turn.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A generated draft cites a quote that is not in the passage | High if shown | The server verifies every quote verbatim (as Research does), the Fact Checker re-checks, the validator re-derives; the mutation suite plants each case |
| The writer paraphrases a source so closely it is plagiarism | Medium | `originality_check` flags a segment whose text is mostly a verbatim run of its source; reported, not hidden |
| Three new components mean three web components, three registration suites and more layout cases | Medium | Slices; each is green before the next starts |
| A study item leaks the answer it withholds (the failure the quiz had) | Medium | A leak test over every item, the same rule as the quiz's blank-everywhere check |
| `TurnContext` grows | Low | Optional fields, defaults, as `graph` was added |

## Definition of done

Each slice: a plan task checked, the new component's registration suite passes and its planted defects are caught, a turn through the real graph with the fake LLM ends at the Composer with the block validated, the web component renders every state in a real browser, the full suites, ruff and pyright clean, `schema-guardian` and `test-runner` reviews done, D-42, STATUS and CHANGELOG current. Overall: the Studio agent is on the roster; `write` and `study` turns work end to end; the live grounding run is recorded.

## Related direction: "intelligent UI" in the large assistants (noted 2026-10-15, at Azim's suggestion)

Azim asked whether the adaptive dashboard and generative components could take ideas from OpenAI's "Intelligent UI" in ChatGPT with GPT-6 (announced 2026-10-07: responses that include charts, forms, buttons, calculators, editable graphs and checklists, with the model deciding when an interactive element helps). Secondary reports describe it as a library of standardised components with a compiler rather than model-written front-end code; I did not open the vendor announcement, so that account is unconfirmed. The wider 2026 pattern (declarative component specs streamed over an event transport) is the one this project already follows, so there is little to import and one distinction to keep:

- **What matches:** a closed, typed catalog; the model never writes UI code on the main path; layout is data; labs are the "calculator or editable graph" case, and they are verified.
- **What this project does differently on purpose:** the component is chosen by the Composer from a written, checkable precondition on retrieved evidence, not by the model's judgement of usefulness (constraint 7); and every shown sentence is a stored quote.
- **What was taken:** interactive starters (the Studio shelf puts a request in the box or asks at once), reveal-on-demand study items with self-rating, a review schedule as a checklist-like surface. Nothing was added that the catalog's rules do not allow.
- **Not taken, with reasons:** model-chosen components (it would break the admission rule), free-form generated forms, any client-side code generation beyond the verified lab.
