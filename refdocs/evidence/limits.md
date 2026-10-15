# Limits chapter: what the evidence does not show (2026-10-15)

> Built from the ledger in `refdocs/evidence/README.md`, the decisions in `refdocs/changelog/DECISIONS.md` and the evidence records. Grouped by what each limit threatens. Every item names its source. Living: when a limit is closed, strike it in the ledger and here.

## 1. Threats to the retrieval conclusions

| Limit | Effect on a claim | Source |
|---|---|---|
| **38 answerable questions in two sets drawn differently** (the original 19 are harder, cross-document; the 19 new ones lean single-paper and mechanism-shaped). No pair of arms is significant at 0.05 | Every retrieval difference is descriptive. "Not shown to help" is not "shown not to help" | `20261015-question-set-extension.md`; D-26; D-39 |
| The extension was drafted by the system's author, from paper text only, and gold completeness is unproven (a question can have more support than found) | Recall is a floor; questions may suit the system | D-39; `eval/gold/README.md` ("What this does not establish") |
| No contradiction questions in the extension | Contradiction behaviour is measured on the original 4 only | `refdocs/plans/2026-10-15-question-set-extension.md` |
| The graph signal's gain over flat does not replicate (+0.039 on the original 19, p = 0.15; -0.042 on the new 19; pooled -0.001, p = 0.69) | GraphRAG is not shown to beat dense retrieval alone on this corpus; do not claim a retrieval gain | `20261015-question-set-extension.md`; D-26; D-40 |
| Candidate depth 30 was chosen post hoc among declared depths and reversed when it did not replicate (D-38, D-40) | No depth claim; the final benchmark uses the frozen protocol | D-38; D-40 |
| One corpus (16 papers, 1,570 passages) and one build per graph; a rebuild would differ (no temperature control) | Results are about this corpus and this build | `20261014-m2-look5-full-corpus.md` |
| The frozen `graph` signal is weak on its own (0.11 nDCG@10 on the original set) | Graph retrieval is a minor contributor in the fused result | `20261014-m2-look5-full-corpus.md` |

## 2. Threats to the Mark 2 (vault) conclusions

| Limit | Effect | Source |
|---|---|---|
| The vault lifts its own graph signal (+0.041 pooled, p = 0.34) but not the fused result (+0.010, p = 0.86) | Its case is the notes, links, claims, quiz and mastery, not a retrieval gain | `20261015-question-set-extension.md`; D-35 Look 5 |
| The gate's clause 3 (question words recognised) fails for the `atomic2` graph: 0.632 against 0.657 | `ready_for_azim_to_decide` is false for this build | `20261014-m2-look5-full-corpus.md` |
| **No human has read a link audit sample.** One sample (the `atomic2` build) was labelled by the assistant: asserted links 0.86 yes, co-mention 0.58 yes; 30 of 100 sentences are bibliography entries. The two earlier samples are unread | Link precision is a model-judged estimate on one sample; the human reading would supersede it | `refdocs/evidence/README.md` ledger; `eval/results/*-m2-audit-sample.md` |
| The full-corpus build was made over two provider routes of the same model in two invocations (Anthropic credit ran out mid-run) | Disclosed provenance; a clean single-route rebuild would differ | `20261014-m2-look5-full-corpus.md`; D-35 A9 addendum |

## 2b. Threats to the live-system conclusions

| Limit | Effect | Source |
|---|---|---|
| One live run of 39 questions and 8 writing topics, one model, no repetition | Rates are descriptive; a rerun would differ | `20261015-grounding-live.md` |
| Citation precision 0.21 and gold recall 0.21 against a gold set that is a floor; half the answers cite no gold-relevant chunk | The answers are grounded, not shown to be relevant or correct; no model-judged quality exists | same; constraint 9 |
| The Fact Checker removed 7 percent of claims that had valid quotes | It is a measured gate with a cost: some supported claims may be removed too (not measured: no labelled support set) | same |
| The browser checks used fake text; the phone-width pass checked layout only (no horizontal overflow at 390 and 768 px) | Real-model text in the UI was seen only in the data, not in a browser | `20261015-p5-studio-browser.md` |

## 3. Threats to the model-judged and trained-tool conclusions

| Limit | Effect | Source |
|---|---|---|
| RAGAS 0.4.3 is installed and its non-LLM context metrics are 0.0 for every arm (the passage is much shorter than the chunk; default threshold, not tuned); LLM-judged RAGAS metrics were not run (they must go through the LLM seam so spend is booked) | No model-judged score exists; none is claimed; the frozen relevance rule is the only retrieval metric | `20261015-ragas-context-metrics.md`; constraint 8 and 9 |
| The one trained-tool experiment (a pretrained cross-encoder) was negative and costs about 5 s per query on CPU; no router or mastery model was built | Objective 03 is met by a documented negative result under the supervisor's rule (relayed, not quoted) | D-37 (Resolved) |

## 4. Threats to the product claims

| Limit | Effect | Source |
|---|---|---|
| VerifiedLab: a branch off the grid and off the fuzz is not seen; the live generator is built and measured on 4 contracts and 8 attempts (6 of 8 accepted after one prompt revision; F1@k refused twice for want of the contract's clamp); the lifecycle (D-41) is built but `audit_lab` has no scheduled caller (ordinary reuse audits and promotes a lab) and crystallisation into a level 1 component is reported only, not built | The lab claim is "a verified artifact from a stored formula under a fixed template", not "any generated lab" | D-36 and its amendments |
| The labs offered depend on formulas the stored passages state (4 of 4 candidate contracts met; ASSUMED reading of the domain) | Usability evidence is four labs, not a general capability | D-36; `STATUS.md` working assumptions item 1 |
| Quiz wrong answers are chosen without a model, so some are too easy; the `one_more_word` lint reason is noisy on real data | Learning-feature quality is descriptive only; no user study (D-06) | D-35 A8; `refdocs/execution/2026-10-07-m2-lint-screen.md` |
| The dashboard is cramped at 1440 px and untried at phone width | UI claims are desktop only | `STATUS.md` P2 row |

## 5. Threats to cost and reproducibility claims

| Limit | Effect | Source |
|---|---|---|
| The embeddings price is marked `ASSUMED` in `api/llm/pricing.py` (the OpenAI page states none) | Reported spend is an estimate until reconciled with the provider console | `STATUS.md` working assumptions item 3 |
| OpenRouter model ids are `ASSUMED` to follow its dotted naming | The fallback route's cost and ids are unconfirmed | `STATUS.md` working assumptions item 2 |
| Anthropic's own credit balance is separate from the monthly cap and can end a build mid-run | Live runs need credit as well as cap | D-35 A9 addendum |

## Studio breadth and panes (D-43, D-44)

A brief is the vault's own sentences, not a summary, and is only as complete as the vault; insights draw a trend only from 7 active days of 14 and the weekly seasonal fit VERA used is not built; the workload applies the schedule's fixed rule and does not model further forgetting; a literature review of a topic whose passages come from one paper is a review of one source; read-aloud is the browser's own voice, offered but not listened to in the headless run; the live check of the writing kinds is one attempt per turn and measures grounding, not quality; Timeline, a shown plagiarism report and a gaps block are not built.
